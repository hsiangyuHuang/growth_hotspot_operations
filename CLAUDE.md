你必须始终使用**简体中文**和我进行所有对话。

# OSL Growth Hotspot Agent

加密行业热点监控 + 竞品动态追踪 + 品牌舆情监控系统，每日自动抓取、AI 处理、生成结构化简报并展示在看板上。

## 运行命令

```bash
# 首次设置
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# 运行
.venv/bin/python main.py fetch      # 一次性抓取 + AI 处理
.venv/bin/python main.py dashboard  # 启动看板（默认 :8080）
.venv/bin/python main.py            # 调度模式：每日 09:00 自动执行 + 看板
```

## 架构

三条并行管线，共享调度入口 `main.py`：

```
┌─ 主流程（行动包）─────────────────────────────────────────────────┐
│ RSS(11源) + Twitter(25+账号) + Telegram(可选)                     │
│   → data/raw/{date}/items.json                                    │
│   → Manus AI 四层漏斗 → data/processed/{date}/result.md          │
│   → Gemini 结构化提取 → data/processed/{date}/result.json        │
└───────────────────────────────────────────────────────────────────┘

┌─ 竞品流程（简报）─────────────────────────────────────────────────┐
│ 多渠道抓取(Twitter/API/RSS/Web) 按竞品并行                        │
│   → data/competitors/{date}/items.json                            │
│ + 媒体关键词过滤（从主流程热点中筛选竞品相关报道，追加到上面）      │
│   → Gemini 结构化提取 → data/competitors/{date}/result.json      │
└───────────────────────────────────────────────────────────────────┘

┌─ 舆情流程（品牌监控）────────────────────────────────────────────┐
│ Twitter + Reddit + YouTube 关键词搜索（7天回溯）                  │
│   → data/sentiment/{date}/items.json                              │
│   → Gemini 过滤噪音 + 结构化提取 → data/sentiment/{date}/result.json │
└───────────────────────────────────────────────────────────────────┘
```

三条管线通过 `asyncio.gather` 并发执行，竞品媒体过滤依赖主流程数据，舆情管线独立运行。

### 执行顺序（`run_fetch_and_process`）

1. 并发：主流程 RSS+Twitter 抓取 ‖ 竞品官方渠道抓取 ‖ 舆情 Twitter+Reddit+YouTube 抓取
2. 串行：Telegram 抓取（需交互式登录，目前已注释）
3. 媒体关键词过滤：`competitor.append_media_items()` 从主流程热点中匹配竞品关键词，去重后追加到竞品 items
4. Manus API 处理主流程 → result.md → Gemini 提取 → result.json
5. Gemini 提取竞品结构化数据 → result.json
6. Gemini 过滤噪音 + 提取舆情结构化数据 → result.json

### 数据读取路径（双模式）

- FastAPI 动态模式：`dashboard/app.py` 直接读 `data/processed/`、`data/competitors/`、`data/sentiment/`，信源读 `config/*.yaml`
- Vercel 静态模式：前端 JS 直接读 `data/processed/`、`data/competitors/`、`data/sentiment/`、`config/*.yaml`（js-yaml 解析）

## 目录结构

