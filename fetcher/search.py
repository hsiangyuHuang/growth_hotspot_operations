"""多平台关键词搜索 fetcher — Twitter / Reddit / YouTube

通过关键词搜索获取各平台上与 OSL 相关的最新讨论、帖子、视频。
配置在 config/sources.yaml 的 search_sources 段。
"""
import asyncio
import hashlib
import logging
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import httpx
import yaml

from fetcher.utils import append_items

logger = logging.getLogger(__name__)


def _load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config" / "sources.yaml"
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _make_id(platform: str, raw_id: str) -> str:
    return hashlib.md5(f"{platform}:{raw_id}".encode()).hexdigest()[:8]


def _parse_created_at(created_at: str) -> datetime | None:
    """解析 Twitter 格式时间: 'Tue Dec 10 07:00:30 +0000 2024'"""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(created_at)
    except Exception:
        return None


# ── Twitter 搜索 ─────────────────────────────────────────────

async def _search_twitter(client: httpx.AsyncClient, cfg: dict) -> list[dict]:
    """使用 TwitterAPI.io advanced_search 搜索关键词"""
    api_key = os.environ.get("TWITTER_API_KEY", "")
    if not api_key:
        logger.warning("[Search:Twitter] TWITTER_API_KEY not set, skipping")
        return []

    global_cfg = _load_config()
    content_limit = global_cfg.get("content_limit", 500)
    lookback = global_cfg.get("lookback_hours", 24)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)

    queries = cfg.get("queries", [])
    max_results = cfg.get("max_results", 40)
    headers = {"X-API-Key": api_key}
    url = "https://api.twitterapi.io/twitter/tweet/advanced_search"

    all_items = []
    for query in queries:
        try:
            resp = await client.get(
                url,
                params={"query": query, "queryType": "Latest"},
                headers=headers,
                timeout=15.0,
            )
            if resp.status_code == 429:
                logger.warning(f"[Search:Twitter] 429 限流，跳过 query: {query[:50]}")
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[Search:Twitter] Failed query '{query[:50]}': {e}")
            continue

        tweets = data.get("tweets", [])
        for tweet in tweets[:max_results]:
            created = _parse_created_at(tweet.get("createdAt", ""))
            if created and created < cutoff:
                continue

            tweet_id = tweet.get("id", "")
            author = tweet.get("author", {}).get("userName", "unknown")
            tweet_url = tweet.get("url") or f"https://x.com/{author}/status/{tweet_id}"

            all_items.append({
                "id": _make_id("twitter", tweet_id),
                "source": "search:twitter",
                "title": tweet.get("text", "")[:100],
                "content": tweet.get("text", "")[:content_limit],
                "url": tweet_url,
                "published_at": created.isoformat() if created else now.isoformat(),
                "fetched_at": now.isoformat(),
                "lang": "en",
                "processed": False,
            })

        await asyncio.sleep(2)  # 避免限流

    logger.info(f"[Search:Twitter] {len(all_items)} results")
    return all_items


# ── Reddit 搜索 ──────────────────────────────────────────────

