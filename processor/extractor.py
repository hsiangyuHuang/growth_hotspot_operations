"""调用 Gemini 从 Manus markdown 中提取结构化行动包 JSON。"""
import json
import logging
import os
import time

from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """你是一个结构化数据提取器。从以下 markdown 中提取所有行动包。

要求：
1. 只提取行动包部分（忽略前面的原始数据和 Layer 1-3 中间过程）
2. 渠道 name 只能是："Paid Ads"、"站内运营 / 用户触达"、"SEO"、"社区"
3. priority 只能是 P0/P1/P2，从上下文推断（如 section 标题"P0 级"或元数据行）
4. 如果某个字段在原文中找不到，设为 null
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "priority": {"type": "string", "enum": ["P0", "P1", "P2"]},
                    "category": {"type": "string", "nullable": True},
                    "timing": {"type": "string", "enum": ["Day", "Wave", "Trend"], "nullable": True},
                    "relation": {"type": "string", "enum": ["Direct", "Indirect", "Brand"], "nullable": True},
                    "intent": {"type": "string", "nullable": True},
                    "site": {"type": "string", "enum": ["HK", "Global", "Both"], "nullable": True},
                    "executability": {"type": "string", "enum": ["A", "B", "C", "D"], "nullable": True},
                    "summary": {"type": "string", "nullable": True},
                    "dont_do": {"type": "string", "nullable": True},
                    "channels": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "enum": ["Paid Ads", "站内运营 / 用户触达", "SEO", "社区"],
                                },
                                "markdown": {"type": "string"},
                            },
                            "required": ["name", "markdown"],
                        },
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "url": {"type": "string"},
                            },
                            "required": ["name", "url"],
                        },
                    },
                },
                "required": ["title", "priority"],
            },
        },
        "product_gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["signal", "description"],
            },
        },
    },
    "required": ["cards", "product_gaps"],
}


def extract(markdown: str, run_date: str) -> dict:
    """用 Gemini 从 markdown 提取结构化行动包。失败时直接报错，不做 fallback。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set")
    model = "gemini-3-flash-preview"

    client = genai.Client(api_key=api_key)
    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=f"{EXTRACTION_PROMPT}\n\n---\n\n{markdown}",
                config=GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=RESPONSE_SCHEMA,
                ),
            )

            result = json.loads(response.text)

            for i, card in enumerate(result.get("cards", []), 1):
                card["id"] = f"ap_{i}"
                # 清理 title 中可能残留的 markdown 方括号
                title = card.get("title", "")
                if title.startswith("[") and title.endswith("]"):
                    card["title"] = title[1:-1]

            logger.info(f"[Extractor] Gemini extracted {len(result.get('cards', []))} cards (attempt {attempt})")

            return {
                "run_date": run_date,
                "header_markdown": "",
                "cards": result.get("cards", []),
                "product_gaps": result.get("product_gaps", []),
            }
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"[Extractor] Attempt {attempt} failed: {e}, retrying in {wait}s...")
                time.sleep(wait)

    logger.error(f"[Extractor] All {max_retries} attempts failed: {last_error}")
    raise RuntimeError(f"Gemini extraction failed after {max_retries} attempts: {last_error}") from last_error
