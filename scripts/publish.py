"""发布 pipeline 数据到 dashboard/data/ 供 Vercel 静态站使用"""
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = ROOT / "data" / "processed"
DASHBOARD_DATA = ROOT / "dashboard" / "data"


def publish(date_str: str, push: bool = True):
    src = PROCESSED_DIR / date_str / "result.json"
    if not src.exists():
        print(f"Error: {src} not found")
        sys.exit(1)

    DASHBOARD_DATA.mkdir(parents=True, exist_ok=True)

    # Copy to dated file + latest
    shutil.copy2(src, DASHBOARD_DATA / f"{date_str}.json")
    shutil.copy2(src, DASHBOARD_DATA / "latest.json")
    print(f"Copied {src} -> {date_str}.json + latest.json")

    # Update dates.json
    dates = sorted(
        [p.stem for p in DASHBOARD_DATA.glob("????-??-??.json")],
        reverse=True,
    )
    (DASHBOARD_DATA / "dates.json").write_text(
        json.dumps(dates, ensure_ascii=False, indent=2) + "\n"
    )
    print(f"Updated dates.json: {dates}")

    # Git commit & push
    subprocess.run(["git", "add", "dashboard/data/"], cwd=ROOT, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"data: publish {date_str}"],
        cwd=ROOT,
        check=True,
    )
    if push:
        subprocess.run(["git", "push"], cwd=ROOT, check=True)
        print("Pushed to remote.")
    else:
        print("Committed (skipped push).")


if __name__ == "__main__":
    args = sys.argv[1:]
    no_push = "--no-push" in args
    args = [a for a in args if a != "--no-push"]
    target_date = args[0] if args else date.today().isoformat()
    publish(target_date, push=not no_push)