async def _search_reddit(client: httpx.AsyncClient, cfg: dict) -> list[dict]:
    """使用 Reddit .json 免认证模式搜索"""
    global_cfg = _load_config()
    content_limit = global_cfg.get("content_limit", 500)
    lookback = global_cfg.get("lookback_hours", 24)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)

    subreddits = cfg.get("subreddits", [])
    query = cfg.get("query", "OSL exchange")
    sort = cfg.get("sort", "new")
    time_filter = cfg.get("time_filter", "day")
    max_results = cfg.get("max_results", 30)

    all_items = []
    for sub in subreddits:
        url = f"https://www.reddit.com/r/{sub}/search.json"
        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "restrict_sr": "on",
            "limit": min(max_results, 25),
        }
        try:
            resp = await client.get(url, params=params, timeout=15.0)
            if resp.status_code == 429:
                logger.warning(f"[Search:Reddit] 429 限流 r/{sub}，跳过")
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[Search:Reddit] Failed r/{sub}: {e}")
            continue

        posts = data.get("data", {}).get("children", [])
        for post in posts:
            pd = post.get("data", {})
            created_utc = pd.get("created_utc")
            if created_utc:
                created = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if created < cutoff:
                    continue
            else:
                created = None

            post_id = pd.get("id", "")
            title = pd.get("title", "")
            selftext = pd.get("selftext", "")
            permalink = pd.get("permalink", "")
            subreddit = pd.get("subreddit", sub)

            all_items.append({
                "id": _make_id("reddit", post_id),
                "source": f"search:reddit:r/{subreddit}",
                "title": title[:200],
                "content": (selftext or title)[:content_limit],
                "url": f"https://www.reddit.com{permalink}" if permalink else "",
                "published_at": created.isoformat() if created else now.isoformat(),
                "fetched_at": now.isoformat(),
                "lang": "en",
                "processed": False,
            })

        await asyncio.sleep(6)  # Reddit ~10 QPM，保守间隔

    logger.info(f"[Search:Reddit] {len(all_items)} results")
    return all_items


# ── YouTube 搜索 ─────────────────────────────────────────────

async def _search_youtube(client: httpx.AsyncClient, cfg: dict) -> list[dict]:
    """使用 YouTube Data API v3 搜索"""
    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        logger.info("[Search:YouTube] YOUTUBE_API_KEY not set, skipping")
        return []

    global_cfg = _load_config()
    content_limit = global_cfg.get("content_limit", 500)
    lookback = global_cfg.get("lookback_hours", 24)
    now = datetime.now(tz=timezone.utc)
    published_after = (now - timedelta(hours=lookback)).strftime("%Y-%m-%dT%H:%M:%SZ")

    query = cfg.get("query", "OSL exchange crypto")
    max_results = cfg.get("max_results", 20)
    order = cfg.get("order", "date")

    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "order": order,
        "maxResults": min(max_results, 50),
        "publishedAfter": published_after,
        "key": api_key,
    }

    try:
        resp = await client.get(url, params=params, timeout=15.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"[Search:YouTube] Failed: {e}")
        return []

    items = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        video_id = item.get("id", {}).get("videoId", "")
        if not video_id:
            continue

        channel = snippet.get("channelTitle", "unknown")
        published = snippet.get("publishedAt", "")
        title = snippet.get("title", "")
        description = snippet.get("description", "")

        items.append({
            "id": _make_id("youtube", video_id),
            "source": f"search:youtube:{channel}",
            "title": title[:200],
            "content": (description or title)[:content_limit],
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "published_at": published or now.isoformat(),
            "fetched_at": now.isoformat(),
            "lang": "en",
            "processed": False,
        })

    logger.info(f"[Search:YouTube] {len(items)} results")
    return items


# ── 主入口 ───────────────────────────────────────────────────

async def search_all(output_path: Path) -> list[dict]:
    """搜索所有已启用的平台，返回合并结果"""
    cfg = _load_config().get("search_sources", {})
    if not cfg:
        logger.info("[Search] No search_sources configured, skipping")
        return []

    all_items = []
    async with httpx.AsyncClient(
        headers={"User-Agent": "OSL-Bot/1.0"},
        follow_redirects=True,
    ) as client:
        # Twitter 搜索
        twitter_cfg = cfg.get("twitter", {})
        if twitter_cfg.get("enabled"):
            items = await _search_twitter(client, twitter_cfg)
            all_items.extend(items)

        # Reddit 搜索
        reddit_cfg = cfg.get("reddit", {})
        if reddit_cfg.get("enabled"):
            items = await _search_reddit(client, reddit_cfg)
            all_items.extend(items)

        # YouTube 搜索
        youtube_cfg = cfg.get("youtube", {})
        if youtube_cfg.get("enabled"):
            items = await _search_youtube(client, youtube_cfg)
            all_items.extend(items)

    if all_items:
        append_items(output_path, all_items)
    logger.info(f"[Search] Total: {len(all_items)} items written to {output_path}")
    return all_items
