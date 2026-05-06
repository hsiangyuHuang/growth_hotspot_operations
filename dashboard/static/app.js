// ── Config ──
const REFRESH_INTERVAL = 5 * 60 * 1000;
let currentSection = "hotspot"; // "hotspot" or "competitors"
let currentTab = "today";
let filterChannel = "ALL";
let filterSite = "ALL";
let _currentData = null;
let refreshTimer = null;

// Data paths — always use static files (works on both Vercel and local FastAPI)
const API = { today: "./data/processed/latest.json", dates: "./data/processed/dates.json", history: (d) => `./data/processed/${d}/result.json` };
const COMP_API = { today: "./data/competitors/pool.json", dates: "./data/competitors/dates.json", history: (d) => `./data/competitors/${d}/result.json` };
const SENT_API = { today: "./data/sentiment/pool.json", dates: "./data/sentiment/dates.json" };

// ── Browser ID ──
function getBrowserId() {
  let id = localStorage.getItem('osl_browser_id');
  if (!id) { id = crypto.randomUUID(); localStorage.setItem('osl_browser_id', id); }
  return id;
}

// ── Design Tokens ──
const URGENCY_CONFIG = {
  Flash: { label: 'Flash <4h', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
  Day:   { label: 'Day 4-48h', color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' },
  Wave:  { label: 'Wave 2-7d', color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' },
  Trend: { label: 'Trend 1-4w', color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
};

const CATEGORY_ORDER = ['行情波动','监管政策','行业趋势','安全事件','宏观经济','行业大会','竞品动态','链上数据'];
const CATEGORY_CONFIG = {
  '行情波动': { label: '行情波动', color: 'text-red-400',     bg: 'bg-red-500/15',     bar: 'bg-red-500',     divider: 'bg-red-500/20' },
  '监管政策': { label: '监管政策', color: 'text-amber-400',   bg: 'bg-amber-500/15',   bar: 'bg-amber-500',   divider: 'bg-amber-500/20' },
  '行业趋势': { label: '行业趋势', color: 'text-emerald-400', bg: 'bg-emerald-500/15', bar: 'bg-emerald-500', divider: 'bg-emerald-500/20' },
  '安全事件': { label: '安全事件', color: 'text-rose-400',    bg: 'bg-rose-500/15',    bar: 'bg-rose-500',    divider: 'bg-rose-500/20' },
  '宏观经济': { label: '宏观经济', color: 'text-blue-400',    bg: 'bg-blue-500/15',    bar: 'bg-blue-500',    divider: 'bg-blue-500/20' },
  '行业大会': { label: '行业大会', color: 'text-violet-400',  bg: 'bg-violet-500/15',  bar: 'bg-violet-500',  divider: 'bg-violet-500/20' },
  '竞品动态': { label: '竞品动态', color: 'text-cyan-400',    bg: 'bg-cyan-500/15',    bar: 'bg-cyan-500',    divider: 'bg-cyan-500/20' },
  '链上数据': { label: '链上数据', color: 'text-teal-400',    bg: 'bg-teal-500/15',    bar: 'bg-teal-500',    divider: 'bg-teal-500/20' },
};

const CHANNEL_CONFIG = {
  'Paid Ads':            { label: 'Paid Ads',    icon: '', color: 'text-amber-300',  bg: 'bg-amber-500/15',  activeCls: 'text-amber-300 bg-amber-500/15' },
  'SEO':                 { label: 'SEO',         icon: '', color: 'text-emerald-300', bg: 'bg-emerald-500/15', activeCls: 'text-emerald-300 bg-emerald-500/15' },
  '站内运营 / 用户触达': { label: '站内运营/触达', icon: '', color: 'text-cyan-300',   bg: 'bg-cyan-500/15',   activeCls: 'text-cyan-300 bg-cyan-500/15' },
  '社区':                { label: '社区运营',     icon: '', color: 'text-violet-300', bg: 'bg-violet-500/15', activeCls: 'text-violet-300 bg-violet-500/15' },
};

const SITE_CONFIG = {
  HK:     { label: 'HK 站',      color: 'text-sky-300',    bg: 'bg-sky-500/15' },
  Global: { label: 'Global 站',  color: 'text-indigo-300', bg: 'bg-indigo-500/15' },
  Both:   { label: 'HK + Global', color: 'text-teal-300',  bg: 'bg-teal-500/15' },
};

// ── Bootstrap ──
document.addEventListener("DOMContentLoaded", () => {
  setupSubTabs();
  loadToday();
  refreshTimer = setInterval(() => {
    if (currentSection === "hotspot" && currentTab === "today") loadToday();
  }, REFRESH_INTERVAL);
});

// ── Left Nav Section Switch ──
function switchSection(section) {
  currentSection = section;
  document.querySelectorAll(".nav-item").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.section === section);
  });
  document.querySelectorAll(".mobile-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.section === section);
  });

  const hotspotTabs = document.getElementById("sub-tabs-hotspot");
  const compTabs = document.getElementById("sub-tabs-competitors");
  const sourcesTabs = document.getElementById("sub-tabs-sources");
  const sentimentTabs = document.getElementById("sub-tabs-sentiment");
  const mainFilters = document.getElementById("main-filters");
  const dateSel = document.getElementById("date-selector");
  const filterDivider = document.getElementById("filter-divider");

  // 默认全部隐藏
  hotspotTabs.style.display = "none";
  compTabs.style.display = "none";
  sourcesTabs.style.display = "none";
  sentimentTabs.style.display = "none";
  mainFilters.style.display = "none";
  dateSel.style.display = "none";
  filterDivider.style.display = "none";

  if (section === "hotspot") {
    hotspotTabs.style.display = "";
    mainFilters.style.display = "";
    filterDivider.style.display = "";
    if (currentTab === "history") {
      dateSel.style.display = "";
      loadDates();
    } else {
      currentTab = "today";
      loadToday();
    }
  } else if (section === "competitors") {
    compTabs.style.display = "";
    currentTab = "competitors";
    loadCompetitors();
  } else if (section === "sources") {
    currentTab = "sources";
    loadSources();
  } else if (section === "sentiment") {
    sentimentTabs.style.display = "";
    currentTab = "sentiment";
    loadSentiment();
  }
}

function setupSubTabs() {
  document.querySelectorAll("#sub-tabs-hotspot .tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      currentTab = btn.dataset.tab;
      document.querySelectorAll("#sub-tabs-hotspot .tab-btn").forEach(b => {
        b.classList.remove("active", "bg-white/[0.12]", "text-white", "ring-1", "ring-inset", "ring-white/15", "shadow-sm");
        b.classList.add("text-slate-400");
      });
      btn.classList.add("active", "bg-white/[0.12]", "text-white", "ring-1", "ring-inset", "ring-white/15", "shadow-sm");
      btn.classList.remove("text-slate-400");
      const dateSel = document.getElementById("date-selector");
      if (currentTab === "today") {
        dateSel.style.display = "none";
        _selectedHistoryDate = null;
        loadToday();
      } else if (currentTab === "history") {
        dateSel.style.display = "";
        loadDates();
      }
    });
  });
  const activeBtn = document.querySelector('#sub-tabs-hotspot .tab-btn.active');
  if (activeBtn) {
    activeBtn.classList.add("bg-white/[0.12]", "text-white", "ring-1", "ring-inset", "ring-white/15", "shadow-sm");
  }
  document.querySelectorAll('#sub-tabs-hotspot .tab-btn:not(.active)').forEach(b => b.classList.add("text-slate-400"));
}

// ── Filter Rendering ──
function renderFilterButtons() {
  const channels = ["ALL", "Paid Ads", "SEO", "站内运营 / 用户触达", "社区"];
  const sites = ["ALL", "HK", "Global"];

  function filterBtn(value, label, isActive, cfg, onclick) {
    const base = 'text-xs font-medium px-3 py-1.5 rounded-md transition-all duration-200 cursor-pointer select-none';
    const active = cfg
      ? `${cfg.color} ${cfg.bg} ring-1 ring-inset ring-white/10 shadow-sm`
      : 'bg-white/[0.12] text-white ring-1 ring-inset ring-white/15 shadow-sm';
    const inactive = 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.06]';
    return `<button onclick="${onclick}" class="${base} ${isActive ? active : inactive}">${label}</button>`;
  }

  document.getElementById("filter-channel").innerHTML =
    '<span class="text-xs text-slate-500 font-medium mr-2">渠道</span>' +
    channels.map(c => {
      const cfg = c !== "ALL" ? CHANNEL_CONFIG[c] : null;
      const label = c === "ALL" ? "全部" : (cfg ? cfg.label : c);
      return filterBtn(c, label, filterChannel === c, cfg, `setFilterChannel('${esc(c)}')`);
    }).join("");

  document.getElementById("filter-site").innerHTML =
    '<span class="text-xs text-slate-500 font-medium mr-2">站点</span>' +
    sites.map(s => {
      const cfg = s !== "ALL" ? SITE_CONFIG[s] : null;
      const label = s === "ALL" ? "全部" : (cfg ? cfg.label : s);
      return filterBtn(s, label, filterSite === s, cfg, `setFilterSite('${s}')`);
    }).join("");
}

