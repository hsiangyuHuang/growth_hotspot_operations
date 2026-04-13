"""FastAPI 看板后端 — 纯 markdown 展示"""
import json
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DATA_DIR = Path(__file__).parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
COMPETITORS_DIR = DATA_DIR / "competitors"
SENTIMENT_DIR = DATA_DIR / "sentiment"
CONFIG_DIR = Path(__file__).parent.parent / "config"

app = FastAPI(title="OSL Growth Hotspot Dashboard")

# 日期目录格式：YYYY-MM-DD
_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_date_dir(d: Path) -> bool:
    return d.is_dir() and bool(_DATE_RE.match(d.name)) and (d / "result.json").exists()

# 静态文件
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def _load_result(date_str: str) -> Optional[dict]:
    """读取指定日期的 result.json。"""
    json_path = PROCESSED_DIR / date_str / "result.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)

    return None


def _load_competitor_result(date_str: str) -> Optional[dict]:
    """读取指定日期的竞品 result.json。"""
    json_path = COMPETITORS_DIR / date_str / "result.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


@app.get("/", response_class=HTMLResponse)
async def index():
    template_path = Path(__file__).parent / "templates" / "index.html"
    return HTMLResponse(template_path.read_text(encoding="utf-8"))


@app.get("/api/today")
async def get_today():
    today = date.today().isoformat()
    result = _load_result(today)
    if not result:
        return JSONResponse({"run_date": today, "header_markdown": "", "cards": []})
    return result


@app.get("/api/history")
async def get_history(date: Optional[str] = Query(None)):
    if not date:
        raise HTTPException(status_code=400, detail="date parameter required (YYYY-MM-DD)")
    result = _load_result(date)
    if not result:
        raise HTTPException(status_code=404, detail=f"No data for {date}")
    return result


@app.get("/api/dates")
async def get_dates():
    if not PROCESSED_DIR.exists():
        return {"dates": []}
    date_dirs = sorted(
        [d for d in PROCESSED_DIR.iterdir() if _is_date_dir(d)],
        key=lambda d: d.name,
        reverse=True,
    )
    result = []
    for d in date_dirs:
        count = 0
        try:
            with open(d / "result.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            count = len(data.get("cards", []))
        except Exception:
            pass
        result.append({"date": d.name, "count": count})
    return {"dates": result}


# ── 竞品 API ─────────────────────────────────────────

@app.get("/api/competitors/today")
async def get_competitors_today():
    # 优先读 7 日 pool
    pool_path = COMPETITORS_DIR / "pool.json"
    if pool_path.exists():
        with open(pool_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # fallback: 单日数据
    today = date.today().isoformat()
    result = _load_competitor_result(today)
    if not result:
        if COMPETITORS_DIR.exists():
            dates = sorted(
                [d.name for d in COMPETITORS_DIR.iterdir() if _is_date_dir(d)],
                reverse=True,
            )
            if dates:
                result = _load_competitor_result(dates[0])
    if not result:
        return JSONResponse({"run_date": today, "competitors": []})
    return result


@app.get("/api/competitors/history")
async def get_competitors_history(date: Optional[str] = Query(None)):
    if not date:
        raise HTTPException(status_code=400, detail="date parameter required")
    result = _load_competitor_result(date)
    if not result:
        raise HTTPException(status_code=404, detail=f"No competitor data for {date}")
    return result


@app.get("/api/competitors/dates")
async def get_competitors_dates():
    if not COMPETITORS_DIR.exists():
        return {"dates": []}
    dates = sorted(
        [d.name for d in COMPETITORS_DIR.iterdir() if _is_date_dir(d)],
        reverse=True,
    )
    return {"dates": dates}


# ── 舆情 API ──────────────────────────────────────────────────

def _load_sentiment_result(date_str: str) -> dict | None:
    json_path = SENTIMENT_DIR / date_str / "result.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


@app.get("/api/sentiment/today")
async def get_sentiment_today():
    # 优先读 7 日 pool
    pool_path = SENTIMENT_DIR / "pool.json"
    if pool_path.exists():
        with open(pool_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # fallback: 单日数据
    today = date.today().isoformat()
    result = _load_sentiment_result(today)
    if not result and SENTIMENT_DIR.exists():
        dates = sorted(
            [d.name for d in SENTIMENT_DIR.iterdir() if _is_date_dir(d)],
            reverse=True,
        )
        if dates:
            result = _load_sentiment_result(dates[0])
    if not result:
        return JSONResponse({"run_date": today, "total_raw": 0, "items": []})
    return result


@app.get("/api/sentiment/history")
async def get_sentiment_history(date: Optional[str] = Query(None)):
    if not date:
        raise HTTPException(status_code=400, detail="date parameter required (YYYY-MM-DD)")
    result = _load_sentiment_result(date)
    if not result:
        raise HTTPException(status_code=404, detail=f"No sentiment data for {date}")
    return result


@app.get("/api/sentiment/dates")
async def get_sentiment_dates():
    if not SENTIMENT_DIR.exists():
        return {"dates": []}
    dates = sorted(
        [d.name for d in SENTIMENT_DIR.iterdir() if _is_date_dir(d)],
        reverse=True,
    )
    return {"dates": dates}


# ── 信源 API ──────────────────────────────────────────────────

@app.get("/api/sources")
async def get_sources():
    import yaml
    result = {"rss": [], "twitter": {"accounts": []}, "competitors": []}
    sources_path = CONFIG_DIR / "sources.yaml"
    if sources_path.exists():
        with open(sources_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        result["rss"] = data.get("rss", [])
        result["twitter"] = data.get("twitter", {})
    competitors_path = CONFIG_DIR / "competitors.yaml"
    if competitors_path.exists():
        with open(competitors_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        result["competitors"] = data.get("competitors", [])
    return result
