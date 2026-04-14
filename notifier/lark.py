"""飞书 Webhook 推送 — 每日热点简报（精简行列式）"""
import asyncio
import json
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://growth-operations.vercel.app"


def _build_card(cards: list[dict], run_date: str) -> dict:
    """构建飞书 Interactive Card JSON — 精简行列式，无分类标签。"""

    header = {
        "title": {"tag": "plain_text", "content": f"增长热点日报 — {run_date}  ·  {len(cards)} 条"},
        "template": "blue",
    }

    elements: list[dict] = []

    # 每条热点一行：标题 + 摘要 + 信源链接
    lines = []
    for card in cards:
        title = card.get("title", "")
        summary = card.get("summary", "")

        sources = card.get("sources", [])
        src_parts = [f"[{s['name']}]({s['url']})" for s in sources if s.get("url")]
        src_line = " · ".join(src_parts)

        line = f"**{title}**\n<font color='grey'>*{summary}*</font>"
        if src_line:
            line += f"\n{src_line}"
        lines.append(line)

    elements.append({"tag": "div", "text": {"tag": "lark_md", "content": "\n".join(lines)}})

    # ── 看板按钮 ──
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "actions": [{
            "tag": "button",
            "text": {"tag": "plain_text", "content": "热点监测工具"},
            "url": DASHBOARD_URL,
            "type": "primary",
        }],
    })

    # ── Footer ──
    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "OSL Growth Intelligence · 自动生成"}],
    })

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True, "enable_forward": True},
            "header": header,
            "elements": elements,
        },
    }


async def push_hotspot_briefing(cards: list[dict], run_date: str) -> bool:
    """推送热点简报到飞书 Webhook，失败不抛异常。"""
    webhook_url = os.environ.get("LARK_WEBHOOK_URL", "")
    if not webhook_url:
        logger.warning("LARK_WEBHOOK_URL 未配置，跳过飞书推送")
        return False

    payload = _build_card(cards, run_date)

    async with httpx.AsyncClient() as client:
        for attempt in range(2):
            try:
                resp = await client.post(webhook_url, json=payload, timeout=10.0)
                data = resp.json()
                if data.get("code") == 0:
                    logger.info(f"飞书推送成功：{len(cards)} 条热点")
                    return True
                else:
                    logger.warning(f"飞书推送失败：{data}")
                    return False
            except Exception as e:
                if attempt == 0:
                    logger.info(f"飞书推送异常，重试：{e}")
                    await asyncio.sleep(2)
                    continue
                logger.warning(f"飞书推送失败：{e}")
                return False
    return False


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    latest = Path(__file__).parent.parent / "data" / "processed" / "latest.json"
    if not latest.exists():
        print("latest.json 不存在")
        raise SystemExit(1)

    with open(latest, "r", encoding="utf-8") as f:
        data = json.load(f)

    ok = asyncio.run(push_hotspot_briefing(
        data.get("cards", []),
        data.get("run_date", "unknown"),
    ))
    print("推送成功" if ok else "推送失败")
