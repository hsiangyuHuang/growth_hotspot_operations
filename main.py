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
from datetime import date, datetime, timezone, timedelta
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
POOL_WINDOW = 30  # 滚动信息池窗口天数

_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_date_dir(d: Path) -> bool:
    return d.is_dir() and bool(_DATE_RE.match(d.name)) and (d / "result.json").exists()


def _is_sentiment_date_dir(d: Path) -> bool:
    return d.is_dir() and bool(_DATE_RE.match(d.name)) and (d / "items.json").exists()


def raw_path(date_str: str) -> Path:
    return DATA_DIR / "raw" / date_str / "items.json"


def competitor_path(date_str: str) -> Path:
    return DATA_DIR / "competitors" / date_str / "items.json"


def sentiment_path(date_str: str) -> Path:
    return DATA_DIR / "sentiment" / date_str / "items.json"


def processed_path(date_str: str) -> Path:
    return DATA_DIR / "processed" / date_str / "result.md"


def _collect_pool_items(subdir: str, window: int = POOL_WINDOW) -> tuple[list[dict], str, str]:
    """合并近 N 天的 items.json，代码层 URL 去重，返回 (items, date_from, date_to)。"""
    target_dir = DATA_DIR / subdir
    if not target_dir.exists():
        return [], "", ""
    date_dirs = sorted(
        [d.name for d in target_dir.iterdir()
         if d.is_dir() and _DATE_RE.match(d.name) and (d / "items.json").exists()],
        reverse=True,
    )[:window]

    if not date_dirs:
        return [], "", ""

    seen_urls: set[str] = set()
    merged: list[dict] = []
    for d in date_dirs:
        items_path = target_dir / d / "items.json"
        with open(items_path, "r", encoding="utf-8") as f:
            items = json.load(f)
        for item in items:
            url = item.get("url", "")
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            merged.append(item)

    return merged, date_dirs[-1], date_dirs[0]


