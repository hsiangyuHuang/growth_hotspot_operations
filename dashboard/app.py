"""FastAPI 看板后端 — 纯静态文件 serve"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT_DIR = Path(__file__).parent.parent

app = FastAPI(title="OSL Growth Hotspot Dashboard")

# 静态资源
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.mount("/data", StaticFiles(directory=str(ROOT_DIR / "data")), name="data")
app.mount("/config", StaticFiles(directory=str(ROOT_DIR / "config")), name="config")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))
