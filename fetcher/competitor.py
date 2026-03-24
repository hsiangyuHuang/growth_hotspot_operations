"""竞品多渠道抓取：Twitter + RSS + 网页解析，输出 items.json"""
import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import httpx
import yaml


logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "competitors.yaml"


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _make_id(raw: str) -> str:
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


# ── Twitter 抓取 ─────────────────────────────────────────────────

async def _fetch_twitter(client: httpx.AsyncClient, accounts: list[str],
                         competitor_name: str, cfg: dict) -> list[dict]:
    api_key = os.environ.get("TWITTER_API_KEY", "")
    if not api_key:
        logger.warning("[Competitor:Twitter] TWITTER_API_KEY not set, skipping")
        return []

    base_url = "https://api.twitterapi.io/twitter/user/last_tweets"
    lookback = cfg.get("lookback_hours", 24)
    content_limit = cfg.get("content_limit", 500)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)
    headers = {"X-API-Key": api_key}
    items = []

    for handle in accounts:
        try:
            resp = await client.get(
                base_url,
                params={"userName": handle, "includeReplies": "false"},
                headers=headers, timeout=15.0,
            )
            if resp.status_code == 429:
                logger.warning(f"[Competitor:Twitter] @{handle} 429, skipping")
                await asyncio.sleep(5)
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"[Competitor:Twitter] @{handle} failed: {e}")
            continue

        tweets = data.get("data", {}).get("tweets", []) or data.get("tweets", [])
        for tweet in tweets[:20]:
            from email.utils import parsedate_to_datetime
            try:
                created = parsedate_to_datetime(tweet.get("createdAt", ""))
            except Exception:
                created = None
            if created and created < cutoff:
                continue

            tweet_id = tweet.get("id", "")
            author = tweet.get("author", {}).get("userName", handle)
            url = tweet.get("url") or f"https://x.com/{author}/status/{tweet_id}"

            items.append({
                "id": _make_id(tweet_id),
                "competitor": competitor_name,
                "source": f"twitter:@{handle}",
                "source_type": "twitter",
                "title": tweet.get("text", "")[:100],
                "content": tweet.get("text", "")[:content_limit],
                "url": url,
                "published_at": created.isoformat() if created else now.isoformat(),
                "fetched_at": now.isoformat(),
            })
        await asyncio.sleep(3)

    logger.info(f"[Competitor:Twitter] {competitor_name}: {len(items)} tweets")
    return items


# ── RSS 抓取 ──────────────────────────────────────────────────────

async def _fetch_rss(client: httpx.AsyncClient, rss_sources: list[dict],
                     competitor_name: str, cfg: dict) -> list[dict]:
    lookback = cfg.get("lookback_hours", 24)
    content_limit = cfg.get("content_limit", 500)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)
    items = []

    for src in rss_sources:
        url = src.get("url", "")
        name = src.get("name", url)
        try:
            resp = await client.get(url, timeout=15.0)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"[Competitor:RSS] {name} failed: {e}")
            continue

        feed = feedparser.parse(resp.text)
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                import calendar
                ts = calendar.timegm(entry.published_parsed)
                published = datetime.fromtimestamp(ts, tz=timezone.utc)
            if published and published < cutoff:
                continue

            link = getattr(entry, "link", "")
            title = getattr(entry, "title", "")
            raw_content = ""
            if hasattr(entry, "content") and entry.content:
                raw_content = entry.content[0].get("value", "")
            elif hasattr(entry, "summary"):
                raw_content = entry.summary
            content = _strip_html(raw_content)[:content_limit]

            items.append({
                "id": _make_id(link or title),
                "competitor": competitor_name,
                "source": name,
                "source_type": "rss",
                "title": title,
                "content": content,
                "url": link,
                "published_at": published.isoformat() if published else now.isoformat(),
                "fetched_at": now.isoformat(),
            })

    logger.info(f"[Competitor:RSS] {competitor_name}: {len(items)} items")
    return items


# ── 网页抓取 ──────────────────────────────────────────────────────

