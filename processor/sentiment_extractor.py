"""用 Gemini 从舆情原始数据中过滤噪音、提取重要 OSL 品牌提及。"""
import asyncio
import json
import logging
import os
from pathlib import Path

from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """你是 OSL（香港持牌加密货币交易所）的舆情分析师。从以下原始社交媒体/视频数据中筛选和提取与 OSL 交易所真正相关的品牌提及。

要求：
1. 过滤掉以下噪音：
   - "OSL" 指的不是 OSL 交易所的内容（如 Oslo 奥斯陆证券交易所代码 OSL、其他缩写）
   - 纯转发、表情包、无实质信息的内容
   - 与 OSL 交易所业务完全无关的内容
2. 必须保留以下类型的用户反馈内容（即使看起来是"日常讨论"）：
   - 用户对 OSL 平台的使用体验、评价、吐槽
   - 关于 OSL 理财收益、KYC、提币、手续费等的讨论
   - 用户投诉、建议、对比其他交易所的评论
   - 社区对 OSL 产品/服务的真实反馈
3. 对保留的内容按重要性分级：
   - high：重大合作、监管动态、安全事件、高影响力 KOL 提及、严重用户投诉
   - medium：产品更新、活动推广、行业分析中提到 OSL、用户使用反馈
   - low：普通日常提及、轻度讨论
4. 同一事件来自多个平台/作者的，合并为一条，sources 中列出所有来源
5. 每条 summary 用简洁中文概括，**加粗**关键信息
6. category 只能是：产品动态、合作伙伴、监管合规、市场分析、用户反馈、活动推广、其他
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "事件标题，简洁明了"},
                    "summary": {"type": "string", "description": "结构化摘要，用**加粗**关键信息"},
                    "category": {
                        "type": "string",
                        "enum": ["产品动态", "合作伙伴", "监管合规", "市场分析", "用户反馈", "活动推广", "其他"],
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
                                "platform": {"type": "string"},
                                "author": {"type": "string"},
                                "url": {"type": "string"},
                            },
                            "required": ["platform", "url"],
                        },
                    },
                    "published_at": {
                        "type": "string",
                        "description": "事件发生时间，ISO 8601 格式，从原始数据的发布时间中提取",
                    },
                },
                "required": ["title", "summary", "category", "importance", "sources", "published_at"],
            },
        },
    },
    "required": ["items"],
}


def _build_items_markdown(items: list[dict]) -> str:
    by_platform: dict[str, list[dict]] = {}
    for item in items:
        p = item.get("source_type", "unknown")
        by_platform.setdefault(p, []).append(item)

    lines = ["# 舆情原始数据", ""]
    for platform, p_items in sorted(by_platform.items()):
        lines.append(f"## {platform} ({len(p_items)} 条)")
        lines.append("")
        for it in p_items:
            lines.append(f"### {it.get('title', '')}")
            lines.append(f"- 作者: {it.get('author', '')}")
            lines.append(f"- 发布时间: {it.get('published_at', '')}")
            lines.append(f"- 链接: {it.get('url', '')}")
            lines.append(f"- 关键词: {it.get('keyword_matched', '')}")
            content = it.get("content", "")[:300]
            if content and content != it.get("title", ""):
                lines.append(f"- 内容: {content}")
            lines.append("")

    return "\n".join(lines)


async def extract(items: list[dict], run_date: str) -> dict:
    """用 Gemini 从舆情原始数据提取结构化品牌提及。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set")
    model = os.environ.get("GEMINI_MODEL", "gemini-3-flash-preview")

    valid_items = [
        item for item in items
        if item.get("title", "").strip() and len(item.get("title", "")) >= 10
    ]
    logger.info(f"[SentimentExtractor] Input: {len(valid_items)}/{len(items)} valid items")

    md = _build_items_markdown(valid_items)
    logger.info(f"[SentimentExtractor] Markdown: {len(md)} chars")

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
            extracted_items = result.get("items", [])

            logger.info(
                f"[SentimentExtractor] Extracted {len(extracted_items)} items "
                f"from {len(valid_items)} raw (attempt {attempt})"
            )

            return {
                "run_date": run_date,
                "total_raw": len(items),
                "items": extracted_items,
            }
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = min(2 ** attempt, 30)
                logger.warning(f"[SentimentExtractor] Attempt {attempt} failed: {e}, retrying in {wait}s...")
                await asyncio.sleep(wait)

    logger.error(f"[SentimentExtractor] All {max_retries} attempts failed: {last_error}")
    raise RuntimeError(f"Sentiment extraction failed after {max_retries} attempts: {last_error}") from last_error