function setFilterChannel(v) {
  filterChannel = v;
  rerender();
  // 自动展开所有卡片中对应渠道的面板
  if (v !== 'ALL') {
    requestAnimationFrame(() => autoExpandChannel(v));
  }
}
function setFilterSite(v) { filterSite = v; rerender(); }
function rerender() { if (_currentData) renderDashboard(_currentData); }

// ── Skeleton Loading ──
function renderSkeleton(count = 4) {
  const card = `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4 space-y-3">
    <div class="flex items-center justify-between">
      <div class="skeleton h-4 w-48"></div>
      <div class="flex gap-1.5"><div class="skeleton h-5 w-10"></div><div class="skeleton h-5 w-20"></div></div>
    </div>
    <div class="skeleton h-3 w-32"></div>
    <div class="space-y-2"><div class="skeleton h-3 w-full"></div><div class="skeleton h-3 w-4/5"></div></div>
    <div class="flex gap-2"><div class="skeleton h-6 w-20"></div><div class="skeleton h-6 w-16"></div></div>
  </div>`;
  return `<div class="grid grid-cols-1 xl:grid-cols-2 gap-4">${card.repeat(count)}</div>`;
}

function showSkeleton() {
  document.getElementById("card-sections").innerHTML = renderSkeleton();
  document.getElementById("hero-stats").innerHTML = `
    <div class="skeleton h-8 w-12"></div>
    <div class="w-px h-8 bg-white/10"></div>
    <div class="skeleton h-8 w-12"></div>
    <div class="skeleton h-8 w-12"></div>
    <div class="skeleton h-8 w-12"></div>`;
}

// ── Data Loading ──
async function loadToday() {
  showSkeleton();
  try {
    const res = await fetch(API.today);
    const data = await res.json();
    _currentData = data;
    renderDashboard(data);
  } catch (e) {
    console.error("Failed to load today:", e);
    document.getElementById("card-sections").innerHTML =
      `<pre class="text-red-400 text-xs p-4">${e.message}</pre>` + renderEmptyState();
  }
}

let _selectedHistoryDate = null;

async function loadDates() {
  try {
    const res = await fetch(API.dates);
    const data = await res.json();
    // Support both old format ["2026-04-10", ...] and new format [{date, count}, ...]
    let rawDates = Array.isArray(data) ? data : (data.dates || []);
    const countMap = {};
    const dateList = [];
    for (const item of rawDates) {
      if (typeof item === 'string') {
        dateList.push(item);
        countMap[item] = 1;
      } else {
        dateList.push(item.date);
        countMap[item.date] = item.count || 0;
      }
    }
    renderDateTimeline(dateList, countMap);
  } catch (e) { console.error("Failed to load dates:", e); }
}

let _calendarDates = [];

function renderDateTimeline(dates, countMap) {
  const container = document.getElementById("date-selector");
  _calendarDates = dates;
  const dateSet = new Set(dates);
  const todayStr = new Date().toISOString().split('T')[0];

  // Fixed range: full year 2026, aligned to week boundaries (Mon–Sun)
  const start = new Date('2026-01-01');
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7)); // align to Monday
  const end = new Date('2026-12-31');
  end.setDate(end.getDate() + (6 - (end.getDay() + 6) % 7)); // align to Sunday

  // Generate all days
  const allDays = [];
  const cur = new Date(start);
  while (cur <= end) {
    allDays.push({
      str: `${cur.getFullYear()}-${String(cur.getMonth()+1).padStart(2,'0')}-${String(cur.getDate()).padStart(2,'0')}`,
      day: cur.getDate(),
      month: cur.getMonth(),
    });
    cur.setDate(cur.getDate() + 1);
  }

  // Group into weeks (7 days each, Mon–Sun)
  const weeks = [];
  for (let i = 0; i < allDays.length; i += 7) weeks.push(allDays.slice(i, i + 7));

  const MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  const dayLabels = ['一','','三','','五','',''];

  // 3-level brightness based on card count
  function heatColor(dateStr) {
    const count = countMap[dateStr] || 0;
    if (count === 0) return '#161b22';
    if (count <= 5) return '#0e4429';
    if (count <= 8) return '#006d32';
    return '#26a641';
  }

  let html = '<div class="w-full overflow-x-auto pb-1">';

  // Legend row
  html += `<div class="flex items-center justify-between mb-2">
    <span class="text-[11px] text-slate-400 font-mono">${dates.length} 天有数据 · 2026</span>
    <div class="flex items-center gap-[3px]">
      <span class="text-[9px] text-slate-600 font-mono mr-1">Less</span>
      <span class="inline-block w-[10px] h-[10px] rounded-sm" style="background:#161b22"></span>
      <span class="inline-block w-[10px] h-[10px] rounded-sm" style="background:#0e4429"></span>
      <span class="inline-block w-[10px] h-[10px] rounded-sm" style="background:#006d32"></span>
      <span class="inline-block w-[10px] h-[10px] rounded-sm" style="background:#26a641"></span>
      <span class="text-[9px] text-slate-600 font-mono ml-1">More</span>
    </div>
  </div>`;

  // Heatmap grid: day-label column + week columns
  html += '<div class="inline-flex gap-[3px]">';

  // Day-of-week labels
  html += '<div class="flex flex-col gap-[3px] mr-[2px]">';
  html += '<div style="height:14px"></div>';
  dayLabels.forEach(l => {
    html += `<div class="flex items-center text-[9px] text-slate-600 font-mono" style="height:11px">${l}</div>`;
  });
  html += '</div>';

  // Week columns
  weeks.forEach((week, wi) => {
    const f = week[0];
    let mLabel = '';
    if (wi === 0 || f.month !== weeks[wi - 1][0].month) mLabel = MONTHS[f.month];

    html += '<div class="flex flex-col gap-[3px]">';
    html += `<div class="text-[9px] text-slate-500 font-mono whitespace-nowrap" style="height:14px;line-height:14px">${mLabel}</div>`;

    week.forEach(d => {
      const has = dateSet.has(d.str);
      const isSel = _selectedHistoryDate === d.str;
      const isToday = d.str === todayStr;
      const count = countMap[d.str] || 0;

      const bg = isSel ? '#39d353' : heatColor(d.str);
      const ring = isSel ? ' ring-1 ring-cyan-400' : (isToday ? ' ring-1 ring-slate-500' : '');
      const click = has ? ` onclick="selectHistoryDate('${d.str}')"` : '';
      const tip = `${d.month + 1}月${d.day}日` + (count > 0 ? ` · ${count} 条` : '');

      html += `<div class="hm-cell${ring}${has ? ' hm-has' : ''}" style="background:${bg}" data-tip="${tip}"${click}></div>`;
    });

    html += '</div>';
  });

  html += '</div></div>';
  container.innerHTML = html;

  // 移动端自动滚动到最近日期区域
  const scrollEl = container.querySelector('.overflow-x-auto');
  if (scrollEl) scrollEl.scrollLeft = scrollEl.scrollWidth;
}

function selectHistoryDate(dateStr) {
  _selectedHistoryDate = dateStr;
  loadDates();
  loadHistory(dateStr);
}

async function loadHistory(dateStr) {
  try {
    const res = await fetch(API.history(dateStr));
    if (!res.ok) { document.getElementById("card-sections").innerHTML = renderEmptyState(); return; }
    const data = await res.json();
    _currentData = data;
    renderDashboard(data);
  } catch (e) { console.error("Failed to load history:", e); }
}

