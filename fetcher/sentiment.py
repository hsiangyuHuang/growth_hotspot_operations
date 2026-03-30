"""舆情监控抓取：Twitter 搜索 + Reddit + YouTube

按关键词搜索 OSL 品牌提及，以天为单位抓取。
"""
import asyncio
import hashlib
import json
import logging
import os
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import yaml

from fetcher.utils import retry_get

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "sentiment.yaml"


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _make_id(raw: str) -> str:
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def _dedup_by_url(items: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for item in items:
        if item["url"] not in seen:
            seen.add(item["url"])
            deduped.append(item)
    return deduped


# ── Twitter 搜索 ─────────────────────────────────────────────

async def _fetch_twitter(client: httpx.AsyncClient, cfg: dict) -> list[dict]:
    api_key = os.environ.get("TWITTER_API_KEY", "")
    if not api_key:
        logger.warning("[Sentiment:Twitter] TWITTER_API_KEY not set, skipping")
        return []

    keywords = cfg.get("keywords", {})
    all_kw = keywords.get("twitter", []) + keywords.get("zh", [])
    lookback = cfg.get("lookback_hours", 24)
    content_limit = cfg.get("content_limit", 500)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)
    items = []

    for kw in all_kw:
        resp = await retry_get(
            client,
            "https://api.twitterapi.io/twitter/tweet/advanced_search",
            params={"query": kw, "queryType": "Latest"},
            headers={"X-API-Key": api_key},
            label=f"Sentiment:Twitter:{kw}",
        )
        if resp is None:
            continue

        try:
            data = resp.json()
        except Exception:
            continue

        tweets = data.get("tweets", []) or data.get("data", {}).get("tweets", [])
        for tweet in tweets[:20]:
            from email.utils import parsedate_to_datetime
            try:
                created = parsedate_to_datetime(tweet.get("createdAt", ""))
            except Exception:
                created = None
            if created and created < cutoff:
                continue

            tweet_id = tweet.get("id", "")
            author = tweet.get("author", {})
            author_name = author.get("userName", "")
            url = tweet.get("url") or f"https://x.com/{author_name}/status/{tweet_id}"

            items.append({
                "id": _make_id(f"sent:tw:{tweet_id}"),
                "source": "twitter:search",
                "source_type": "twitter",
                "title": tweet.get("text", "")[:100],
                "content": tweet.get("text", "")[:content_limit],
                "url": url,
                "author": f"@{author_name}" if author_name else "",
                "published_at": created.isoformat() if created else now.isoformat(),
                "fetched_at": now.isoformat(),
                "keyword_matched": kw,
            })
        await asyncio.sleep(3)  # 避免 429

    logger.info(f"[Sentiment:Twitter] {len(items)} items")
    return _dedup_by_url(items)


# ── Reddit 搜索（RapidAPI reddit34）────────────────────────

async def _fetch_reddit(client: httpx.AsyncClient, cfg: dict) -> list[dict]:
    api_key = os.environ.get("RAPIDAPI_KEY", "")
    if not api_key:
        logger.warning("[Sentiment:Reddit] RAPIDAPI_KEY not set, skipping")
        return []

    keywords = cfg.get("keywords", {})
    all_kw = keywords.get("reddit", [])
    content_limit = cfg.get("content_limit", 500)
    lookback = cfg.get("lookback_hours", 24)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)
    items = []

    for kw in all_kw:
        resp = await retry_get(
            client,
            "https://reddit34.p.rapidapi.com/getSearchPosts",
            params={"query": kw, "sort": "new"},
            headers={
                "x-rapidapi-key": api_key,
                "x-rapidapi-host": "reddit34.p.rapidapi.com",
            },
            label=f"Sentiment:Reddit:{kw}",
        )
        if resp is None:
            continue

        try:
            data = resp.json()
        except Exception:
            continue

        posts = []
        if isinstance(data, dict) and data.get("success"):
            posts = data.get("data", {}).get("posts", [])

        for post in posts[:20]:
            pd = post.get("data", post)
            created_utc = pd.get("created_utc")
            if created_utc:
                created = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
                if created < cutoff:
                    continue
            else:
                created = None

            post_id = pd.get("id", "")
            title = pd.get("title", "")
            selftext = pd.get("selftext", "")
            author = pd.get("author", "")
            permalink = pd.get("permalink", "")
            url = f"https://www.reddit.com{permalink}" if permalink else ""
            subreddit = pd.get("subreddit", "")

            items.append({
                "id": _make_id(f"sent:rd:{post_id}"),
                "source": f"reddit:r/{subreddit}" if subreddit else "reddit:search",
                "source_type": "reddit",
                "title": title[:200],
                "content": (selftext or title)[:content_limit],
                "url": url,
                "author": f"u/{author}" if author else "",
                "published_at": created.isoformat() if created else now.isoformat(),
                "fetched_at": now.isoformat(),
                "keyword_matched": kw,
            })
        await asyncio.sleep(1)

    logger.info(f"[Sentiment:Reddit] {len(items)} items")
    return _dedup_by_url(items)


