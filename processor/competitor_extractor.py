"""用 Gemini 从竞品原始数据中提取结构化竞品动态 JSON。"""
import asyncio
import json
import logging
import os
from pathlib import Path

import yaml
from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "competitors.yaml"


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


EXTRACTION_PROMPT = """你是一个竞品情报分析师。从以下原始数据中提取各竞品的最新动态。

要求：
1. 按竞品分组，每个竞品输出一句话概览 summary 和详细事件列表 events
2. 事件分类 category 只能是以下之一：新币上线、产品更新、活动推广、合作伙伴、监管合规、融资/IPO、人事变动、其他
3. 每个事件的 summary 使用结构化 Markdown：**加粗**关键信息，用列表列举要点
4. importance 分三级：high（重大战略动作）、medium（常规运营）、low（日常信息）
5. 如果某竞品当日无实质动态，仍需输出该竞品但 events 为空数组，summary 写"今日无重大动态"
6. sources 中的 name 只填媒体/平台名称（如 "Binance Blog"、"CoinDesk"），不含文章标题
7. 去重：同一事件即使来自多个渠道也只输出一次，但在 sources 中合并所有来源
8. 忽略无实质内容的推文（如纯转发、表情包、无信息量内容）
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "competitors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "竞品名称"},
                    "summary": {"type": "string", "description": "一句话概览今日动态"},
                    "events": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "事件标题，简洁明了"},
                                "category": {
                                    "type": "string",
                                    "enum": ["新币上线", "产品更新", "活动推广", "合作伙伴",
                                             "监管合规", "融资/IPO", "人事变动", "其他"],
                                },
                                "summary": {
                                    "type": "string",
                                    "description": "结构化 Markdown 摘要：用**加粗**和列表",
                                },
                                "importance": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "sources": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string", "description": "媒体/平台名称"},
                                            "url": {"type": "string"},
                                        },
                                        "required": ["name", "url"],
                                    },
                                },
                            },
                            "required": ["title", "category", "summary", "importance"],
                        },
                    },
                },
                "required": ["name", "summary", "events"],
            },
        },
    },
    "required": ["competitors"],
}


def _build_items_markdown(items: list[dict]) -> str:
    """将原始 items 转为 Markdown 供 Gemini 处理"""
    by_comp: dict[str, list[dict]] = {}
    for item in items:
        comp = item.get("competitor", "Unknown")
        by_comp.setdefault(comp, []).append(item)

    lines = ["# 竞品原始数据", ""]
    for comp, comp_items in sorted(by_comp.items()):
        lines.append(f"## {comp} ({len(comp_items)} 条)")
        lines.append("")
        for it in comp_items:
            src = it.get("source", "")
            title = it.get("title", "")
            content = it.get("content", "")[:300]
            url = it.get("url", "")
            lines.append(f"### {title}")
            lines.append(f"- 来源: {src}")
            lines.append(f"- 链接: {url}")
            lines.append(f"- 内容: {content}")
            lines.append("")

    return "\n".join(lines)


async def extract(items: list[dict], run_date: str) -> dict:
    """用 Gemini 从竞品原始数据提取结构化动态。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set")
    model = "gemini-3-flash-preview"

    # 加载竞品配置获取 region
    cfg = _load_config()
    comp_meta = {}
    for comp in cfg.get("competitors", []):
        comp_meta[comp["name"]] = {"region": comp.get("region", "HK")}

    # 过滤无效 items
    valid_items = [
        item for item in items
        if item.get("title", "").strip() and len(item.get("title", "")) >= 10
    ]
    if len(valid_items) < len(items):
        logger.info(f"[CompetitorExtractor] Filtered {len(items) - len(valid_items)} invalid items")

    md = _build_items_markdown(valid_items)
    logger.info(f"[CompetitorExtractor] Input: {len(valid_items)} items, {len(md)} chars markdown")

    client = genai.Client(api_key=api_key)
    max_retries = 5
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=f"{EXTRACTION_PROMPT}\n\n---\n\n{md}",
                config=GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                ),
            )
            result = json.loads(response.text)

            # 注入 region，并补全配置中所有未被 Gemini 输出的竞品（events 为空）
            extracted = {c["name"]: c for c in result.get("competitors", [])}
            for comp in result.get("competitors", []):
                meta = comp_meta.get(comp["name"], {})
                comp["region"] = meta.get("region", "HK")

            # 按配置顺序填充完整竞品列表
            full_list = []
            for comp_cfg in cfg.get("competitors", []):
                name = comp_cfg["name"]
                if name in extracted:
                    full_list.append(extracted[name])
                else:
                    full_list.append({
                        "name": name,
                        "region": comp_cfg.get("region", "HK"),
                        "summary": "今日无重大动态",
                        "events": [],
                    })

            logger.info(
                f"[CompetitorExtractor] Extracted {len(extracted)} competitors with data, "
                f"{len(full_list)} total (attempt {attempt})"
            )

            return {
                "run_date": run_date,
                "competitors": full_list,
            }
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = min(2 ** attempt, 30)
                logger.warning(f"[CompetitorExtractor] Attempt {attempt} failed: {e}, retrying in {wait}s...")
                await asyncio.sleep(wait)

    logger.error(f"[CompetitorExtractor] All {max_retries} attempts failed: {last_error}")
    raise RuntimeError(f"Competitor extraction failed after {max_retries} attempts: {last_error}") from last_error
