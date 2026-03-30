"""Fetcher 共享工具"""
import asyncio
import json
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


def append_items(path: Path, new_items: list[dict]):
    """将新条目追加写入 JSON 文件（已存在则合并）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            existing = json.load(f)
    existing_ids = {item["id"] for item in existing}
    deduped = [item for item in new_items if item["id"] not in existing_ids]
    existing.extend(deduped)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)


async def retry_get(client: httpx.AsyncClient, url: str, *,
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
