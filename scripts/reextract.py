"""Re-run Gemini extractor on recent data with updated prompts."""
import os, sys, json, shutil, time
from pathlib import Path

# Clear proxy env vars that block API calls
for k in ['http_proxy','https_proxy','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY']:
    os.environ.pop(k, None)

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from processor.extractor import extract

PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"
DASHBOARD = Path(__file__).resolve().parent.parent / "dashboard" / "data"

all_dates = sorted(d.name for d in PROCESSED.iterdir() if d.is_dir() and (d / "result.md").exists())[-7:]
# Skip already-processed dates
done = {'2026-03-17','2026-03-18','2026-03-19','2026-03-20'}
dates = [d for d in all_dates if d not in done]
print(f"Dates to process: {dates}", flush=True)

for date_str in dates:
    md_path = PROCESSED / date_str / "result.md"
    json_path = PROCESSED / date_str / "result.json"
    dash_path = DASHBOARD / f"{date_str}.json"
    md = md_path.read_text(encoding="utf-8")
    print(f"\n[{date_str}] {len(md)} chars ...", end="", flush=True)
    try:
        result = extract(md, date_str)
        n = len(result.get("cards", []))
        names = [s["name"] for c in result["cards"][:2] for s in c.get("sources", [])[:2]]
        print(f" OK: {n} cards, sources={names}", flush=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        shutil.copy2(json_path, dash_path)
    except Exception as e:
        print(f" ERROR: {e}", flush=True)
    time.sleep(3)

latest = dates[-1]
shutil.copy2(DASHBOARD / f"{latest}.json", DASHBOARD / "latest.json")
all_dates = sorted(d.stem for d in DASHBOARD.glob("2*.json"))
with open(DASHBOARD / "dates.json", "w") as f:
    json.dump(all_dates, f)
print(f"\nDone. latest={latest}, {len(all_dates)} dates total", flush=True)
