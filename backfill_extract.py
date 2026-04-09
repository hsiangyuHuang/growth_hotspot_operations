"""一次性脚本：对缺少 result.json 的历史日期重新跑 Gemini 提取。

用法：
  1. 先从 git 恢复 result.md：
     git checkout origin/main -- data/processed/2026-03-26 data/processed/2026-03-27 ...
  2. 运行本脚本：
     .venv/bin/python backfill_extract.py
  3. 重建索引 + 提交推送
"""
import asyncio
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from processor.extractor import extract

DEFAULT_DATES = [
    "2026-03-26", "2026-03-27", "2026-03-28",
    "2026-03-29", "2026-03-30", "2026-03-31",
]
# 支持通过环境变量覆盖（CI workflow_dispatch 使用）
DATES = [
    d.strip() for d in os.environ.get("BACKFILL_DATES", "").split(",") if d.strip()
] or DEFAULT_DATES


def restore_from_git():
    """从 git 恢复缺失的 result.md 文件"""
    paths_to_restore = []
    for date in DATES:
        md_path = Path(f"data/processed/{date}/result.md")
        if not md_path.exists():
            paths_to_restore.append(f"data/processed/{date}")
    if paths_to_restore:
        print(f"[GIT]  Restoring {len(paths_to_restore)} date dirs from origin/main...")
        subprocess.run(
            ["git", "checkout", "origin/main", "--"] + paths_to_restore,
            check=True,
        )
        print(f"[GIT]  Restored: {', '.join(paths_to_restore)}")


def rebuild_index():
    """重建 dates.json + latest.json（复用 main.py 逻辑）"""
    from main import _generate_index_files
    _generate_index_files()
    print("[INDEX] dates.json + latest.json rebuilt")


async def main():
    # Step 1: 从 git 恢复 result.md
    restore_from_git()

    # Step 2: Gemini 提取生成 result.json
    for date in DATES:
        md_path = Path(f"data/processed/{date}/result.md")
        json_path = Path(f"data/processed/{date}/result.json")
        if json_path.exists():
            print(f"[SKIP] {date} already has result.json")
            continue
        if not md_path.exists():
            print(f"[SKIP] {date} missing result.md")
            continue
        print(f"[RUN]  {date} extracting...")
        markdown = md_path.read_text(encoding="utf-8")
        result = await extract(markdown, date)
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[DONE] {date} -> {len(result.get('cards', []))} cards")

    # Step 3: 重建索引
    rebuild_index()

if __name__ == "__main__":
    asyncio.run(main())