# ── YouTube 搜索（Google YouTube Data API v3）────────────────

async def _fetch_youtube(client: httpx.AsyncClient, cfg: dict) -> list[dict]:
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        logger.warning("[Sentiment:YouTube] YOUTUBE_API_KEY not set, skipping")
        return []

    keywords = cfg.get("keywords", {})
    all_kw = keywords.get("youtube", [])
    content_limit = cfg.get("content_limit", 500)
    lookback = cfg.get("lookback_hours", 24)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)
    published_after = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    items = []

    for kw in all_kw:
        resp = await retry_get(
            client,
            "https://www.googleapis.com/youtube/v3/search",
            params={
                "part": "snippet",
                "q": kw,
                "type": "video",
                "order": "date",
                "maxResults": 10,
                "publishedAfter": published_after,
                "key": api_key,
            },
            label=f"Sentiment:YouTube:{kw}",
        )
        if resp is None:
            continue

        try:
            data = resp.json()
        except Exception:
            continue

        for item_data in data.get("items", []):
            snippet = item_data.get("snippet", {})
            video_id = item_data.get("id", {}).get("videoId", "")
            title = snippet.get("title", "")
            description = snippet.get("description", "")
            channel = snippet.get("channelTitle", "")
            published = snippet.get("publishedAt", "")

            try:
                pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
            except Exception:
                pub_dt = None

            items.append({
                "id": _make_id(f"sent:yt:{video_id}"),
                "source": "youtube:search",
                "source_type": "youtube",
                "title": title[:200],
                "content": (description or title)[:content_limit],
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "author": channel,
                "published_at": pub_dt.isoformat() if pub_dt else now.isoformat(),
                "fetched_at": now.isoformat(),
                "keyword_matched": kw,
            })
        await asyncio.sleep(1)

    logger.info(f"[Sentiment:YouTube] {len(items)} items")
    return _dedup_by_url(items)


# ── 主入口 ───────────────────────────────────────────────────

async def fetch_all(output_path: Path) -> list[dict]:
    """抓取所有平台的舆情数据，写入 output_path。"""
    cfg = _load_config()
    platforms = cfg.get("platforms", {})
    all_items = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; OSL-Bot/1.0)"},
        follow_redirects=True,
    ) as client:
        tasks = []
        if platforms.get("twitter", {}).get("enabled"):
            tasks.append(_fetch_twitter(client, cfg))
        if platforms.get("reddit", {}).get("enabled"):
            tasks.append(_fetch_reddit(client, cfg))
        if platforms.get("youtube", {}).get("enabled"):
            tasks.append(_fetch_youtube(client, cfg))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.warning(f"[Sentiment] Platform fetch failed: {result}")
            else:
                all_items.extend(result)

    # 写入（ID 去重）
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing_ids = {item["id"] for item in existing}
    deduped = [item for item in all_items if item["id"] not in existing_ids]
    existing.extend(deduped)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)

    type_counts = Counter(item["source_type"] for item in all_items)
    logger.info(f"[Sentiment] Stats: {dict(type_counts)}")
    logger.info(f"[Sentiment] Total: {len(all_items)} items -> {output_path}")
    return all_items