// ── Main Render ──
function renderDashboard(data) {
  const allCards = data.cards || [];

  // Header date
  document.getElementById("header-date").textContent = data.run_date
    ? `数据更新于 ${data.run_date}`
    : "";

  // Filter
  const filtered = allCards.filter(card => {
    if (filterChannel !== "ALL" && !(card.channels || []).some(c => c.name === filterChannel)) return false;
    if (filterSite !== "ALL") {
      const site = normalizeSite(card.site);
      if (site !== filterSite && site !== "Both") return false;
    }
    return true;
  });

  renderFilterButtons();
  document.getElementById("filter-count").textContent = `显示 ${filtered.length} / ${allCards.length} 条`;
  renderHeroStats(allCards);

  // Group by category
  const byCategory = {};
  for (const card of filtered) {
    const cat = card.category || '行业趋势';
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(card);
  }

  let html = "";
  for (const cat of CATEGORY_ORDER) {
    if (byCategory[cat] && byCategory[cat].length > 0) {
      html += renderCategorySection(cat, byCategory[cat]);
    }
  }
  // Render any categories not in CATEGORY_ORDER (fallback for old data)
  for (const cat of Object.keys(byCategory)) {
    if (!CATEGORY_ORDER.includes(cat)) {
      html += renderCategorySection(cat, byCategory[cat]);
    }
  }
  if (filtered.length === 0) html = renderEmptyState();

  document.getElementById("card-sections").innerHTML = html;
  renderSidebar(data);

  document.getElementById("footer-left").textContent = `OSL Growth Intelligence · ${data.run_date || ""}`;
  document.getElementById("footer-right").textContent = `基于四层漏斗筛选 · ${allCards.length} 个行动包`;
}

// ── Hero Stats ──
function renderHeroStats(cards) {
  // Count by category
  const catCounts = {};
  for (const c of cards) {
    const cat = c.category || '行业趋势';
    catCounts[cat] = (catCounts[cat] || 0) + 1;
  }
  // Sort by count desc, take top categories
  const sorted = Object.entries(catCounts).sort((a, b) => b[1] - a[1]);
  const topStats = sorted.slice(0, 4).map(([cat, count]) => {
    const cfg = CATEGORY_CONFIG[cat] || { color: 'text-slate-400', label: cat };
    return `<div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold ${cfg.color}">${count}</div><div class="text-[10px] text-slate-500 font-mono">${cfg.label}</div></div>`;
  }).join("");
  document.getElementById("hero-stats").innerHTML = `
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-white">${cards.length}</div><div class="text-[10px] text-slate-500 font-mono">行动包</div></div>
    <div class="w-px h-6 md:h-8 bg-white/10"></div>
    ${topStats}`;
}

// ── Category Section ──
function renderCategorySection(category, cards) {
  const cfg = CATEGORY_CONFIG[category] || { label: category, color: 'text-slate-400', bg: 'bg-slate-500/15', bar: 'bg-slate-500', divider: 'bg-slate-500/20' };

  return `<section>
    <div class="flex items-center gap-3 mb-4">
      <span class="h-3 w-3 rounded-full ${cfg.bar} shrink-0"></span>
      <h2 class="text-sm font-display font-bold ${cfg.color} tracking-wide uppercase">${cfg.label}</h2>
      <div class="flex-1 h-px ${cfg.divider}"></div>
      <span class="text-[10px] font-mono ${cfg.color} opacity-60">${cards.length} 条</span>
    </div>
    <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
      ${cards.map((card, i) => renderCard(card, i)).join("")}
    </div>
  </section>`;
}

// ── Card ──
function renderCard(card, index) {
  const cat = card.category || '行业趋势';
  const catCfg = CATEGORY_CONFIG[cat] || CATEGORY_CONFIG['行业趋势'];
  const timing = parseTimingKey(card.timing);
  const tCfg = URGENCY_CONFIG[timing] || URGENCY_CONFIG.Day;
  const site = normalizeSite(card.site);
  const sCfg = SITE_CONFIG[site] || SITE_CONFIG.Both;

  const channelTabs = (card.channels || []).map((ch, ci) => {
    const chCfg = CHANNEL_CONFIG[ch.name] || { label: ch.name, icon: '', color: 'text-slate-300', bg: 'bg-slate-500/15', activeCls: 'text-slate-300 bg-slate-500/15' };
    return `<button onclick="toggleChannelTab('${card.id}',${ci})" id="ch-tab-${card.id}-${ci}" data-channel="${esc(ch.name)}"
      class="ch-tab inline-flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-medium transition-colors duration-150 text-slate-400 bg-white/[0.05] hover:bg-white/10 hover:text-slate-200">
      ${chCfg.label}<span class="ml-0.5 transition-transform duration-150" id="ch-arrow-${card.id}-${ci}">▾</span>
    </button>`;
  }).join("");

  const channelPanels = (card.channels || []).map((ch, ci) => {
    const chCfg = CHANNEL_CONFIG[ch.name] || { label: ch.name, icon: '📋', color: 'text-slate-300', bg: 'bg-slate-500/15' };
    return `<div id="ch-panel-${card.id}-${ci}" class="hidden border border-white/[0.08] rounded-md bg-[#0f1623] p-3 mb-2 mt-1 ch-panel" data-channel="${esc(ch.name)}">
      <div class="flex items-center justify-between mb-2">
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${chCfg.color} ${chCfg.bg}">${chCfg.label}</span>
        <button onclick="copyAndAccept('${card.id}','${esc(ch.name)}','ch-md-${card.id}-${ci}')"
          class="text-[10px] font-mono px-2 py-1 rounded border border-white/10 text-slate-400 hover:border-cyan-500/40 hover:text-cyan-400 hover:bg-cyan-500/5 transition-colors duration-150">Copy / Accept</button>
      </div>
      <div class="prose-container text-[12px] leading-relaxed" data-md="${encodeURIComponent(ch.markdown || '')}" id="ch-md-${card.id}-${ci}"></div>
    </div>`;
  }).join("");

  const sources = (card.sources || []).map(s => {
    return `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"
      class="text-[11px] text-slate-500 hover:text-cyan-400 transition-colors duration-150 underline underline-offset-2 decoration-slate-700 hover:decoration-cyan-500/50">${esc(s.name)}</a>`;
  }).join('<span class="text-slate-700 mx-1">·</span>');

  const dontDo = card.dont_do
    ? `<div class="flex items-start gap-2 bg-red-500/[0.08] border border-red-500/20 rounded px-3 py-2 mb-3">
        <span class="text-red-400 text-[11px] shrink-0 font-mono">⚠ 禁区</span>
        <p class="text-[11px] text-red-300/80 leading-relaxed font-body">${esc(card.dont_do)}</p>
      </div>` : "";

  return `
  <div class="card-item relative rounded-lg border border-white/[0.08] bg-navy-light overflow-hidden card-tinted-shadow"
       style="--i:${index}; animation: fadeSlideIn 0.3s ease-out both; animation-delay: calc(var(--i) * 0.06s)">
    <div class="absolute left-0 top-0 bottom-0 w-0.5 md:w-1 ${catCfg.bar}"></div>
    <div class="pl-3 pr-3 pt-2.5 pb-2 md:pl-4 md:pr-4 md:pt-4 md:pb-3">
      <div class="flex flex-col md:flex-row md:items-start md:justify-between gap-1.5 md:gap-3 mb-2">
        <div class="min-w-0">
          <h3 class="text-sm font-display font-semibold text-white leading-snug">${esc(card.title)}</h3>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium ${catCfg.color} ${catCfg.bg}">${esc(cat)}</span>
          <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${tCfg.color} ${tCfg.bg} ${tCfg.border}">${tCfg.label}</span>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-1.5 mb-3">
        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono ${sCfg.color} ${sCfg.bg}">${sCfg.label}</span>
        <span class="text-[10px] text-slate-500 font-mono">关联:${esc(card.relation || "")}</span>
        <span class="text-[10px] text-slate-500 font-mono">意图:${esc(card.intent || "")}</span>
      </div>
      <p class="text-[12px] text-slate-300 leading-relaxed font-body mb-3">${esc(card.summary || "")}</p>
      ${dontDo}
      <div class="flex flex-wrap gap-1.5 mb-2">${channelTabs}</div>
      ${channelPanels}
      <div class="flex flex-wrap items-center gap-x-0 gap-y-1 pt-2 border-t border-white/[0.05]">
        ${sources}
      </div>
    </div>
  </div>`;
}

