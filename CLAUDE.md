你必须始终使用**简体中文**和我进行所有对话。

# OSL Growth Hotspot Agent

加密行业热点监控 + 竞品动态追踪系统，每日自动抓取、AI 处理、生成结构化简报并展示在看板上。

## 运行命令

```bash
python main.py fetch      # 一次性抓取 + AI 处理
python main.py sync       # 同步数据到 dashboard/data/（供静态部署）
python main.py dashboard  # 启动看板（默认 :8080）
python main.py            # 调度模式：每日 09:00 自动执行 + 看板
```

## 架构

两条并行管线，共享调度入口 `main.py`：

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
```

两条管线通过 `asyncio.gather` 并发执行，竞品媒体过滤依赖主流程数据。

### 执行顺序（`run_fetch_and_process`）

1. 并发：主流程 RSS+Twitter 抓取 ‖ 竞品官方渠道抓取
2. 串行：Telegram 抓取（需交互式登录，目前已注释）
3. 媒体关键词过滤：`competitor.append_media_items()` 从主流程热点中匹配竞品关键词，去重后追加到竞品 items
4. Manus API 处理主流程 → result.md → Gemini 提取 → result.json
5. Gemini 提取竞品结构化数据 → result.json

### 数据读取路径（双模式）

- FastAPI 动态模式：`dashboard/app.py` 直接读 `data/processed/` 和 `data/competitors/`
- 静态部署模式：前端 JS 读 `dashboard/data/`（由 `sync` 命令从源目录复制）

## 目录结构

```
main.py                   # 入口：命令分发 + 调度 + fetch/sync/dashboard
config/
  sources.yaml            # 主流程信源（RSS 11个 + Twitter 25+账号）
  competitors.yaml        # 竞品配置（32个竞品，T1-T4 分层，7 区域，含媒体关键词）
fetcher/
  rss.py                  # RSS 并发抓取，feedparser 解析，24h 时间过滤
  twitter.py              # TwitterAPI.io 串行抓取（避免 429），指数退避重试
  telegram.py             # Telethon 频道拉取（需交互式登录，目前已注释）
  competitor.py           # 竞品多渠道抓取 + 通用重试 + 媒体关键词过滤 + append_media_items()
processor/
  manus.py                # Manus API：文件上传 → 创建任务 → 轮询(60s/1800s) → 提取输出
  extractor.py            # Gemini 提取行动包 JSON（gemini-3-flash-preview，async）
  competitor_extractor.py # Gemini 提取竞品简报 JSON + 按配置补全所有竞品（async）
dashboard/
  app.py                  # FastAPI 看板（7 个 API 端点，含 /api/sources）
  index.html              # Vercel 静态部署入口（与 templates/index.html 同步）
  templates/index.html    # FastAPI 单页模板
  static/app.js           # 前端交互（三栏切换：热点/竞品/信源，过滤/日历/自动刷新 5min）
  static/style.css        # 样式（侧边栏导航 + 卡片 + 动画）
  data/                   # sync 输出目录（供静态部署）
knowledge/                # 业务知识库（SOP、周会纪要等）
```

## 环境变量（.env）

- `TWITTER_API_KEY` — TwitterAPI.io（主流程 + 竞品共用）
- `GEMINI_API_KEY` — Gemini 结构化提取（模型：gemini-3-flash-preview）
- `MANUS_API_KEY` / `MANUS_PROJECT_ID` — Manus AI 处理
- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` — Telegram（可选，目前已注释）
- `DASHBOARD_PORT` — 看板端口（默认 8080）

## 竞品分层（32 家，7 区域）

- T1 HK 核心竞对：HashKey、HKVAX、HKbitEX、VDX、Bullish
- T2 头部交易所：Binance、OKX、Bybit、Coinbase、Kraken
- T3 区域竞品：
  - JP(bitFlyer/Coincheck/GMO Coin/bitbank/SBI VC Trade/Rakuten Wallet)
  - VN(VNDC/Remitano)
  - EU(Bitstamp/Bitpanda/Bitvavo/Crypto.com/Gemini)
  - ID(Indodax/Tokocrypto/PINTU/Upbit/Luno/Reku)
- T4 BROKER 轻量监控：富途/老虎/盈透（仅关注加密相关）

## 竞品信源覆盖

- Web 可爬（12 家）：HKVAX、Bullish、Coincheck、bitbank、Bitstamp、Bitpanda、Crypto.com、Gemini、Indodax、PINTU、Luno、Reku
- RSS/API（9 家）：Binance(API)、Bybit(API)、Coinbase(RSS)、Kraken(RSS)、GMO Coin(RSS)、bitbank(RSS)、Tokocrypto(RSS)、富途(RSS)、老虎(RSS)、盈透(RSS)
- 仅 Twitter（11 家）：HashKey、HKbitEX、VDX、OKX、VNDC、Remitano、bitFlyer、SBI VC Trade、Rakuten Wallet、Bitvavo、Upbit Indonesia
- Web 不可用原因：SPA 需 JS 渲染（HKbitEX/SBI VC Trade）、WAF 拦截（HashKey/Rakuten Wallet/Bitvavo/bitFlyer）、地区限制（OKX）

## 数据存储结构

```
data/
├── raw/{date}/items.json              # 主流程原始热点（RSS+Twitter+Telegram）
├── processed/{date}/
│   ├── result.md                      # Manus 输出的 Markdown
│   └── result.json                    # Gemini 结构化行动包
└── competitors/{date}/
    ├── items.json                     # 竞品原始数据（官方渠道 + 媒体过滤）
    └── result.json                    # Gemini 结构化竞品简报

dashboard/data/                        # sync 输出（静态部署用）
├── {date}.json / latest.json / dates.json
├── competitors/{date}.json / latest.json / dates.json
└── sources.json                       # 信源配置（sync 从 config/sources.yaml 生成）
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
| `GET /api/sources` | 信源配置（读取 config/sources.yaml） |

## 已知问题

- ~~`data/competitors/` 下存在冗余的 `processed/` 和 `raw/` 子目录（历史遗留），sync 和 API 遍历时需过滤非日期目录~~ ✅ 已通过 `_is_date_dir()` 正则过滤修复
- Coinbase RSS 返回 403、Indodax Web/RSS 连接超时（网络环境相关）
- Binance API 返回 0 items（可能需要调整 catalogId 参数）
- Telegram 需交互式登录，自动化环境无法运行（sources.yaml 已注释）

## 架构约定

- 目录遍历必须使用 `_is_date_dir()` 过滤（正则 `^\d{4}-\d{2}-\d{2}$` + result.json 存在），`app.py` 和 `main.py` 各有一份
- Gemini 提取器（`extractor.py`、`competitor_extractor.py`）均为 async，重试用 `asyncio.sleep`
- 媒体关键词过滤的唯一入口是 `competitor.append_media_items()`，禁止在 `main.py` 中手动实现过滤+去重逻辑

## 技术栈

Python 3.13 + httpx + feedparser + BeautifulSoup4 + FastAPI + google-genai + APScheduler + python-dotenv + PyYAML

## CI/CD

- GitHub Action `daily_fetch.yml`：每日北京时间 07:30（UTC 23:30）自动执行 fetch + sync + commit + push
- 提交范围：`data/**/*.json`、`data/**/*.md`、`dashboard/data/*.json`、`dashboard/data/competitors/*.json`、`dashboard/data/sources.json`
- Vercel 静态部署：`dashboard/` 目录，`index.html` + `static/` + `data/`
