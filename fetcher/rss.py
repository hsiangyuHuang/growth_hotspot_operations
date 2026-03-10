"""RSS fetcher: 并发抓取多个 RSS 源，过滤 24h 内条目，写入 items.json"""
import asyncio
import hashlib
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import httpx
import yaml

from fetcher.utils import append_items

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "sources.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _load_sources() -> list[dict]:
    return _load_config().get("rss", [])


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _get_content(entry) -> str:
    # 优先 content:encoded
    if hasattr(entry, "content") and entry.content:
        raw = entry.content[0].get("value", "")
    elif hasattr(entry, "summary"):
        raw = entry.summary
    else:
        raw = ""
    content_limit = _load_config().get("content_limit", 500)
    return _strip_html(raw)[:content_limit]


def _parse_published(entry) -> datetime | None:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        import calendar
        ts = calendar.timegm(entry.published_parsed)
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return None


def _make_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:8]


async def fetch_feed(client: httpx.AsyncClient, source: dict) -> list[dict]:
    url = source["url"]
    name = source["name"]
    lang = source.get("lang", "en")
    lookback = _load_config().get("lookback_hours", 24)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)

    try:
        resp = await client.get(url, timeout=15.0)
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"[RSS] Failed to fetch {name} ({url}): {e}")
        return []

    feed = feedparser.parse(resp.text)
    items = []
    for entry in feed.entries:
        published = _parse_published(entry)
        if published and published < cutoff:
            continue  # 过旧

        link = getattr(entry, "link", "")
        title = getattr(entry, "title", "")
        content = _get_content(entry)
        now = datetime.now(tz=timezone.utc)

        item = {
            "id": _make_id(link or title),
            "source": name,
            "title": title,
            "content": content,
            "url": link,
            "published_at": published.isoformat() if published else now.isoformat(),
            "fetched_at": now.isoformat(),
            "lang": lang,
            "processed": False,
        }
        items.append(item)

    logger.info(f"[RSS] {name}: {len(items)} items")
    return items


async def fetch_all(output_path: Path) -> list[dict]:
    sources = _load_sources()
    all_items = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; OSL-Bot/1.0)"},
        follow_redirects=True,
    ) as client:
        tasks = [fetch_feed(client, src) for src in sources]
        results = await asyncio.gather(*tasks)

    for items in results:
        all_items.extend(items)

    # 追加写入（若文件已存在则合并）
    append_items(output_path, all_items)
    logger.info(f"[RSS] Total: {len(all_items)} items written to {output_path}")
    return all_items