// ── Channel Tab Toggle ──
function toggleChannelTab(cardId, idx) {
  const panel = document.getElementById(`ch-panel-${cardId}-${idx}`);
  const arrow = document.getElementById(`ch-arrow-${cardId}-${idx}`);
  const tab = document.getElementById(`ch-tab-${cardId}-${idx}`);
  if (!panel) return;

  const cardEl = panel.closest('.card-item');
  const wasHidden = panel.classList.contains("hidden");

  // Close all panels in this card
  cardEl.querySelectorAll('.ch-panel').forEach(p => p.classList.add("hidden"));
  cardEl.querySelectorAll('[id^="ch-arrow-"]').forEach(a => a.style.transform = "");
  // Reset all tabs: only swap color/bg, never touch padding/border/ring
  cardEl.querySelectorAll('.ch-tab').forEach(t => {
    t.dataset.active = "";
    t.classList.remove(
      'text-amber-300','text-emerald-300','text-cyan-300','text-violet-300','text-slate-300',
      'bg-amber-500/15','bg-emerald-500/15','bg-cyan-500/15','bg-violet-500/15','bg-slate-500/15'
    );
    t.classList.add('text-slate-400', 'bg-white/[0.05]');
  });

  if (wasHidden) {
    panel.classList.remove("hidden");
    arrow.style.transform = "rotate(180deg)";
    lazyRenderMd(`ch-md-${cardId}-${idx}`);
    // Apply active color only (no ring, no border, no padding change)
    const cards = _currentData ? (_currentData.cards || []) : [];
    const card = cards.find(c => c.id === cardId);
    if (card && card.channels[idx]) {
      const chCfg = CHANNEL_CONFIG[card.channels[idx].name];
      if (chCfg && chCfg.activeCls) {
        tab.classList.remove('text-slate-400', 'bg-white/[0.05]');
        chCfg.activeCls.split(' ').forEach(c => tab.classList.add(c));
        tab.dataset.active = "1";
      }
    }
  }
}

function lazyRenderMd(elId) {
  const mdEl = document.getElementById(elId);
  if (mdEl && !mdEl.dataset.rendered && mdEl.dataset.md) {
    mdEl.innerHTML = marked.parse(decodeURIComponent(mdEl.dataset.md));
    mdEl.dataset.rendered = "1";
  }
}

function autoExpandChannel(channelName) {
  document.querySelectorAll('.card-item').forEach(cardEl => {
    // Find the tab that matches the channel
    const tabs = cardEl.querySelectorAll('.ch-tab');
    tabs.forEach((tab, idx) => {
      if (tab.dataset.channel === channelName) {
        const cardId = tab.id.replace('ch-tab-', '').replace(/-\d+$/, '');
        const panel = document.getElementById(`ch-panel-${cardId}-${idx}`);
        if (panel && panel.classList.contains('hidden')) {
          toggleChannelTab(cardId, idx);
        }
      }
    });
  });
}

function copyPanelContent(mdElId) {
  const el = document.getElementById(mdElId);
  if (!el) return;
  const text = el.innerText || el.textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = el.closest('.ch-panel').querySelector('button[onclick^="copyAndAccept"]') || el.closest('.ch-panel').querySelector('button');
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = '✓ Copied';
      btn.classList.add('text-emerald-400', 'border-emerald-500/40', 'bg-emerald-500/10');
      btn.style.transform = 'scale(1.05)';
      setTimeout(() => { btn.style.transform = ''; }, 200);
      setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove('text-emerald-400', 'border-emerald-500/40', 'bg-emerald-500/10');
      }, 1500);
    }
  });
}

function copyAndAccept(cardId, chName, mdElId) {
  // 复制内容
  copyPanelContent(mdElId);
  // PostHog 埋点
  const dateStr = _currentData?.run_date || '';
  if (window.posthog) {
    posthog.capture('accept_channel', {
      date: dateStr,
      channel: chName,
      card_id: cardId,
      card_title: (_currentData?.cards || []).find(c => c.id === cardId)?.title || '',
      user_id: getBrowserId(),
    });
  }
}