```
main.py                   # 入口：命令分发 + 调度 + fetch/dashboard
config/
  sources.yaml            # 主流程信源（RSS 11个 + Twitter 25+账号）
  competitors.yaml        # 竞品配置（30个竞品，T1-T4 分层，7 区域，含媒体关键词）
  sentiment.yaml          # 舆情监控配置（关键词 + 平台开关 + 回溯天数）
fetcher/
  rss.py                  # RSS 并发抓取，feedparser 解析，24h 时间过滤
  twitter.py              # TwitterAPI.io 串行抓取（避免 429），指数退避重试
  telegram.py             # Telethon 频道拉取（需交互式登录，目前已注释）
  competitor.py           # 竞品多渠道抓取 + 通用重试 + 媒体关键词过滤 + append_media_items()
  sentiment.py            # 舆情抓取：Twitter+Reddit+YouTube 关键词搜索，7天回溯，URL 去重
processor/
  manus.py                # Manus API：文件上传 → 创建任务 → 轮询(60s/1800s) → 提取输出
  extractor.py            # Gemini 提取行动包 JSON（gemini-3-flash-preview，async）
  competitor_extractor.py # Gemini 提取竞品简报 JSON + 按配置补全所有竞品（async）
  sentiment_extractor.py  # Gemini 过滤噪音 + 提取舆情结构化 JSON（importance 分级，async）
dashboard/
  app.py                  # FastAPI 看板（9 个 API 端点，含 /api/sentiment/*）
  index.html              # Vercel 静态部署入口
  templates/index.html    # FastAPI 单页模板
  static/app.js           # 前端交互（四栏切换：热点/竞品/舆情/信源，过滤/日历/自动刷新 5min）
  static/style.css        # 样式（侧边栏导航 + 卡片 + 动画）
vercel.json               # Vercel rewrite 规则（根目录部署）
knowledge/                # 业务知识库（SOP、周会纪要等）
```

## 环境变量（.env）

- `TWITTER_API_KEY` — TwitterAPI.io（主流程 + 竞品 + 舆情共用）
- `GEMINI_API_KEY` — Gemini 结构化提取（模型：gemini-3-flash-preview）
- `MANUS_API_KEY` / `MANUS_PROJECT_ID` — Manus AI 处理
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — Telegram（可选，目前已注释）
- `RAPIDAPI_KEY` — RapidAPI Reddit 搜索（舆情 Reddit 抓取）
- `YOUTUBE_API_KEY` — YouTube Data API v3（舆情 YouTube 抓取）
- `DASHBOARD_PORT` — 看板端口（默认 8080）

## 竞品分层（30 家，7 区域）

- T1 HK 核心竞对：HashKey、HKVAX、VDX、Bullish
- T2 头部交易所：Binance、OKX、Bybit、Coinbase、Kraken
- T3 区域竞品：
  - JP(bitFlyer/Coincheck/GMO Coin/bitbank/SBI VC Trade/Rakuten Wallet)
  - VN(Remitano)
  - EU(Bitstamp/Bitpanda/Bitvavo/Crypto.com/Gemini)
  - ID(Indodax/Tokocrypto/PINTU/Upbit/Luno/Reku)
- T4 BROKER 轻量监控：富途/老虎/盈透（仅关注加密相关）

## 竞品信源覆盖

- Web 可爬（12 家）：HKVAX、Bullish、Coincheck、bitbank、Bitstamp、Bitpanda、Crypto.com、Gemini、Indodax、PINTU、Luno、Reku
- RSS/API（9 家）：Binance(API)、Bybit(API)、Coinbase(RSS)、Kraken(RSS)、GMO Coin(RSS)、bitbank(RSS)、Tokocrypto(RSS)、富途(RSS)、老虎(RSS)、盈透(RSS)
- 仅 Twitter（9 家）：HashKey、VDX、OKX、Remitano、bitFlyer、SBI VC Trade、Rakuten Wallet、Bitvavo、Upbit Indonesia
- Web 不可用原因：SPA 需 JS 渲染（SBI VC Trade）、WAF 拦截（HashKey/Rakuten Wallet/Bitvavo/bitFlyer）、地区限制（OKX）

## 数据存储结构

