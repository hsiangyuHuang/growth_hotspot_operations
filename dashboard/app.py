"""FastAPI 看板后端 — 纯 markdown 展示"""
import json
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

DATA_DIR = Path(__file__).parent.parent / "data"
PROCESSED_DIR = DATA_DIR / "processed"
COMPETITORS_DIR = DATA_DIR / "competitors"
SENTIMENT_DIR = DATA_DIR / "sentiment"
TRACKING_DIR = DATA_DIR / "tracking"
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
    dates = sorted(
        [d.name for d in PROCESSED_DIR.iterdir() if _is_date_dir(d)],
        reverse=True,
    )
    return {"dates": dates}


# ── 竞品 API ──────────────────────────────────────────────────

@app.get("/api/competitors/today")
async def get_competitors_today():
    today = date.today().isoformat()
    result = _load_competitor_result(today)
    if not result:
        # 回退到最近一天有数据的日期
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


# ── 追踪 API ──────────────────────────────────────────────────

def _is_tracking_date_dir(d: Path) -> bool:
    return d.is_dir() and bool(_DATE_RE.match(d.name)) and (d / "status.json").exists()


def _load_tracking(date_str: str) -> dict:
    p = TRACKING_DIR / date_str / "status.json"
    if p.exists():
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"run_date": date_str, "cards": {}}


def _save_tracking(date_str: str, data: dict):
    d = TRACKING_DIR / date_str
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "status.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.get("/api/tracking")
async def get_tracking(date: str = Query(...)):
    return _load_tracking(date)


@app.post("/api/tracking/accept")
async def accept_card(request: Request):
    from datetime import datetime as dt, timezone as tz, timedelta as td
    body = await request.json()
    date_str = body.get("date")
    card_id = body.get("card_id")
    user_id = body.get("user_id")
    if not all([date_str, card_id, user_id]):
        raise HTTPException(400, "date, card_id, user_id required")

    data = _load_tracking(date_str)
    card_data = data["cards"].get(card_id)

    if card_data is None:
        # 首次采纳，从 result.json 读取标题
        title = ""
        result = _load_result(date_str)
        if result:
            for card in result.get("cards", []):
                if card.get("id") == card_id:
                    title = card.get("title", "")
                    break
        card_data = {"title": title, "accepts": []}
        data["cards"][card_id] = card_data

    # 同一 user_id 幂等：已存在则跳过
    existing_ids = {a["user_id"] for a in card_data["accepts"]}
    if user_id in existing_ids:
        return {"ok": True, "already": True, "count": len(card_data["accepts"])}

    now = dt.now(tz(td(hours=8))).isoformat()
    card_data["accepts"].append({"user_id": user_id, "accepted_at": now})
    _save_tracking(date_str, data)
    return {"ok": True, "already": False, "count": len(card_data["accepts"])}


@app.get("/api/tracking/stats")
async def get_tracking_stats(days: int = Query(30)):
    from datetime import timedelta as td
    today = date.today()
    stats = {
        "period_days": days,
        "total_cards": 0,
        "total_accepted": 0,
        "by_priority": {},
        "by_category": {},
        "top_cards": [],
    }
    all_cards = []
    for i in range(days):
        d = (today - td(days=i)).isoformat()
        result = _load_result(d)
        if not result or not result.get("cards"):
            continue
        tracking = _load_tracking(d)
        for card in result["cards"]:
            cid = card.get("id", "")
            card_tracking = tracking["cards"].get(cid, {})
            accept_count = len(card_tracking.get("accepts", []))
            priority = card.get("priority", "P2")
            category = card.get("category", "未分类")
            stats["total_cards"] += 1
            if accept_count > 0:
                stats["total_accepted"] += 1
            bp = stats["by_priority"].setdefault(priority, {"total": 0, "accepted": 0})
            bp["total"] += 1
            if accept_count > 0:
                bp["accepted"] += 1
            bc = stats["by_category"].setdefault(category, {"total": 0, "accepted": 0})
            bc["total"] += 1
            if accept_count > 0:
                bc["accepted"] += 1
            all_cards.append({
                "date": d, "card_id": cid, "title": card.get("title", ""),
                "priority": priority, "accept_count": accept_count,
            })
    all_cards.sort(key=lambda x: x["accept_count"], reverse=True)
    stats["top_cards"] = all_cards[:20]
    return stats


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