// ── Sidebar ──
function renderSidebar(data) {
  let html = "";

  // Header markdown as gap signals
  if (data.header_markdown) {
    html += `<div class="rounded-lg border border-amber-500/20 bg-amber-500/5 overflow-hidden">
      <div class="px-4 py-3 border-b border-amber-500/15 flex items-center gap-2">
        <span class="text-amber-400">💡</span>
        <h3 class="text-xs font-display font-semibold text-amber-300">产品缺口信号</h3>
      </div>
      <div class="px-4 py-3 prose-container text-[11px]">${marked.parse(data.header_markdown)}</div>
    </div>`;
  }

  // Urgency legend
  html += `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">时效说明</h3>
    <div class="space-y-2">${Object.entries(URGENCY_CONFIG).map(([, v]) =>
      `<div class="flex items-center gap-2"><span class="text-[10px] font-mono font-medium ${v.color}">${v.label}</span></div>`
    ).join("")}</div>
  </div>`;

  // Category legend
  html += `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">热点类型</h3>
    <div class="space-y-2">${CATEGORY_ORDER.map(cat => {
      const cfg = CATEGORY_CONFIG[cat];
      return `<div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full ${cfg.bar}"></span><span class="text-[10px] font-mono ${cfg.color}">${cfg.label}</span></div>`;
    }).join("")}</div>
  </div>`;

  // Channel legend
  html += `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">渠道图例</h3>
    <div class="space-y-2">${Object.entries(CHANNEL_CONFIG).map(([, v]) =>
      `<div class="flex items-center gap-2"><span class="text-[10px] font-mono ${v.color}">${v.label}</span></div>`
    ).join("")}</div>
  </div>`;

  document.getElementById("sidebar-content").innerHTML = html;
}

// ── Helpers ──
function normalizeSite(site) {
  if (!site) return "Both";
  if (site.includes("HK") && site.includes("Global")) return "Both";
  if (site.includes("Both")) return "Both";
  if (site.includes("HK")) return "HK";
  if (site.includes("Global")) return "Global";
  return "Both";
}

function parseTimingKey(timing) {
  if (!timing) return "Day";
  const t = timing.toLowerCase();
  if (t.startsWith("flash") || t.includes("<4h")) return "Flash";
  if (t.startsWith("day") || t.includes("4-48h")) return "Day";
  if (t.startsWith("wave") || t.includes("2-7d")) return "Wave";
  if (t.startsWith("trend") || t.includes("1-4w")) return "Trend";
  return "Day";
}

function renderEmptyState() {
  return `<div class="text-center py-20 text-slate-500 font-body">
    <div class="text-4xl mb-3">🔍</div>
    <p class="text-sm">当前筛选条件下无行动包</p>
    <p class="text-xs text-slate-600 mt-1">等待今日数据处理完成</p>
  </div>`;
}

function esc(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ══════════════════════════════════════════════════════════════
// ── Competitor Dashboard ──
// ══════════════════════════════════════════════════════════════

let _currentCompData = null;
let filterRegion = "ALL";
let compTimeRange = 7; // 默认展示近 7 天

const REGION_CONFIG = {
  HK:     { label: '香港',    color: 'text-rose-400',    bg: 'bg-rose-500/10',    bar: 'bg-rose-500',    hex: '#f43f5e' },
  GLOBAL: { label: 'Global',  color: 'text-blue-400',    bg: 'bg-blue-500/10',    bar: 'bg-blue-500',    hex: '#3b82f6' },
  VN:     { label: '越南',    color: 'text-emerald-400', bg: 'bg-emerald-500/10', bar: 'bg-emerald-500', hex: '#10b981' },
  EU:     { label: '欧洲',    color: 'text-violet-400',  bg: 'bg-violet-500/10',  bar: 'bg-violet-500',  hex: '#8b5cf6' },
  ID:     { label: '印尼',    color: 'text-amber-400',   bg: 'bg-amber-500/10',   bar: 'bg-amber-500',   hex: '#f59e0b' },
  JP:     { label: '日本',    color: 'text-pink-400',    bg: 'bg-pink-500/10',    bar: 'bg-pink-500',    hex: '#ec4899' },
  BROKER: { label: '券商',    color: 'text-slate-400',   bg: 'bg-slate-500/10',   bar: 'bg-slate-500',   hex: '#64748b' },
};

const IMPORTANCE_CONFIG = {
  high:   { label: '重要', color: 'text-red-400',   bg: 'bg-red-500/10',   dot: 'bg-red-500' },
  medium: { label: '一般', color: 'text-amber-400', bg: 'bg-amber-500/10', dot: 'bg-amber-500' },
  low:    { label: '日常', color: 'text-slate-400', bg: 'bg-slate-500/10', dot: 'bg-slate-500' },
};

const CATEGORY_ICONS = {
  '新币上线': '🪙', '产品更新': '🔧', '活动推广': '🎯', '合作伙伴': '🤝',
  '监管合规': '📋', '融资/IPO': '💰', '人事变动': '👤', '其他': '📌',
};

const CATEGORY_STYLE = {
  '新币上线': { dot: 'bg-yellow-500' },
  '产品更新': { dot: 'bg-cyan-500' },
  '活动推广': { dot: 'bg-green-500' },
  '合作伙伴': { dot: 'bg-blue-500' },
  '监管合规': { dot: 'bg-orange-500' },
  '融资/IPO': { dot: 'bg-purple-500' },
  '人事变动': { dot: 'bg-pink-500' },
  '其他':     { dot: 'bg-slate-500' },
};

async function loadCompetitors() {
  showSkeleton();
  try {
    const res = await fetch(COMP_API.today);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    _currentCompData = data;
    renderCompetitorDashboard(data);
  } catch (e) {
    console.error("Failed to load competitors:", e);
    document.getElementById("card-sections").innerHTML =
      '<div class="text-center py-20 text-slate-500"><div class="text-4xl mb-3">🏢</div><p class="text-sm">暂无竞品数据</p><p class="text-xs text-slate-600 mt-1">运行 python main.py fetch 抓取竞品数据</p></div>';
    document.getElementById("hero-stats").innerHTML = '';
    document.getElementById("sidebar-content").innerHTML = '';
  }
}

function setFilterRegion(v) {
  filterRegion = v;
  if (_currentCompData) renderCompetitorDashboard(_currentCompData);
}

function setCompTimeRange(days) {
  compTimeRange = days;
  if (_currentCompData) renderCompetitorDashboard(_currentCompData);
}

function _filterCompByTimeRange(competitors) {
  if (!compTimeRange) return competitors;
  const now = new Date();
  const cutoff = new Date(now.getTime() - compTimeRange * 24 * 60 * 60 * 1000);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  return competitors.map(c => {
    const filtered = (c.events || []).filter(e => !e.date || e.date >= cutoffStr);
    return { ...c, events: filtered };
  });
}

function renderCompetitorDashboard(data) {
  const rawCompetitors = data.competitors || [];
  const competitors = _filterCompByTimeRange(rawCompetitors);

  // Header — show displayed time range
  const now = new Date();
  const fromDate = new Date(now.getTime() - compTimeRange * 24 * 60 * 60 * 1000).toISOString().slice(0, 10);
  const toDate = now.toISOString().slice(0, 10);
  document.getElementById("header-date").textContent = `竞品动态 ${fromDate} ~ ${toDate}`;

  // Time range buttons
  const timeRanges = [7, 14, 30];
  const timeBtns = timeRanges.map(d => {
    const isActive = compTimeRange === d;
    const base = 'text-xs font-medium px-3 py-1.5 rounded-md transition-all duration-200 cursor-pointer select-none';
    const activeStyle = 'bg-cyan-500/15 text-cyan-400 ring-1 ring-inset ring-cyan-500/30 shadow-sm';
    const inactiveStyle = 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.06]';
    return `<button onclick="setCompTimeRange(${d})" class="${base} ${isActive ? activeStyle : inactiveStyle}">${d}天</button>`;
  }).join("");

  // Region filter buttons
  const regions = ["ALL", ...Object.keys(REGION_CONFIG)];
  const regionBtns = regions.map(r => {
    const cfg = r !== "ALL" ? REGION_CONFIG[r] : null;
    const label = r === "ALL" ? "全部" : cfg.label;
    const isActive = filterRegion === r;
    const base = 'text-xs font-medium px-3 py-1.5 rounded-md transition-all duration-200 cursor-pointer select-none';
    const active = cfg
      ? `${cfg.color} ${cfg.bg} ring-1 ring-inset ring-white/10 shadow-sm`
      : 'bg-white/[0.12] text-white ring-1 ring-inset ring-white/15 shadow-sm';
    const inactive = 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.06]';
    return `<button onclick="setFilterRegion('${r}')" class="${base} ${isActive ? active : inactive}">${label}</button>`;
  }).join("");
  document.getElementById("sub-tabs-competitors").innerHTML =
    '<div class="flex flex-wrap items-center gap-3">'
    + '<div class="flex items-center gap-1.5"><span class="text-xs text-slate-500 font-medium mr-1">时间</span>' + timeBtns + '</div>'
    + '<div class="w-px h-4 bg-white/10"></div>'
    + '<div class="flex items-center gap-1.5"><span class="text-xs text-slate-500 font-medium mr-1">区域</span>' + regionBtns + '</div>'
    + '</div>';

  // Split active / inactive, apply region filter
  const active = competitors.filter(c => (c.events || []).length > 0);
  const inactive = competitors.filter(c => (c.events || []).length === 0);

  const filteredActive = filterRegion === "ALL"
    ? active
    : active.filter(c => (c.region || "HK") === filterRegion);
  const filteredInactive = filterRegion === "ALL"
    ? inactive
    : inactive.filter(c => (c.region || "HK") === filterRegion);

  // Sort active by event count desc
  filteredActive.sort((a, b) => (b.events || []).length - (a.events || []).length);

  // Hero stats — computed from filtered set
  const filteredAll = [...filteredActive, ...filteredInactive];
  const filteredEvents = filteredAll.flatMap(c => c.events || []);
  const highCount = filteredEvents.filter(e => e.importance === 'high').length;
  const medCount = filteredEvents.filter(e => e.importance === 'medium').length;
  document.getElementById("hero-stats").innerHTML = `
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-white">${filteredAll.length}</div><div class="text-[10px] text-slate-500 font-mono">竞品</div></div>
    <div class="w-px h-6 md:h-8 bg-white/10"></div>
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-cyan-400">${filteredActive.length}</div><div class="text-[10px] text-slate-500 font-mono">有动态</div></div>
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-red-400">${highCount}</div><div class="text-[10px] text-slate-500 font-mono">重要</div></div>
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-amber-400">${medCount}</div><div class="text-[10px] text-slate-500 font-mono">一般</div></div>`;

  document.getElementById("filter-count").textContent = `${filteredAll.length} / ${competitors.length} 家`;

  // Render columns
  let html = '';
  if (filteredActive.length > 0) {
    const cols = filteredActive.map((comp, i) => renderCompetitorColumn(comp, i)).join("");
    html += `<div class="competitor-columns">${cols}</div>`;
  }

  // Inactive competitors as tags
  if (filteredInactive.length > 0) {
    const tags = filteredInactive.map(c => {
      const rCfg = REGION_CONFIG[c.region] || REGION_CONFIG.HK;
      return `<span class="inline-flex items-center gap-1 text-[10px] font-mono text-slate-600 px-2 py-1 rounded border border-white/[0.05] bg-white/[0.02]"><span class="${rCfg.color}">${esc(c.region)}</span> ${esc(c.name)}</span>`;
    }).join("");
    html += `<div class="mt-4"><div class="text-[10px] text-slate-500 font-mono mb-2">近${compTimeRange}日无动态 (${filteredInactive.length})</div><div class="flex flex-wrap gap-2">${tags}</div></div>`;
  }

  if (!html) html = '<div class="text-center py-20 text-slate-500"><p class="text-sm">该区域暂无竞品数据</p></div>';

  document.getElementById("card-sections").innerHTML = html;

  // Sidebar
  renderCompetitorSidebar(competitors);

  const compFooterDate = `${fromDate} ~ ${toDate}`;
  document.getElementById("footer-left").textContent = `OSL Growth Intelligence · ${compFooterDate}`;
  document.getElementById("footer-right").textContent = `竞品监控 · ${competitors.length} 家竞品`;
}