```
data/
├── raw/{date}/items.json              # 主流程原始热点（RSS+Twitter+Telegram）
├── processed/{date}/
│   ├── result.md                      # Manus 输出的 Markdown
│   └── result.json                    # Gemini 结构化行动包
├── processed/dates.json               # 可用日期索引（fetch 自动生成）
├── processed/latest.json              # 最新日期数据副本
├── competitors/{date}/
│   ├── items.json                     # 竞品原始数据（官方渠道 + 媒体过滤）
│   └── result.json                    # Gemini 结构化竞品简报
├── competitors/dates.json             # 竞品日期索引
├── competitors/latest.json            # 最新竞品数据副本
├── sentiment/{date}/
│   ├── items.json                     # 舆情原始数据（Twitter+Reddit+YouTube）
│   └── result.json                    # Gemini 结构化舆情（importance 分级）
├── sentiment/dates.json               # 舆情日期索引
└── sentiment/latest.json              # 最新舆情数据副本
```

## API 端点

| 端点 | 说明 |
|------|------|
| `GET /api/today` | 今日行动包（无数据返回空 cards） |
| `GET /api/history?date=YYYY-MM-DD` | 历史行动包 |
| `GET /api/dates` | 所有可用日期列表 |
| `GET /api/competitors/today` | 今日竞品动态（无数据回退到最近一天） |
| `GET /api/competitors/history?date=YYYY-MM-DD` | 历史竞品数据 |
| `GET /api/competitors/dates` | 竞品数据日期列表 |
| `GET /api/sentiment/today` | 今日舆情数据（无数据回退到最近一天） |
| `GET /api/sentiment/dates` | 舆情数据日期列表 |
| `GET /api/sources` | 信源配置（读取 config/sources.yaml） |

## 已知问题

- ~~`data/competitors/` 下存在冗余的 `processed/` 和 `raw/` 子目录（历史遗留），sync 和 API 遍历时需过滤非日期目录~~ ✅ 已通过 `_is_date_dir()` 正则过滤修复
- Coinbase RSS 返回 403、Indodax Web/RSS 连接超时（网络环境相关）
- Binance API 返回 0 items（可能需要调整 catalogId 参数）
- Telegram 需交互式登录，自动化环境无法运行（sources.yaml 已注释）
- 移动端适配缺失：左侧导航 `#left-nav` 固定 208px（`w-52`）在手机上占半屏，`#app-content` 硬编码 `ml-52` 导致内容被挤压到 ~167px，CSS 无媒体查询，JS 无移动端逻辑。方案：移动端（<768px）隐藏左侧导航（`hidden md:flex`），主内容改为 `md:ml-52`，新增底部固定标签栏（3 tab：热点/竞品/信源，复用侧边栏 SVG 图标），CSS 加 `@media (max-width: 767px)` 隐藏过滤栏分隔符、hero-stats 换行，JS `switchSection()` 同步底部标签栏 active 状态

## 架构约定

- 目录遍历必须使用 `_is_date_dir()` 过滤（正则 `^\d{4}-\d{2}-\d{2}$` + result.json 存在），`app.py` 和 `main.py` 各有一份；`main.py` 中 `_is_sentiment_date_dir()` 仅用于索引生成前检查 items.json 是否存在（舆情可能只有 items 没有 result）
- Gemini 提取器（`extractor.py`、`competitor_extractor.py`、`sentiment_extractor.py`）均为 async，重试用 `asyncio.sleep`
- 媒体关键词过滤的唯一入口是 `competitor.append_media_items()`，禁止在 `main.py` 中手动实现过滤+去重逻辑
- 舆情抓取配置集中在 `config/sentiment.yaml`，关键词按平台分组，`lookback_hours` 控制回溯窗口（默认 168h = 7天）

## 技术栈

Python 3.13 + httpx + feedparser + BeautifulSoup4 + FastAPI + google-genai + APScheduler + python-dotenv + PyYAML

## CI/CD

- GitHub Action `daily_fetch.yml`：每日北京时间 07:30（UTC 23:30）自动执行 fetch + commit + push
- fetch 结束自动生成 `dates.json` + `latest.json` 索引文件
- 提交范围：`data/**/*.json`、`data/**/*.md`
- Vercel 静态部署：仓库根目录，`vercel.json` 配置 rewrite 规则，前端直接读 `data/` 和 `config/`
