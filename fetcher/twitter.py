"""Twitter fetcher: 使用 TwitterAPI.io 抓取指定账号最新推文"""
import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx
import yaml

from fetcher.utils import append_items

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "sources.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _load_accounts() -> list[str]:
    return _load_config().get("twitter", {}).get("accounts", [])


def _parse_created_at(created_at: str) -> datetime | None:
    """解析 Twitter 格式时间: 'Tue Dec 10 07:00:30 +0000 2024'"""
    try:
        return parsedate_to_datetime(created_at)
    except Exception:
        return None


def _make_id(tweet_id: str) -> str:
    return hashlib.md5(tweet_id.encode()).hexdigest()[:8]


MAX_RETRIES = 3


async def fetch_account(client: httpx.AsyncClient, handle: str, api_key: str, base_url: str) -> list[dict]:
    import asyncio
    cfg = _load_config()
    lookback = cfg.get("lookback_hours", 24)
    max_tweets = cfg.get("twitter", {}).get("max_tweets_per_account", 20)
    content_limit = cfg.get("content_limit", 500)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    params = {"userName": handle, "includeReplies": "false"}
    headers = {"X-API-Key": api_key}

    data = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = await client.get(base_url, params=params, headers=headers, timeout=15.0)
            if resp.status_code == 429:
                wait = 5 * (attempt + 1)
                logger.info(f"[Twitter] @{handle} 429 限流，等 {wait}s 后重试 ({attempt+1}/{MAX_RETRIES})")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                logger.warning(f"[Twitter] Failed to fetch @{handle}: {e}")
                return []

    if data is None:
        logger.warning(f"[Twitter] @{handle} 重试耗尽")
        return []

    tweets = data.get("data", {}).get("tweets", []) or data.get("tweets", [])
    items = []
    now = datetime.now(tz=timezone.utc)

    for tweet in tweets[:max_tweets]:
        created = _parse_created_at(tweet.get("createdAt", ""))
        if created and created < cutoff:
            continue

        tweet_id = tweet.get("id", "")
        author = tweet.get("author", {}).get("userName", handle)
        url = tweet.get("url") or f"https://x.com/{author}/status/{tweet_id}"

        item = {
            "id": _make_id(tweet_id),
            "source": f"twitter:@{handle}",
            "title": tweet.get("text", "")[:100],
            "content": tweet.get("text", "")[:content_limit],
            "url": url,
            "published_at": created.isoformat() if created else now.isoformat(),
            "fetched_at": now.isoformat(),
            "lang": "en",
            "processed": False,
        }
        items.append(item)

    logger.info(f"[Twitter] @{handle}: {len(items)} tweets")
    return items


async def fetch_all(output_path: Path) -> list[dict]:
    api_key = os.environ.get("TWITTER_API_KEY", "")
    if not api_key:
        logger.warning("[Twitter] TWITTER_API_KEY not set, skipping")
        return []
    base_url = os.environ.get("TWITTER_API_BASE", "")
    if not base_url:
        logger.warning("[Twitter] TWITTER_API_BASE not set, skipping")
        return []

    accounts = _load_accounts()
    all_items = []

    import asyncio
    async with httpx.AsyncClient(follow_redirects=True) as client:
        for handle in accounts:
            items = await fetch_account(client, handle, api_key, base_url)
            all_items.extend(items)
            await asyncio.sleep(3)  # 避免 429 限流

    append_items(output_path, all_items)
    logger.info(f"[Twitter] Total: {len(all_items)} tweets written to {output_path}")
    return all_items