function renderCompetitorColumn(comp, index) {
  const events = (comp.events || []).slice();
  const regionCfg = REGION_CONFIG[comp.region] || REGION_CONFIG.HK;

  // Sort by date desc, then importance
  events.sort((a, b) => {
    const da = a.date || '';
    const db = b.date || '';
    if (db > da) return 1;
    if (da > db) return -1;
    const impOrder = { high: 3, medium: 2, low: 1 };
    return (impOrder[b.importance] || 0) - (impOrder[a.importance] || 0);
  });

  const eventsHtml = events.map(e => renderEventItem(e)).join("");

  // Logo with fallback to first letter avatar
  const logoUrl = comp.logo || '';
  const logoHtml = logoUrl
    ? `<img src="${esc(logoUrl)}" alt="" class="w-5 h-5 rounded-full object-cover bg-white/10 shrink-0" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'">`
      + `<span class="w-5 h-5 rounded-full bg-white/10 items-center justify-center text-[10px] font-bold text-white shrink-0" style="display:none">${esc(comp.name[0])}</span>`
    : `<span class="w-5 h-5 rounded-full bg-white/10 flex items-center justify-center text-[10px] font-bold text-white shrink-0">${esc(comp.name[0])}</span>`;

  return `<div class="competitor-column" style="--i:${index}; border-top: 2px solid ${regionCfg.hex}; animation: fadeSlideIn 0.3s ease-out both; animation-delay: calc(var(--i) * 0.06s)">
    <div class="col-header relative" style="background: linear-gradient(135deg, ${regionCfg.hex}0a, transparent)">
      <div class="absolute left-0 top-0 bottom-0 w-[3px] rounded-l ${regionCfg.bar}"></div>
      <div class="flex items-center justify-between gap-2 mb-1.5 pl-2">
        <div class="flex items-center gap-2 min-w-0">
          ${logoHtml}
          <h3 class="text-sm font-display font-semibold text-white truncate">${esc(comp.name)}</h3>
          <span class="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono ${regionCfg.color} ${regionCfg.bg}">${esc(comp.region)}</span>
        </div>
        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono ${regionCfg.color} ${regionCfg.bg} shrink-0">${events.length} 事件</span>
      </div>
      <p class="text-[11px] text-slate-400 font-body leading-relaxed line-clamp-2 pl-2">${esc(comp.summary || "")}</p>
    </div>
    <div class="col-body space-y-2">
      ${eventsHtml}
    </div>
  </div>`;
}

function renderEventItem(event) {
  const impCfg = IMPORTANCE_CONFIG[event.importance] || IMPORTANCE_CONFIG.low;
  const catStyle = CATEGORY_STYLE[event.category] || CATEGORY_STYLE['其他'];
  const sources = (event.sources || []).map(s =>
    `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" class="text-[10px] text-slate-500 hover:text-cyan-400 transition-colors underline underline-offset-2 decoration-slate-700 hover:decoration-cyan-500/50">${esc(s.name)}</a>`
  ).join('<span class="text-slate-700 mx-0.5">·</span>');

  const summaryId = 'comp-ev-' + Math.random().toString(36).slice(2, 8);
  const dateStr = event.date || '';
  const dateLabel = dateStr ? dateStr.slice(5) : '';

  return `<div class="border border-white/[0.06] rounded-md bg-[#0f1623] p-3">
    <div class="flex items-start justify-between gap-2 mb-1.5">
      <div class="flex items-center gap-1.5 min-w-0">
        <span class="w-2 h-2 rounded-full ${catStyle.dot} shrink-0 mt-0.5"></span>
        <span class="text-[11px] font-medium text-white truncate">${esc(event.title)}</span>
      </div>
      <div class="flex items-center gap-1 shrink-0">
        <span class="text-[9px] font-mono px-1.5 py-0.5 rounded ${impCfg.color} ${impCfg.bg}">${impCfg.label}</span>
        <span class="text-[9px] font-mono text-slate-600">${esc(event.category)}</span>
        ${dateLabel ? `<span class="text-[9px] font-mono text-slate-600">${esc(dateLabel)}</span>` : ''}
      </div>
    </div>
    <div class="prose-container text-[11px] leading-relaxed text-slate-300" data-md="${encodeURIComponent(event.summary || '')}" id="${summaryId}"></div>
    ${sources ? `<div class="flex flex-wrap items-center gap-x-0 gap-y-1 mt-2 pt-1.5 border-t border-white/[0.04]">${sources}</div>` : ""}
  </div>`;
}


