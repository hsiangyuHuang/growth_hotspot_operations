"""Telegram fetcher: 使用 Telethon 拉取频道 24h 内消息"""
import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

from fetcher.utils import append_items

logger = logging.getLogger(__name__)

def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "sources.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _load_channels() -> list[str]:
    return _load_config().get("telegram", {}).get("channels", [])


def _make_id(channel: str, msg_id: int) -> str:
    key = f"{channel}:{msg_id}"
    return hashlib.md5(key.encode()).hexdigest()[:8]


async def fetch_channel(client, channel: str, cutoff: datetime) -> list[dict]:
    items = []
    now = datetime.now(tz=timezone.utc)

    try:
        async for msg in client.iter_messages(channel, limit=200):
            if msg.date.replace(tzinfo=timezone.utc) < cutoff:
                break
            if not msg.text:
                continue

            url = f"https://t.me/{channel}/{msg.id}"
            item = {
                "id": _make_id(channel, msg.id),
                "source": f"telegram:{channel}",
                "title": msg.text[:100],
                "content": msg.text[:500],
                "url": url,
                "published_at": msg.date.replace(tzinfo=timezone.utc).isoformat(),
                "fetched_at": now.isoformat(),
                "lang": "zh" if channel in ("theblockbeats", "odailycn") else "en",
                "processed": False,
            }
            items.append(item)
    except Exception as e:
        logger.warning(f"[Telegram] Failed to fetch {channel}: {e}")

    logger.info(f"[Telegram] {channel}: {len(items)} messages")
    return items


async def fetch_all(output_path: Path) -> list[dict]:
    api_id = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "")
    phone = os.environ.get("TELEGRAM_PHONE_NUMBER", "")

    if not api_id or not api_hash:
        logger.warning("[Telegram] TELEGRAM_API_ID/HASH not set, skipping")
        return []

    try:
        from telethon import TelegramClient
    except ImportError:
        logger.warning("[Telegram] telethon not installed, skipping")
        return []

    channels = _load_channels()
    lookback = _load_config().get("lookback_hours", 24)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    all_items = []

    session_path = str(Path(__file__).parent.parent / "telegram_session")
    client = TelegramClient(session_path, int(api_id), api_hash)

    try:
        await client.start(phone=phone)
        import asyncio
        tasks = [fetch_channel(client, ch, cutoff) for ch in channels]
        results = await asyncio.gather(*tasks)
        for items in results:
            all_items.extend(items)
    finally:
        await client.disconnect()

    append_items(output_path, all_items)
    logger.info(f"[Telegram] Total: {len(all_items)} messages written to {output_path}")
    return all_items
