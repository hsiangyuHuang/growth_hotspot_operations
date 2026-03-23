"""通用 JSON API fetcher — 配置驱动，支持任意交易所公告 API

每个 API 源的端点、参数、字段映射全部在 config/sources.yaml 的 api_sources 段定义，
新增交易所 API 只需加 YAML 配置，不需改代码。
"""
import hashlib
import logging
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


def _make_id(value: str) -> str:
    return hashlib.md5(value.encode()).hexdigest()[:8]


def _extract_path(data, path: str) -> list:
    """简易 JSONPath: 支持 'data.catalogs[].articles[]' 格式

    遍历 path 中用 '.' 分隔的 key，遇到 '[]' 后缀时 flatten list。
    """
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


def _parse_date(value, fmt: str) -> datetime | None:
    """支持 'timestamp_ms'、'timestamp_s'、'iso' 三种格式"""
    try:
        if fmt == "timestamp_ms":
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
        elif fmt == "timestamp_s":
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        else:  # iso
            return datetime.fromisoformat(str(value))
    except Exception:
        return None


async def _fetch_source(client: httpx.AsyncClient, source: dict) -> list[dict]:
    """根据配置抓取单个 API 源"""
    name = source["name"]
    cfg = _load_config()
    lookback = cfg.get("lookback_hours", 24)
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=lookback)
    now = datetime.now(tz=timezone.utc)

    try:
        resp = await client.get(
            source["url"],
            params=source.get("params", {}),
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.warning(f"[API] Failed to fetch {name}: {e}")
        return []

    articles = _extract_path(data, source["articles_path"])
    items = []

    for article in articles:
        pub_date = _parse_date(
            article.get(source["date_field"]),
            source.get("date_format", "iso"),
        )
        if pub_date and pub_date < cutoff:
            continue

        id_val = str(article.get(source["id_field"], ""))
        if not id_val:
            continue

        title = article.get(source["title_field"], "")
        content_field = source.get("content_field", source["title_field"])
        content = article.get(content_field, title)

        try:
            url = source["url_template"].format(**article)
        except KeyError:
            url = source["url"]

        items.append({
            "id": _make_id(id_val),
            "source": name,
            "title": title,
            "content": content,
            "url": url,
            "published_at": pub_date.isoformat() if pub_date else now.isoformat(),
            "fetched_at": now.isoformat(),
            "lang": source.get("lang", "en"),
            "processed": False,
        })

    logger.info(f"[API] {name}: {len(items)} items")
    return items


async def fetch_all(output_path: Path) -> list[dict]:
    """遍历 config 中所有 api_sources，逐个抓取"""
    sources = _load_config().get("api_sources", [])
    if not sources:
        logger.info("[API] No api_sources configured, skipping")
        return []

    all_items = []
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (compatible; OSL-Bot/1.0)"},
        follow_redirects=True,
    ) as client:
        for source in sources:
            items = await _fetch_source(client, source)
            all_items.extend(items)

    append_items(output_path, all_items)
    logger.info(f"[API] Total: {len(all_items)} items written to {output_path}")
    return all_items