function renderCompetitorSidebar(competitors) {
  const allEvents = competitors.flatMap(c => c.events || []);
  const byCat = {};
  allEvents.forEach(e => {
    const cat = e.category || '其他';
    byCat[cat] = (byCat[cat] || 0) + 1;
  });

  let html = `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">事件分类统计</h3>
    <div class="space-y-2">${Object.entries(byCat).sort((a, b) => b[1] - a[1]).map(([cat, count]) =>
      `<div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400"><span class="inline-block w-1.5 h-1.5 rounded-full ${(CATEGORY_STYLE[cat] || CATEGORY_STYLE['其他']).dot} mr-1 align-middle"></span>${cat}</span><span class="text-[10px] font-mono text-slate-500">${count}</span></div>`
    ).join("")}</div>
  </div>`;

  // Region breakdown
  const byRegion = {};
  competitors.forEach(c => {
    const r = c.region || 'HK';
    if (!byRegion[r]) byRegion[r] = { total: 0, active: 0 };
    byRegion[r].total++;
    if ((c.events || []).length > 0) byRegion[r].active++;
  });

  html += `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">区域覆盖</h3>
    <div class="space-y-2">${Object.entries(byRegion).map(([r, v]) => {
      const cfg = REGION_CONFIG[r] || REGION_CONFIG.HK;
      return `<div class="flex items-center justify-between"><span class="text-[10px] font-mono ${cfg.color}">${cfg.label}</span><span class="text-[10px] font-mono text-slate-500">${v.active}/${v.total}</span></div>`;
    }).join("")}</div>
  </div>`;

  // Importance legend
  html += `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">重要性说明</h3>
    <div class="space-y-2">${Object.entries(IMPORTANCE_CONFIG).map(([, v]) =>
      `<div class="flex items-center gap-2"><span class="w-2 h-2 rounded-full ${v.dot}"></span><span class="text-[10px] font-mono ${v.color}">${v.label}</span></div>`
    ).join("")}</div>
  </div>`;

  document.getElementById("sidebar-content").innerHTML = html;
}

// Lazy render markdown for competitor events adate
const _compMdObserver = new MutationObserver(() => {
  document.querySelectorAll('[id^="comp-ev-"]').forEach(el => {
    if (!el.dataset.rendered && el.dataset.md) {
      el.innerHTML = marked.parse(decodeURIComponent(el.dataset.md));
      el.dataset.rendered = "1";
    }
  });
});
_compMdObserver.observe(document.body, { childList: true, subtree: true });

// ── Sources (信源) ──────────────────────────────────────────────

async function loadSources() {
  showSkeleton();
  try {
    const [srcRes, compRes] = await Promise.all([
      fetch("./config/sources.yaml"),
      fetch("./config/competitors.yaml"),
    ]);
    if (!srcRes.ok) throw new Error(`sources.yaml HTTP ${srcRes.status}`);
    if (!compRes.ok) throw new Error(`competitors.yaml HTTP ${compRes.status}`);
    const srcYaml = jsyaml.load(await srcRes.text());
    const compYaml = jsyaml.load(await compRes.text());
    const data = {
      rss: (srcYaml && srcYaml.rss) || [],
      twitter: (srcYaml && srcYaml.twitter) || {},
      competitors: (compYaml && compYaml.competitors) || [],
    };
    renderSourcesDashboard(data);
  } catch (e) {
    console.error("Failed to load sources:", e);
    document.getElementById("card-sections").innerHTML =
      '<div class="text-center py-20 text-slate-500"><p class="text-sm">无法加载信源配置</p></div>';
    document.getElementById("hero-stats").innerHTML = '';
    document.getElementById("sidebar-content").innerHTML = '';
  }
}


function renderSourcesDashboard(data) {
  const rssList = data.rss || [];
  const twitterAccounts = (data.twitter && data.twitter.accounts) || [];
  const competitors = data.competitors || [];

  const compTwitter = competitors.reduce((n, c) => n + (c.twitter || []).length, 0);
  const compRss = competitors.reduce((n, c) => n + (c.rss || []).length, 0);
  const compWeb = competitors.reduce((n, c) => n + (c.web || []).length, 0);
  const compApi = competitors.reduce((n, c) => n + (c.api || []).length, 0);
  const compChannels = compTwitter + compRss + compWeb + compApi;

  document.getElementById("header-date").textContent = "信源配置";
  document.getElementById("header-subtitle").textContent = `热点 ${rssList.length + twitterAccounts.length} 源 · 竞品 ${competitors.length} 家 ${compChannels} 渠道`;
  document.getElementById("filter-count").textContent = '';

  document.getElementById("hero-stats").innerHTML = `
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-orange-400">${rssList.length}</div><div class="text-[10px] text-slate-500 font-mono">RSS</div></div>
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-sky-400">${twitterAccounts.length}</div><div class="text-[10px] text-slate-500 font-mono">Twitter</div></div>
    <div class="w-px h-6 md:h-8 bg-white/10"></div>
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-violet-400">${competitors.length}</div><div class="text-[10px] text-slate-500 font-mono">竞品</div></div>
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-emerald-400">${compChannels}</div><div class="text-[10px] text-slate-500 font-mono">监测渠道</div></div>`;

  let html = '';
  html += renderSourceSection('热点 · RSS 订阅源', 'bg-orange-500', 'text-orange-400',
    rssList.map((s, i) => renderRssSourceCard(s, i)).join(''));
  html += renderSourceSection('热点 · Twitter 账号', 'bg-sky-500', 'text-sky-400',
    twitterAccounts.map((handle, i) => renderTwitterSourceCard(handle, i)).join(''));

  if (competitors.length > 0) {
    const COMP_REGION_CFG = {
      HK:     { label: '香港',   color: 'text-rose-400',    bar: 'bg-rose-500' },
      GLOBAL: { label: 'Global', color: 'text-blue-400',    bar: 'bg-blue-500' },
      JP:     { label: '日本',   color: 'text-pink-400',    bar: 'bg-pink-500' },
      VN:     { label: '越南',   color: 'text-teal-400',    bar: 'bg-teal-500' },
      EU:     { label: '欧洲',   color: 'text-indigo-400',  bar: 'bg-indigo-500' },
      ID:     { label: '印尼',   color: 'text-amber-400',   bar: 'bg-amber-500' },
      BROKER: { label: '券商',   color: 'text-slate-400',   bar: 'bg-slate-500' },
    };
    const regionOrder = ["HK", "GLOBAL", "JP", "VN", "EU", "ID", "BROKER"];
    const byRegion = {};
    for (const c of competitors) {
      const r = c.region || "HK";
      if (!byRegion[r]) byRegion[r] = [];
      byRegion[r].push(c);
    }
    for (const region of regionOrder) {
      const comps = byRegion[region];
      if (!comps || comps.length === 0) continue;
      const cfg = COMP_REGION_CFG[region] || COMP_REGION_CFG.HK;
      html += renderSourceSection('竞品 · ' + cfg.label, cfg.bar, cfg.color,
        comps.map((c, i) => renderCompetitorSourceCard(c, i)).join(''));
    }
  }

  document.getElementById("card-sections").innerHTML = html;

  const zhCount = rssList.filter(s => s.lang === 'zh').length;
  const enCount = rssList.filter(s => s.lang === 'en').length;
  document.getElementById("sidebar-content").innerHTML = `
    <div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
      <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">热点信源</h3>
      <div class="space-y-2">
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">RSS 源</span><span class="text-[10px] font-mono text-orange-400">${rssList.length}</span></div>
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">Twitter</span><span class="text-[10px] font-mono text-sky-400">${twitterAccounts.length}</span></div>
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">中文源</span><span class="text-[10px] font-mono text-slate-300">${zhCount}</span></div>
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">英文源</span><span class="text-[10px] font-mono text-slate-300">${enCount}</span></div>
      </div>
    </div>
    <div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
      <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">竞品监测</h3>
      <div class="space-y-2">
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">竞品数</span><span class="text-[10px] font-mono text-violet-400">${competitors.length}</span></div>
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">Twitter</span><span class="text-[10px] font-mono text-sky-400">${compTwitter}</span></div>
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">RSS</span><span class="text-[10px] font-mono text-orange-400">${compRss}</span></div>
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">Web 爬取</span><span class="text-[10px] font-mono text-emerald-400">${compWeb}</span></div>
        <div class="flex items-center justify-between"><span class="text-[10px] font-mono text-slate-400">API</span><span class="text-[10px] font-mono text-cyan-400">${compApi}</span></div>
      </div>
    </div>`;

  document.getElementById("footer-left").textContent = 'OSL Growth Intelligence';
  document.getElementById("footer-right").textContent = `信源配置 · ${rssList.length + twitterAccounts.length} 热点源 · ${competitors.length} 竞品`;
}

function renderSourceSection(title, barColor, textColor, cardsHtml) {
  return `<section class="mb-6">
    <div class="flex items-center gap-3 mb-4">
      <span class="h-3 w-3 rounded-full ${barColor} shrink-0"></span>
      <h2 class="text-sm font-display font-bold ${textColor} tracking-wide uppercase">${title}</h2>
      <div class="flex-1 h-px bg-white/[0.08]"></div>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      ${cardsHtml}
    </div>
  </section>`;
}

function renderRssSourceCard(source, index) {
  const langBadge = source.lang === 'zh'
    ? '<span class="text-[9px] font-mono px-1.5 py-0.5 rounded text-amber-300 bg-amber-500/10">中文</span>'
    : '<span class="text-[9px] font-mono px-1.5 py-0.5 rounded text-emerald-300 bg-emerald-500/10">EN</span>';
  return `
  <div class="relative rounded-lg border border-white/[0.08] bg-navy-light overflow-hidden card-tinted-shadow"
       style="animation: fadeSlideIn 0.3s ease-out both; animation-delay: ${index * 0.04}s">
    <div class="absolute left-0 top-0 bottom-0 w-1 bg-orange-500"></div>
    <div class="pl-4 pr-4 py-3">
      <div class="flex items-center justify-between gap-2">
        <span class="text-[12px] font-display font-semibold text-white truncate">${esc(source.name)}</span>
        ${langBadge}
      </div>
      <a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer"
         class="text-[10px] text-slate-500 hover:text-cyan-400 transition-colors truncate block mt-1 font-mono">${esc(source.url)}</a>
    </div>
  </div>`;
}

function renderTwitterSourceCard(handle, index) {
  return `
  <div class="relative rounded-lg border border-white/[0.08] bg-navy-light overflow-hidden card-tinted-shadow"
       style="animation: fadeSlideIn 0.3s ease-out both; animation-delay: ${index * 0.04}s">
    <div class="absolute left-0 top-0 bottom-0 w-1 bg-sky-500"></div>
    <div class="pl-4 pr-4 py-3">
      <div class="flex items-center gap-2">
        <span class="text-[12px] font-display font-semibold text-white">@${esc(handle)}</span>
      </div>
      <a href="https://x.com/${esc(handle)}" target="_blank" rel="noopener noreferrer"
         class="text-[10px] text-slate-500 hover:text-cyan-400 transition-colors block font-mono">x.com/${esc(handle)}</a>
    </div>
  </div>`;
}

function renderCompetitorSourceCard(comp, index) {
  const channels = [];
  (comp.twitter || []).forEach(h => channels.push({ type: 'Twitter', label: '@' + h, url: 'https://x.com/' + h }));
  (comp.rss || []).forEach(r => channels.push({ type: 'RSS', label: r.name || r.url, url: r.url }));
  (comp.web || []).forEach(w => channels.push({ type: 'Web', label: w.type || 'web', url: w.url }));
  (comp.api || []).forEach(a => channels.push({ type: 'API', label: 'API', url: a.url }));

  const tierBadge = `<span class="text-[9px] font-mono px-1.5 py-0.5 rounded text-slate-300 bg-white/[0.06]">T${comp.tier || '?'}</span>`;
  const channelHtml = channels.length > 0
    ? channels.map(ch => {
        const colors = { Twitter: 'text-sky-400', RSS: 'text-orange-400', Web: 'text-emerald-400', API: 'text-cyan-400' };
        const color = colors[ch.type] || 'text-slate-400';
        return `<a href="${esc(ch.url)}" target="_blank" rel="noopener noreferrer" class="text-[9px] font-mono ${color} hover:underline">${esc(ch.type)}: ${esc(ch.label)}</a>`;
      }).join('<span class="text-slate-600 mx-1">&middot;</span>')
    : '<span class="text-[9px] font-mono text-slate-600">仅媒体关键词匹配</span>';

  return `
  <div class="relative rounded-lg border border-white/[0.08] bg-navy-light overflow-hidden card-tinted-shadow"
       style="animation: fadeSlideIn 0.3s ease-out both; animation-delay: ${index * 0.04}s">
    <div class="absolute left-0 top-0 bottom-0 w-1 bg-violet-500"></div>
    <div class="pl-4 pr-4 py-3">
      <div class="flex items-center justify-between gap-2 mb-1.5">
        <span class="text-[12px] font-display font-semibold text-white">${esc(comp.name)}</span>
        ${tierBadge}
      </div>
      <div class="flex flex-wrap items-center gap-x-0 gap-y-1">${channelHtml}</div>
    </div>
  </div>`;
}