async def _fetch_web(client: httpx.AsyncClient, web_sources: list[dict],
                     competitor_name: str, cfg: dict) -> list[dict]:
    content_limit = cfg.get("content_limit", 500)
    now = datetime.now(tz=timezone.utc)
    items = []

    for src in web_sources:
        url = src.get("url", "")
        try:
            resp = await client.get(url, timeout=20.0)
            resp.raise_for_status()
            html = resp.text
        except Exception as e:
            logger.warning(f"[Competitor:Web] {url} failed: {e}")
            continue

        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")

            # 通用策略：查找文章/公告链接
            anchors = []
            for selector in ["article a", ".article a", ".post a", ".announcement a",
                             "a[href*='announcement']", "a[href*='blog']", "a[href*='news']",
                             "h2 a", "h3 a", ".list-item a", ".card a"]:
                anchors.extend(soup.select(selector))

            # 去重
            seen = set()
            for a in anchors:
                href = a.get("href", "")
                if not href or href in seen or href.startswith("#"):
                    continue
                seen.add(href)

                title = a.get_text(strip=True)
                if not title or len(title) < 5:
                    continue
                if not href.startswith("http"):
                    from urllib.parse import urljoin
                    href = urljoin(url, href)

                items.append({
                    "id": _make_id(href),
                    "competitor": competitor_name,
                    "source": f"web:{competitor_name}",
                    "source_type": "web",
                    "title": title[:200],
                    "content": title[:content_limit],
                    "url": href,
                    "published_at": now.isoformat(),
                    "fetched_at": now.isoformat(),
                })

                if len(items) >= 20:
                    break

        except ImportError:
            logger.warning("[Competitor:Web] beautifulsoup4 not installed, skipping web scraping")
            break
        except Exception as e:
            logger.warning(f"[Competitor:Web] Parse error for {url}: {e}")

    logger.info(f"[Competitor:Web] {competitor_name}: {len(items)} items")
    return items


# ── 媒体关键词过滤 ────────────────────────────────────────────────

def _filter_media_items(hotspot_items: list[dict], cfg: dict) -> list[dict]:
    """从现有热点 items 中筛选竞品相关的媒体报道"""
    media_keywords = cfg.get("media_keywords", {})
    now = datetime.now(tz=timezone.utc)
    items = []

    for comp_name, keywords in media_keywords.items():
        for item in hotspot_items:
            text = f"{item.get('title', '')} {item.get('content', '')}".lower()
            for kw in keywords:
                if kw.lower() in text:
                    items.append({
                        "id": _make_id(f"media:{comp_name}:{item.get('id', '')}"),
                        "competitor": comp_name,
                        "source": item.get("source", "media"),
                        "source_type": "media",
                        "title": item.get("title", ""),
                        "content": item.get("content", ""),
                        "url": item.get("url", ""),
                        "published_at": item.get("published_at", now.isoformat()),
                        "fetched_at": now.isoformat(),
                    })
                    break  # 一条 item 只匹配一次

    logger.info(f"[Competitor:Media] Found {len(items)} media items about competitors")
    return items


# ── 主入口 ────────────────────────────────────────────────────────

async def fetch_all(output_path: Path, hotspot_items: list[dict] | None = None) -> list[dict]:
    """抓取所有竞品数据，写入 output_path"""
    cfg = _load_config()
    competitors = cfg.get("competitors", [])
    all_items = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; OSL-Bot/1.0)"},
        follow_redirects=True,
    ) as client:
        for comp in competitors:
            name = comp["name"]
            logger.info(f"[Competitor] Fetching {name}...")

            # Twitter
            twitter_accounts = comp.get("twitter", [])
            if twitter_accounts:
                items = await _fetch_twitter(client, twitter_accounts, name, cfg)
                all_items.extend(items)

            # RSS
            rss_sources = comp.get("rss", [])
            if rss_sources:
                items = await _fetch_rss(client, rss_sources, name, cfg)
                all_items.extend(items)

            # Web scraping
            web_sources = comp.get("web", [])
            if web_sources:
                items = await _fetch_web(client, web_sources, name, cfg)
                all_items.extend(items)

    # 媒体关键词过滤
    if hotspot_items:
        media_items = _filter_media_items(hotspot_items, cfg)
        all_items.extend(media_items)

    # 写入
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    logger.info(f"[Competitor] Total: {len(all_items)} items -> {output_path}")
    return all_items
