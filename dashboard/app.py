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

app = FastAPI(title="OSL Growth Hotspot Dashboard")

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
        [
            d.name
            for d in PROCESSED_DIR.iterdir()
            if d.is_dir() and (d / "result.json").exists()
        ],
        reverse=True,
    )
    return {"dates": dates}