// ── Sentiment (舆情监控) ──

const PLATFORM_CONFIG = {
  twitter:    { label: 'Twitter',  color: 'text-sky-400',    bg: 'bg-sky-500/15',    border: 'border-sky-500/30' },
  reddit:     { label: 'Reddit',   color: 'text-orange-400', bg: 'bg-orange-500/15', border: 'border-orange-500/30' },
  youtube:    { label: 'YouTube',  color: 'text-red-400',    bg: 'bg-red-500/15',    border: 'border-red-500/30' },
};

let _currentSentimentFilter = "ALL";

async function loadSentiment() {
  showSkeleton();
  try {
    const res = await fetch(SENT_API.today);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    let data = await res.json();
    if (Array.isArray(data)) {
      data = { run_date: "", total_raw: 0, items: data };
    }
    renderSentimentDashboard(data);
  } catch (e) {
    console.error("Failed to load sentiment:", e);
    document.getElementById("card-sections").innerHTML =
      '<div class="text-center py-20 text-slate-500"><div class="text-4xl mb-3">&#128226;</div><p class="text-sm">暂无舆情数据</p><p class="text-xs text-slate-600 mt-1">运行 python main.py fetch 抓取舆情数据</p></div>';
    document.getElementById("hero-stats").innerHTML = '';
    document.getElementById("sidebar-content").innerHTML = '';
  }
}

function renderSentimentDashboard(data) {
  const items = data.items || [];
  const totalRaw = data.total_raw || 0;

  const sentDateLabel = data.date_range
    ? `舆情监控 ${data.date_range.from} ~ ${data.date_range.to}`
    : (data.run_date ? `舆情数据 ${data.run_date}` : "");
  document.getElementById("header-date").textContent = sentDateLabel;

  const highCount = items.filter(i => i.importance === 'high').length;
  document.getElementById("hero-stats").innerHTML = `
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-white">${totalRaw}</div><div class="text-[10px] text-slate-500 font-mono">原始数据</div></div>
    <div class="w-px h-6 md:h-8 bg-white/10"></div>
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-cyan-400">${items.length}</div><div class="text-[10px] text-slate-500 font-mono">有效提及</div></div>
    <div class="text-center"><div class="text-lg md:text-2xl font-mono tabular-nums font-bold text-red-400">${highCount}</div><div class="text-[10px] text-slate-500 font-mono">重要</div></div>`;

  const IMP_CFG = {
    high:   { label: '重要', color: 'text-red-400',   bg: 'bg-red-500/15',   border: 'border-red-500/30' },
    medium: { label: '一般', color: 'text-amber-400', bg: 'bg-amber-500/15', border: 'border-amber-500/30' },
    low:    { label: '日常', color: 'text-slate-400',  bg: 'bg-slate-500/15', border: 'border-slate-500/30' },
  };
  const levels = ["ALL", "high"];
  const filterBtns = levels.map(l => {
    const cfg = l !== "ALL" ? IMP_CFG[l] : null;
    const label = l === "ALL" ? "全部" : cfg.label;
    const isActive = _currentSentimentFilter === l;
    const base = 'text-xs font-medium px-3 py-1.5 rounded-md transition-all duration-200 cursor-pointer select-none';
    const active = cfg
      ? `${cfg.color} ${cfg.bg} ring-1 ring-inset ring-white/10 shadow-sm`
      : 'bg-white/[0.12] text-white ring-1 ring-inset ring-white/15 shadow-sm';
    const inactive = 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.06]';
    return `<button onclick="setSentimentFilter('${l}')" class="${base} ${isActive ? active : inactive}">${label}</button>`;
  }).join("");
  document.getElementById("sub-tabs-sentiment").innerHTML =
    '<div class="flex items-center gap-1.5"><span class="text-xs text-slate-500 font-medium mr-1">重要性</span>' + filterBtns + '</div>';

  const filtered = _currentSentimentFilter === "ALL"
    ? items
    : items.filter(i => i.importance === _currentSentimentFilter);

  document.getElementById("filter-count").textContent = `${filtered.length} / ${items.length} 条`;

  if (!filtered.length) {
    document.getElementById("card-sections").innerHTML =
      '<div class="text-center py-20 text-slate-500"><p class="text-sm">暂无匹配的舆情数据</p></div>';
  } else {
    document.getElementById("card-sections").innerHTML =
      '<div class="space-y-3">' + filtered.map((item, i) => renderSentimentCard(item, i)).join("") + '</div>';
  }

  document.getElementById("sidebar-content").innerHTML = '';
  const sentFooterDate = data.date_range
    ? `${data.date_range.from} ~ ${data.date_range.to}`
    : (data.run_date || "");
  document.getElementById("footer-left").textContent = `OSL Growth Intelligence · ${sentFooterDate}`;
  document.getElementById("footer-right").textContent = `舆情监控 · ${items.length} 条有效提及（原始 ${totalRaw} 条）`;
  window._sentimentData = data;
}

function setSentimentFilter(v) {
  _currentSentimentFilter = v;
  if (window._sentimentData) renderSentimentDashboard(window._sentimentData);
}

function renderSentimentCard(item, index) {
  const IMP_CFG = {
    high:   { label: '重要', color: 'text-red-400',   bg: 'bg-red-500/15',   border: 'border-red-500/30' },
    medium: { label: '一般', color: 'text-amber-400', bg: 'bg-amber-500/15', border: 'border-amber-500/30' },
    low:    { label: '日常', color: 'text-slate-400',  bg: 'bg-slate-500/15', border: 'border-slate-500/30' },
  };
  const impCfg = IMP_CFG[item.importance] || IMP_CFG.low;
  const sources = item.sources || [];
  const timeStr = item.published_at ? new Date(item.published_at).toLocaleString("zh-CN", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }) : "";

  const sourcesHtml = sources.map(s => {
    const pCfg = PLATFORM_CONFIG[s.platform] || { label: s.platform || '', color: 'text-slate-400' };
    const authorStr = s.author ? ` ${esc(s.author)}` : '';
    return s.url
      ? `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer" class="text-[9px] font-mono ${pCfg.color} hover:underline">${pCfg.label || esc(s.platform)}${authorStr}</a>`
      : `<span class="text-[9px] font-mono ${pCfg.color}">${pCfg.label || esc(s.platform)}${authorStr}</span>`;
  }).join('<span class="text-slate-600 mx-1">&middot;</span>');

  return `
  <div class="relative rounded-lg border border-white/[0.08] bg-navy-light overflow-hidden card-tinted-shadow"
       style="--i:${index}; animation: fadeSlideIn 0.3s ease-out both; animation-delay: calc(var(--i) * 0.03s)">
    <div class="absolute left-0 top-0 bottom-0 w-1 ${impCfg.bg.replace('/15', '')}"></div>
    <div class="pl-4 pr-4 py-3">
      <div class="flex items-center gap-2 mb-1.5">
        <span class="text-[9px] font-mono ${impCfg.color} ${impCfg.bg} ${impCfg.border} border px-1.5 py-0.5 rounded">${impCfg.label}</span>
        <span class="text-[9px] font-mono text-slate-500 bg-white/[0.04] px-1.5 py-0.5 rounded">${esc(item.category || '')}</span>
        ${timeStr ? `<span class="text-[9px] font-mono text-slate-600 ml-auto">${timeStr}</span>` : ''}
      </div>
      <h3 class="text-[13px] font-medium text-white mb-1 leading-snug">${esc(item.title)}</h3>
      ${item.summary ? `<div class="text-[11px] text-slate-400 leading-relaxed prose-container">${marked.parse(item.summary)}</div>` : ""}
      <div class="flex flex-wrap items-center gap-x-1 gap-y-1 mt-2">${sourcesHtml}</div>
    </div>
  </div>`;
}
