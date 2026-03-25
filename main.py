"""OSL Growth Hotspot Agent — 主入口

用法：
  python main.py fetch          # 立即抓取 + 处理（一次性）
  python main.py dashboard      # 只启动看板
  python main.py                # 调度器模式：每日 09:00 自动执行 + 启动看板
"""
import asyncio
import json
import logging
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")

DATA_DIR = Path(__file__).parent / "data"

_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_date_dir(d: Path) -> bool:
    return d.is_dir() and bool(_DATE_RE.match(d.name)) and (d / "result.json").exists()


def raw_path(date_str: str) -> Path:
    return DATA_DIR / "raw" / date_str / "items.json"


def competitor_path(date_str: str) -> Path:
    return DATA_DIR / "competitors" / date_str / "items.json"


def processed_path(date_str: str) -> Path:
    return DATA_DIR / "processed" / date_str / "result.md"


async def run_fetch_and_process():
    """抓取所有信源（主流程 + 竞品）+ 调用 Manus 处理"""
    today = date.today().isoformat()
    out_path = raw_path(today)
    comp_path = competitor_path(today)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== 开始抓取 {today} ===")

    from fetcher import rss as rss_fetcher
    from fetcher import twitter as twitter_fetcher
    from fetcher import telegram as telegram_fetcher
    from fetcher import competitor as competitor_fetcher

    # 并发抓取：主流程（RSS + Twitter）+ 竞品官方渠道
    (rss_items, twitter_items), comp_items = await asyncio.gather(
        asyncio.gather(
            rss_fetcher.fetch_all(out_path),
            twitter_fetcher.fetch_all(out_path),
        ),
        competitor_fetcher.fetch_all(comp_path),
    )

    # Telegram 串行（需要交互式登录）
    telegram_items = await telegram_fetcher.fetch_all(out_path)

    # 媒体关键词过滤：从主流程热点中筛选竞品相关报道，追加到竞品数据
    hotspot_items = rss_items + twitter_items + telegram_items
    competitor_fetcher.append_media_items(comp_path, hotspot_items)

    total = len(hotspot_items)
    logger.info(f"抓取完成：RSS {len(rss_items)} + Twitter {len(twitter_items)} + Telegram {len(telegram_items)} = {total} 条")
    logger.info(f"竞品抓取完成：{len(comp_items)} 条")

    if total == 0:
        logger.warning("未抓取到任何条目，跳过 Manus 处理")
        return

    logger.info("=== 开始 Manus 处理 ===")
    from processor import manus
    try:
        result = await manus.process(out_path, processed_path(today), today)
        logger.info(f"处理完成，结果已写入 {processed_path(today)}")
    except EnvironmentError as e:
        logger.warning(f"跳过 Manus 处理：{e}")
        logger.info(f"原始数据已保存至 {out_path}，配置好 MANUS_API_KEY 后重新运行即可")

    # 竞品 Gemini 提取
    if comp_path.exists():
        logger.info("=== 开始竞品 Gemini 提取 ===")
        try:
            from processor import competitor_extractor
            with open(comp_path, "r", encoding="utf-8") as f:
                comp_items = json.load(f)
            if comp_items:
                comp_result = await competitor_extractor.extract(comp_items, today)
                # 写入结构化结果
                result_path = comp_path.parent / "result.json"
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump(comp_result, f, ensure_ascii=False, indent=2)
                logger.info(f"竞品提取完成：{result_path}")
            else:
                logger.info("竞品数据为空，跳过 Gemini 提取")
        except Exception as e:
            logger.warning(f"竞品提取失败：{e}")

    # 生成静态索引文件（供 Vercel 静态模式使用）
    _generate_index_files()


def _generate_index_files():
    """生成 dates.json + latest.json 索引文件（供 Vercel 静态模式）"""
    for subdir in ["processed", "competitors"]:
        target_dir = DATA_DIR / subdir
        if not target_dir.exists():
            continue
        dates = sorted(
            [d.name for d in target_dir.iterdir() if _is_date_dir(d)],
            reverse=True,
        )
        if not dates:
            continue
        # dates.json
        with open(target_dir / "dates.json", "w", encoding="utf-8") as f:
            json.dump(dates, f, ensure_ascii=False, indent=2)
        # latest.json — 复制最新日期的 result.json
        latest_src = target_dir / dates[0] / "result.json"
        shutil.copy2(latest_src, target_dir / "latest.json")
        logger.info(f"[index] {subdir}: dates.json ({len(dates)} 条) + latest.json → {dates[0]}")


def run_dashboard():
    """启动 FastAPI 看板"""
    import uvicorn
    port = int(os.environ.get("DASHBOARD_PORT", "8080"))
    logger.info(f"启动看板：http://localhost:{port}")
    uvicorn.run(
        "dashboard.app:app",
        host="0.0.0.0",
        port=port,
        reload=False,
        log_level="warning",
    )


def run_scheduler():
    """调度模式：每日 09:00 执行抓取+处理，同时启动看板"""
    from apscheduler.schedulers.background import BackgroundScheduler

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: asyncio.run(run_fetch_and_process()),
        trigger="cron",
        hour=9,
        minute=0,
        timezone="Asia/Shanghai",
        id="daily_fetch",
        name="每日热点抓取",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("调度器已启动，每日 09:00 自动抓取")

    # 阻塞在看板
    run_dashboard()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scheduler"

    if cmd == "fetch":
        asyncio.run(run_fetch_and_process())
    elif cmd == "dashboard":
        run_dashboard()
    else:
        run_scheduler()
