"""用 Gemini 从竞品原始数据中提取结构化竞品动态 JSON。

按 region 分组并行调用 Gemini，每组独立提取后合并结果。
"""
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
5. 每个事件需标注 date（YYYY-MM-DD 格式）。优先从原文提取明确日期；若无明确日期，根据发布时间或上下文推断最可能的日期
6. 如果某竞品近期无重大事件，events 为空数组，summary 应简要描述该竞品近期的一般状态（如"持续运营中，近期以社区互动为主"），不要写"无重大动态"之类的空话
7. sources 中的 name 只填媒体/平台名称（如 "Binance Blog"、"CoinDesk"），不含文章标题
8. 去重：同一事件即使来自多个渠道也只输出一次，但在 sources 中合并所有来源
9. 忽略无实质内容的推文（如纯转发、表情包、无信息量内容）
10. 特别注意识别营销活动类事件（交易赛、空投、Earn 产品推广、推荐奖励、红包、零手续费促销等），归类为「活动推广」
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
                    "summary": {"type": "string", "description": "一句话概览近期动态"},
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
                                "date": {
                                    "type": "string",
                                    "description": "事件日期，格式 YYYY-MM-DD。从原文提取或根据上下文推断",
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
                            "required": ["title", "category", "summary", "importance", "date"],
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
            pub_date = it.get("published", it.get("date", ""))
            if pub_date:
                lines.append(f"- 日期: {pub_date}")
            lines.append(f"- 内容: {content}")
            lines.append("")

    return "\n".join(lines)


def _group_items_by_region(items: list[dict], cfg: dict) -> dict[str, list[dict]]:
    """按 region 分组 items"""
    comp_to_region = {}
    for comp in cfg.get("competitors", []):
        comp_to_region[comp["name"]] = comp.get("region", "HK")

    groups: dict[str, list[dict]] = {}
    for item in items:
        comp_name = item.get("competitor", "Unknown")
        region = comp_to_region.get(comp_name, "OTHER")
        groups.setdefault(region, []).append(item)

    return groups


async def _extract_region(
    client: genai.Client,
    model: str,
    region: str,
    items: list[dict],
    comp_meta: dict,
    max_retries: int = 5,
) -> list[dict]:
    """对单个 region 的 items 调用 Gemini 提取"""
    valid_items = [
        item for item in items
        if item.get("title", "").strip() and len(item.get("title", "")) >= 10
    ]
    if not valid_items:
        return []

    md = _build_items_markdown(valid_items)
    logger.info(f"[CompetitorExtractor:{region}] Input: {len(valid_items)} items, {len(md)} chars")

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

            extracted = result.get("competitors", [])
            for comp in extracted:
                meta = comp_meta.get(comp["name"], {})
                comp["region"] = meta.get("region", region)
                comp["logo"] = meta.get("logo", "")

            logger.info(f"[CompetitorExtractor:{region}] Extracted {len(extracted)} competitors (attempt {attempt})")
            return extracted
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = min(2 ** attempt, 30)
                logger.warning(f"[CompetitorExtractor:{region}] Attempt {attempt} failed: {e}, retrying in {wait}s...")
                await asyncio.sleep(wait)

    logger.error(f"[CompetitorExtractor:{region}] All {max_retries} attempts failed: {last_error}")
    return []


async def extract(items: list[dict], run_date: str) -> dict:
    """按 region 分组并行调用 Gemini 提取，合并结果。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set")
    model = "gemini-3-flash-preview"

    cfg = _load_config()
    comp_meta = {}
    for comp in cfg.get("competitors", []):
        comp_meta[comp["name"]] = {"region": comp.get("region", "HK"), "logo": comp.get("logo", "")}

    # 按 region 分组
    region_groups = _group_items_by_region(items, cfg)
    logger.info(
        f"[CompetitorExtractor] Total {len(items)} items split into {len(region_groups)} regions: "
        + ", ".join(f"{r}({len(v)})" for r, v in sorted(region_groups.items()))
    )

    client = genai.Client(api_key=api_key)

    # 并行提取各 region
    tasks = [
        _extract_region(client, model, region, region_items, comp_meta)
        for region, region_items in sorted(region_groups.items())
    ]
    region_results = await asyncio.gather(*tasks)

    # 合并所有 region 的结果
    extracted_map: dict[str, dict] = {}
    for region_comps in region_results:
        for comp in region_comps:
            extracted_map[comp["name"]] = comp

    # 按配置顺序填充完整竞品列表（补全无数据的竞品）
    full_list = []
    for comp_cfg in cfg.get("competitors", []):
        name = comp_cfg["name"]
        if name in extracted_map:
            full_list.append(extracted_map[name])
        else:
            full_list.append({
                "name": name,
                "region": comp_cfg.get("region", "HK"),
                "logo": comp_cfg.get("logo", ""),
                "summary": f"近期未监测到 {name} 的公开动态",
                "events": [],
            })

    total_events = sum(len(c.get("events", [])) for c in full_list)
    logger.info(f"[CompetitorExtractor] Final: {len(extracted_map)} competitors with data, {total_events} events total")

    return {
        "run_date": run_date,
        "competitors": full_list,
    }
