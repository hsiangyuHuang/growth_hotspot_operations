"""调用 Gemini 从 Manus markdown 中提取结构化行动包 JSON。"""
import asyncio
import json
import logging
import os

from google import genai
from google.genai.types import GenerateContentConfig

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """你是一个结构化数据提取器。从以下 markdown 中提取所有行动包。

要求：
1. 只提取行动包部分（忽略前面的原始数据和 Layer 1-3 中间过程）
2. 渠道 name 只能是："Paid Ads"、"站内运营 / 用户触达"、"SEO"、"社区"
3. priority 只能是 P0/P1/P2，从上下文推断（如 section 标题"P0 级"或元数据行）
4. 如果某个字段在原文中找不到，设为 null
5. sources 中的 name 只填写媒体/来源的名称（如 "CoinDesk"、"律动 BlockBeats"、"WuBlockchain"），不要包含文章标题或其他内容
6. sources 中的 url：从信源引用中的 markdown 链接提取，格式如 [媒体名](url)，将 url 部分填入。如果没有链接则设为空字符串
7. channels 中的 markdown 字段必须使用结构化的 Markdown 格式，而不是纯文本段落。要求：
   - 用 **加粗** 标注关键信息（受众定向、核心策略、CTA、KPI 等）
   - 用分段小标题（如 `### 受众定向`、`### 素材与文案`、`### 落地页`、`### 注意事项`）分割内容
   - 用有序或无序列表列举具体步骤、要点或注意事项
   - 确保内容可扫读，避免大段文字
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
                    "timing": {"type": "string", "enum": ["Flash", "Day", "Wave", "Trend"], "nullable": True},
                    "relation": {"type": "string", "enum": ["Direct", "Indirect", "Brand", "Gap"], "nullable": True},
                    "intent": {"type": "string", "nullable": True},
                    "site": {"type": "string", "enum": ["HK", "Global", "Both"], "nullable": True},
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
                                "markdown": {"type": "string", "description": "使用结构化 Markdown：用 ### 小标题分段、**加粗**标注关键信息、用列表列举步骤和要点。禁止纯文本段落。"},
                            },
                            "required": ["name", "markdown"],
                        },
                    },
                    "sources": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "媒体/来源名称，如 CoinDesk、律动 BlockBeats、WuBlockchain，不含文章标题"},
                                "url": {"type": "string"},
                            },
                            "required": ["name", "url"],
                        },
                    },
                },
                "required": ["title", "priority"],
            },
        },
    },
    "required": ["cards"],
}


async def extract(markdown: str, run_date: str) -> dict:
    """用 Gemini 从 markdown 提取结构化行动包。失败时直接报错，不做 fallback。"""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY not set")
    model = "gemini-3-flash-preview"

    client = genai.Client(api_key=api_key)
    max_retries = 5
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
            }
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = min(2 ** attempt, 30)
                logger.warning(f"[Extractor] Attempt {attempt} failed: {e}, retrying in {wait}s...")
                await asyncio.sleep(wait)

    logger.error(f"[Extractor] All {max_retries} attempts failed: {last_error}")
    raise RuntimeError(f"Gemini extraction failed after {max_retries} attempts: {last_error}") from last_error
