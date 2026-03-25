"""竞品多渠道抓取：Twitter + API + RSS + 网页解析 + 媒体关键词过滤

数据流：
  competitors.yaml → 按竞品并行抓取 → items.json
  主流程 hotspot_items → 媒体关键词过滤 → 追加到 items.json
"""
import asyncio
import hashlib
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import httpx
import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent / "config" / "competitors.yaml"
MAX_RETRIES = 3


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _make_id(raw: str) -> str:
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def _strip_html(text: str) -> str:
    import html as html_mod
    cleaned = re.sub(r"<[^>]+>", "", text or "")
    return html_mod.unescape(cleaned).strip()


# ── 通用重试请求 ──────────────────────────────────────────────

async def _retry_request(client: httpx.AsyncClient, url: str, *,
                         max_retries: int = MAX_RETRIES,
                         timeout: float = 15.0,
                         label: str = "",
                         **kwargs) -> httpx.Response | None:
    """带重试、429 退避、5xx 重试的通用 HTTP GET。"""
    for attempt in range(max_retries):
        try:
            resp = await client.get(url, timeout=timeout, **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5 * (attempt + 1)))
                logger.info(f"[{label}] 429 rate limited, retry {attempt+1}/{max_retries} in {wait}s")
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 500 and attempt < max_retries - 1:
                logger.info(f"[{label}] {resp.status_code}, retry {attempt+1}/{max_retries}")
                await asyncio.sleep(2 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
            if attempt < max_retries - 1:
                logger.info(f"[{label}] {type(e).__name__}, retry {attempt+1}/{max_retries}")
                await asyncio.sleep(2 * (attempt + 1))
                continue
            logger.warning(f"[{label}] {url} failed after {max_retries} retries: {e}")
            return None
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 * (attempt + 1))
                continue
            logger.warning(f"[{label}] {url} failed: {e}")
            return None
    return None


# ── Twitter 抓取（带重试） ───────────────────────────────────

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
        resp = await _retry_request(
            client, base_url,
            params={"userName": handle, "includeReplies": "false"},
            headers=headers, label=f"Competitor:Twitter:@{handle}",
        )
        if resp is None:
            continue

        try:
            data = resp.json()
        except Exception:
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


# ── API 抓取（交易所公告） ───────────────────────────────────

async def _fetch_api(client: httpx.AsyncClient, api_sources: list[dict],
                     competitor_name: str, cfg: dict) -> list[dict]:
    lookback = cfg.get("lookback_hours", 24)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)
    items = []

    for src in api_sources:
        url = src.get("url", "")
        resp = await _retry_request(
            client, url, params=src.get("params", {}),
            label=f"Competitor:API:{competitor_name}",
        )
        if resp is None:
            continue

        try:
            data = resp.json()
        except Exception as e:
            logger.warning(f"[Competitor:API] {competitor_name} JSON parse failed: {e}")
            continue

        # 简易 JSONPath 提取
        articles = _extract_path(data, src.get("articles_path", ""))

        for article in articles:
            pub_date = _parse_api_date(
                article.get(src.get("date_field", "")),
                src.get("date_format", "iso"),
            )
            if pub_date and pub_date < cutoff:
                continue

            id_val = str(article.get(src.get("id_field", "id"), ""))
            if not id_val:
                continue

            title = str(article.get(src.get("title_field", "title"), ""))
            try:
                article_url = src["url_template"].format(**article)
            except (KeyError, IndexError):
                article_url = url

            items.append({
                "id": _make_id(f"api:{competitor_name}:{id_val}"),
                "competitor": competitor_name,
                "source": f"api:{competitor_name}",
                "source_type": "api",
                "title": title[:200],
                "content": title[:cfg.get("content_limit", 500)],
                "url": article_url,
                "published_at": pub_date.isoformat() if pub_date else now.isoformat(),
                "fetched_at": now.isoformat(),
            })

    logger.info(f"[Competitor:API] {competitor_name}: {len(items)} items")
    return items


