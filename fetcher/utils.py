"""Fetcher 共享工具"""
import json
from pathlib import Path


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