def _generate_competitor_pool():
    """合并近 POOL_WINDOW 天的 result.json 生成 pool.json（纯合并去重，不调 LLM）。"""
    import yaml

    target_dir = DATA_DIR / "competitors"
    if not target_dir.exists():
        return

    date_dirs = sorted(
        [d.name for d in target_dir.iterdir() if _is_date_dir(d)],
        reverse=True,
    )[:POOL_WINDOW]

    if not date_dirs:
        logger.info("无竞品历史 result.json，跳过 Pool 生成")
        return

    # 收集所有竞品事件，按 (competitor, title) 去重
    comp_events: dict[str, list[dict]] = {}
    comp_meta: dict[str, dict] = {}
    seen_keys: set[str] = set()

    for d in date_dirs:
        result_path = target_dir / d / "result.json"
        with open(result_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for comp in data.get("competitors", []):
            name = comp.get("name", "")
            if not name:
                continue
            if name not in comp_meta:
                comp_meta[name] = {
                    "region": comp.get("region", "HK"),
                    "logo": comp.get("logo", ""),
                    "summary": comp.get("summary", ""),
                }
            comp_events.setdefault(name, [])
            for ev in comp.get("events", []):
                key = f"{name}|{ev.get('title', '')}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                comp_events[name].append(ev)

    # 按配置顺序组装完整列表
    config_path = Path(__file__).parent / "config" / "competitors.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    full_list = []
    for comp_cfg in cfg.get("competitors", []):
        name = comp_cfg["name"]
        meta = comp_meta.get(name, {})
        events = comp_events.get(name, [])
        events.sort(key=lambda e: e.get("date", ""), reverse=True)
        full_list.append({
            "name": name,
            "region": meta.get("region", comp_cfg.get("region", "HK")),
            "logo": meta.get("logo", comp_cfg.get("logo", "")),
            "summary": meta.get("summary", f"近期未监测到 {name} 的公开动态"),
            "events": events,
        })

    pool_result = {
        "date_range": {"from": date_dirs[-1], "to": date_dirs[0]},
        "competitors": full_list,
    }

    pool_path = target_dir / "pool.json"
    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(pool_result, f, ensure_ascii=False, indent=2)

    total_events = sum(len(c["events"]) for c in full_list)
    logger.info(f"竞品 Pool 生成：合并 {len(date_dirs)} 天 result.json，{total_events} 事件（去重后）→ {pool_path}")


async def run_fetch_and_process():
    """抓取所有信源（主流程 + 竞品）+ 调用 Manus 处理"""
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    out_path = raw_path(today)
    comp_path = competitor_path(today)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== 开始抓取 {today} ===")

    from fetcher import rss as rss_fetcher
    from fetcher import twitter as twitter_fetcher
    from fetcher import telegram as telegram_fetcher
    from fetcher import competitor as competitor_fetcher
    from fetcher import sentiment as sentiment_fetcher

    # 并发抓取：主流程（RSS + Twitter）+ 竞品官方渠道 + 舆情监控
    sent_path = sentiment_path(today)
    (rss_items, twitter_items), comp_items, sent_items = await asyncio.gather(
        asyncio.gather(
            rss_fetcher.fetch_all(out_path),
            twitter_fetcher.fetch_all(out_path),
        ),
        competitor_fetcher.fetch_all(comp_path),
        sentiment_fetcher.fetch_all(sent_path),
    )

    # Telegram 串行（需要交互式登录）
    telegram_items = await telegram_fetcher.fetch_all(out_path)

    # 媒体关键词过滤：从主流程热点中筛选竞品相关报道，追加到竞品数据
    hotspot_items = rss_items + twitter_items + telegram_items
    competitor_fetcher.append_media_items(comp_path, hotspot_items)

    total = len(hotspot_items)
    logger.info(f"抓取完成：RSS {len(rss_items)} + Twitter {len(twitter_items)} + Telegram {len(telegram_items)} = {total} 条")
    logger.info(f"竞品抓取完成：{len(comp_items)} 条")
    logger.info(f"舆情抓取完成：{len(sent_items)} 条")

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

    # 舆情 Gemini 提取
    if sent_path.exists():
        logger.info("=== 开始舆情 Gemini 提取 ===")
        try:
            from processor import sentiment_extractor
            with open(sent_path, "r", encoding="utf-8") as f:
                sent_raw = json.load(f)
            if sent_raw:
                sent_result = await sentiment_extractor.extract(sent_raw, today)
                result_path = sent_path.parent / "result.json"
                with open(result_path, "w", encoding="utf-8") as f:
                    json.dump(sent_result, f, ensure_ascii=False, indent=2)
                logger.info(f"舆情提取完成：{result_path}")
            else:
                logger.info("舆情数据为空，跳过 Gemini 提取")
        except Exception as e:
            logger.warning(f"舆情提取失败：{e}")

    # ── 竞品 30 日 Pool（合并 result.json，不调 LLM）──
    logger.info("=== 生成竞品 30 日 Pool ===")
    try:
        _generate_competitor_pool()
    except Exception as e:
        logger.warning(f"竞品 Pool 生成失败：{e}")

    # ── 舆情 7 日 Pool 提取 ──
    logger.info("=== 生成舆情 7 日 Pool ===")
    try:
        sent_pool_items, sent_from, sent_to = _collect_pool_items("sentiment")
        if sent_pool_items:
            from processor import sentiment_extractor
            pool_result = await sentiment_extractor.extract(sent_pool_items, today)
            pool_result["date_range"] = {"from": sent_from, "to": sent_to}
            pool_result.pop("run_date", None)
            pool_path = DATA_DIR / "sentiment" / "pool.json"
            with open(pool_path, "w", encoding="utf-8") as f:
                json.dump(pool_result, f, ensure_ascii=False, indent=2)
            logger.info(f"舆情 Pool 生成：{len(sent_pool_items)} items（去重后）→ {pool_path}")
        else:
            logger.info("无舆情历史数据，跳过 Pool 生成")
    except Exception as e:
        logger.warning(f"舆情 Pool 生成失败：{e}")

    # 生成静态索引文件（供 Vercel 静态模式使用）
    _generate_index_files()

    # ── 飞书推送 ──
    try:
        from notifier.lark import push_hotspot_briefing
        latest_path = DATA_DIR / "processed" / "latest.json"
        if latest_path.exists():
            with open(latest_path, "r", encoding="utf-8") as f:
                latest = json.load(f)
            cards = latest.get("cards", [])
            if cards:
                await push_hotspot_briefing(cards, today)
    except Exception as e:
        logger.warning(f"飞书推送异常：{e}")


def _generate_index_files():
    """生成 dates.json + latest.json 索引文件（供 Vercel 静态模式）"""
    for subdir in ["processed", "competitors", "sentiment"]:
        target_dir = DATA_DIR / subdir
        if not target_dir.exists():
            continue
        dates = sorted(
            [d.name for d in target_dir.iterdir() if _is_date_dir(d)],
            reverse=True,
        )
        if not dates:
            continue
        # dates.json — processed 包含每日卡片数量，其他保持纯日期列表
        if subdir == "processed":
            dates_with_count = []
            for d in dates:
                count = 0
                result_path = target_dir / d / "result.json"
                try:
                    with open(result_path, "r", encoding="utf-8") as rf:
                        result_data = json.load(rf)
                    count = len(result_data.get("cards", []))
                except Exception:
                    pass
                dates_with_count.append({"date": d, "count": count})
            with open(target_dir / "dates.json", "w", encoding="utf-8") as f:
                json.dump(dates_with_count, f, ensure_ascii=False, indent=2)
        else:
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