def _extract_path(data, path: str) -> list:
    """简易 JSONPath: 支持 'data.catalogs[].articles[]' 格式"""
    if not path:
        return [data] if isinstance(data, dict) else data if isinstance(data, list) else []
    current = [data]
    for segment in path.split("."):
        flatten = segment.endswith("[]")
        key = segment.rstrip("[]")
        next_level = []
        for item in current:
            val = item.get(key) if isinstance(item, dict) else None
            if val is None:
                continue
            if flatten and isinstance(val, list):
                next_level.extend(val)
            else:
                next_level.append(val)
        current = next_level
    return current


def _parse_api_date(value, fmt: str) -> datetime | None:
    try:
        if fmt == "timestamp_ms":
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        elif fmt == "timestamp_s":
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        else:
            return datetime.fromisoformat(str(value))
    except Exception:
        return None


# ── RSS 抓取 ─────────────────────────────────────────────────

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
        resp = await _retry_request(
            client, url, label=f"Competitor:RSS:{name}",
        )
        if resp is None:
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


# ── 网页抓取（支持 per-site 选择器 + 正则模式） ──────────────

async def _fetch_web(client: httpx.AsyncClient, web_sources: list[dict],
                     competitor_name: str, cfg: dict) -> list[dict]:
    content_limit = cfg.get("content_limit", 500)
    now = datetime.now(tz=timezone.utc)
    items = []

    for src in web_sources:
        url = src.get("url", "")
        resp = await _retry_request(
            client, url, timeout=20.0,
            label=f"Competitor:Web:{competitor_name}",
        )
        if resp is None:
            continue
        html = resp.text

        try:
            from bs4 import BeautifulSoup

            link_regex = src.get("link_regex")
            seen = set()

            if link_regex:
                # 正则模式：从原始 HTML 中提取链接（适用于 Next.js SPA 等）
                matches = re.findall(link_regex, html)
                for path in dict.fromkeys(matches):  # 去重保序
                    full_url = urljoin(url, path)
                    if full_url in seen:
                        continue
                    seen.add(full_url)

                    # 从路径末段生成可读标题
                    slug = path.rstrip("/").rsplit("/", 1)[-1]
                    title = slug.replace("-", " ").strip() or slug

                    items.append({
                        "id": _make_id(full_url),
                        "competitor": competitor_name,
                        "source": f"web:{competitor_name}",
                        "source_type": "web",
                        "title": title[:200],
                        "content": title[:content_limit],
                        "url": full_url,
                        "published_at": now.isoformat(),
                        "fetched_at": now.isoformat(),
                    })
                    if len(items) >= 20:
                        break
            else:
                # CSS 选择器模式（默认）
                soup = BeautifulSoup(html, "html.parser")

                custom_selectors = src.get("selectors", [])
                default_selectors = [
                    "article a", ".article a", ".post a", ".announcement a",
                    "a[href*='announcement']", "a[href*='blog']", "a[href*='news']",
                    "h2 a", "h3 a", ".list-item a", ".card a",
                ]
                selectors = custom_selectors if custom_selectors else default_selectors

                anchors = []
                for selector in selectors:
                    anchors.extend(soup.select(selector))

                for a in anchors:
                    href = a.get("href", "")
                    if not href or href in seen or href.startswith("#") or href.startswith("javascript:"):
                        continue
                    seen.add(href)

                    title = a.get_text(strip=True)
                    if not title or len(title) < 5:
                        continue
                    if not href.startswith("http"):
                        href = urljoin(url, href)

                    # 从父容器提取更丰富的 content
                    content = title
                    parent = a.find_parent(["article", "div", "li"])
                    if parent:
                        parent_text = parent.get_text(strip=True, separator=" ")
                        if len(parent_text) > len(title) + 10:
                            content = parent_text

                    # 尝试提取日期（如果配置了 date_selector）
                    pub_at = now.isoformat()
                    date_sel = src.get("date_selector")
                    if date_sel:
                        date_parent = a.find_parent()
                        if date_parent:
                            date_el = date_parent.select_one(date_sel)
                            if date_el:
                                pub_at = date_el.get_text(strip=True)

                    items.append({
                        "id": _make_id(href),
                        "competitor": competitor_name,
                        "source": f"web:{competitor_name}",
                        "source_type": "web",
                        "title": title[:200],
                        "content": content[:content_limit],
                        "url": href,
                        "published_at": pub_at,
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


# ── 媒体关键词过滤（正则词边界匹配） ────────────────────────

def filter_media_items(hotspot_items: list[dict], cfg: dict) -> list[dict]:
    """从主流程热点 items 中筛选竞品相关的媒体报道。
    改进：正则词边界匹配 + 允许一条 item 匹配多个竞品。
    """
    media_keywords = cfg.get("media_keywords", {})
    now = datetime.now(tz=timezone.utc)
    items = []

    # 预编译正则
    compiled = {}
    for comp_name, keywords in media_keywords.items():
        patterns = []
        for kw in keywords:
            try:
                patterns.append(re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE))
            except re.error:
                patterns.append(re.compile(re.escape(kw), re.IGNORECASE))
        compiled[comp_name] = patterns

    for item in hotspot_items:
        text = f"{item.get('title', '')} {item.get('content', '')}"
        # 一条 item 可以匹配多个竞品
        for comp_name, patterns in compiled.items():
            for pattern in patterns:
                if pattern.search(text):
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
                    break  # 同一竞品只匹配一次，但不阻止其他竞品匹配

    logger.info(f"[Competitor:Media] Found {len(items)} media items about competitors")
    return items


# ── 单个竞品抓取（聚合所有信源） ─────────────────────────────

async def _fetch_one_competitor(client: httpx.AsyncClient, comp: dict, cfg: dict) -> list[dict]:
    """抓取单个竞品的所有信源，每个渠道独立 try-except"""
    name = comp["name"]
    items = []

    source_types = [
        ("twitter", _fetch_twitter, "twitter"),
        ("api", _fetch_api, "api"),
        ("rss", _fetch_rss, "rss"),
        ("web", _fetch_web, "web"),
    ]

    for source_type, fetch_fn, key in source_types:
        sources = comp.get(key, [])
        if not sources:
            continue
        try:
            result = await fetch_fn(client, sources, name, cfg)
            items.extend(result)
        except Exception as e:
            logger.warning(f"[Competitor:{source_type}] {name} uncaught error: {e}")

    return items


# ── 主入口 ───────────────────────────────────────────────────

async def fetch_all(output_path: Path) -> list[dict]:
    """抓取所有竞品数据，写入 output_path。

    按竞品并行抓取（同一竞品内的 Twitter 账号串行避免 429）。
    """
    cfg = _load_config()
    competitors = cfg.get("competitors", [])
    all_items = []

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; OSL-Bot/1.0)"},
        follow_redirects=True,
    ) as client:
        # 按竞品并行抓取
        tasks = [_fetch_one_competitor(client, comp, cfg) for comp in competitors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.warning(f"[Competitor] {competitors[i]['name']} failed: {result}")
            else:
                all_items.extend(result)

    # 去重写入（ID 去重 + URL 去重）
    _dedup_and_write(output_path, all_items)

    # 抓取统计
    type_counts = Counter(item["source_type"] for item in all_items)
    logger.info(f"[Competitor] Stats by source: {dict(type_counts)}")
    logger.info(f"[Competitor] Total: {len(all_items)} new items -> {output_path}")
    return all_items


def append_media_items(output_path: Path, hotspot_items: list[dict]) -> list[dict]:
    """从主流程热点中筛选竞品相关报道，去重后追加到 output_path。

    返回实际追加的媒体 items。
    """
    if not hotspot_items:
        return []
    cfg = _load_config()
    media_items = filter_media_items(hotspot_items, cfg)
    if not media_items:
        return []
    count = _dedup_and_write(output_path, media_items)
    logger.info(f"[Competitor:Media] {count} 条竞品相关报道追加到 {output_path}")
    return media_items


def _dedup_and_write(output_path: Path, new_items: list[dict]) -> int:
    """ID + URL 双重去重后写入文件，返回实际新增条数。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing_ids = {item["id"] for item in existing}
    deduped = [item for item in new_items if item["id"] not in existing_ids]
    existing.extend(deduped)

    # URL 级去重
    seen_urls: set[str] = set()
    final_items = []
    for item in existing:
        url = item.get("url", "")
        if url and url in seen_urls:
            continue
        if url:
            seen_urls.add(url)
        final_items.append(item)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_items, f, ensure_ascii=False, indent=2)

    return len(deduped)
