// ── Config ──
const REFRESH_INTERVAL = 5 * 60 * 1000;
let currentSection = "hotspot"; // "hotspot" | "competitors"
let currentTab = "today";
let filterPriority = "ALL";
let filterChannel = "ALL";
let filterSite = "ALL";
let _currentData = null;
let refreshTimer = null;
let _compExpandedSet = new Set();

// Auto-detect: static site (Vercel) vs local FastAPI
const IS_STATIC = !window.location.port || window.location.hostname !== 'localhost';
const API = IS_STATIC
  ? { today: "./data/latest.json", dates: "./data/dates.json", history: (d) => `./data/${d}.json`,
      compToday: "./data/competitors/latest.json", compDates: "./data/competitors/dates.json", compHistory: (d) => `./data/competitors/${d}.json` }
  : { today: "/api/today", dates: "/api/dates", history: (d) => `/api/history?date=${d}`,
      compToday: "/api/competitors/today", compDates: "/api/competitors/dates", compHistory: (d) => `/api/competitors/history?date=${d}` };

let _compData = null;
let compFilterName = "ALL";
let compFilterRegion = "ALL";

// ── Design Tokens ──
const URGENCY_CONFIG = {
  Flash: { label: 'Flash <4h', color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
  Day:   { label: 'Day 4-48h', color: 'text-amber-400', bg: 'bg-amber-500/10', border: 'border-amber-500/30' },
  Wave:  { label: 'Wave 2-7d', color: 'text-emerald-400', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30' },
  Trend: { label: 'Trend 1-4w', color: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
};

const PRIORITY_CONFIG = {
  P0: { label: 'P0 当日启动', color: 'text-red-400', bg: 'bg-red-500/15', bar: 'bg-red-500', divider: 'bg-red-500/20' },
  P1: { label: 'P1 计划跟进', color: 'text-amber-400', bg: 'bg-amber-500/15', bar: 'bg-amber-500', divider: 'bg-amber-500/20' },
  P2: { label: 'P2 轻量参与', color: 'text-slate-400', bg: 'bg-slate-500/15', bar: 'bg-slate-500', divider: 'bg-slate-500/20' },
};

const CHANNEL_CONFIG = {
  'Paid Ads':            { label: 'Paid Ads',    icon: '📣', color: 'text-amber-300',  bg: 'bg-amber-500/15',  activeCls: 'text-amber-300 bg-amber-500/15' },
  'SEO':                 { label: 'SEO',         icon: '🔍', color: 'text-emerald-300', bg: 'bg-emerald-500/15', activeCls: 'text-emerald-300 bg-emerald-500/15' },
  '站内运营 / 用户触达': { label: '站内运营/触达', icon: '🖥️', color: 'text-cyan-300',   bg: 'bg-cyan-500/15',   activeCls: 'text-cyan-300 bg-cyan-500/15' },
  '社区':                { label: '社区运营',     icon: '💬', color: 'text-violet-300', bg: 'bg-violet-500/15', activeCls: 'text-violet-300 bg-violet-500/15' },
};

const SITE_CONFIG = {
  HK:     { label: 'HK 站',      color: 'text-sky-300',    bg: 'bg-sky-500/15' },
  Global: { label: 'Global 站',  color: 'text-indigo-300', bg: 'bg-indigo-500/15' },
  Both:   { label: 'HK + Global', color: 'text-teal-300',  bg: 'bg-teal-500/15' },
};

const EXEC_CONFIG = {
  A: { label: 'A 级 2-4h',  color: 'text-green-400' },
  B: { label: 'B 级 1-2d',  color: 'text-yellow-400' },
  C: { label: 'C 级 2-3d',  color: 'text-orange-400' },
  D: { label: 'D 级 纯内容', color: 'text-slate-400' },
};

// ── Bootstrap ──
document.addEventListener("DOMContentLoaded", () => {
  setupNav();
  loadToday();
  refreshTimer = setInterval(() => { if (currentSection === 'hotspot') loadToday(); }, REFRESH_INTERVAL);
});

function _activateBtn(btn, allSelector) {
  document.querySelectorAll(allSelector).forEach(b => {
    b.classList.remove("active", "bg-white/[0.12]", "text-white", "ring-1", "ring-inset", "ring-white/15", "shadow-sm");
    b.classList.add("text-slate-400");
  });
  btn.classList.add("active", "bg-white/[0.12]", "text-white", "ring-1", "ring-inset", "ring-white/15", "shadow-sm");
  btn.classList.remove("text-slate-400");
}

function _switchSection(section) {
  currentSection = section;
  const hotspotSubs = document.getElementById('hotspot-sub-tabs');
  const hotspotFilters = document.getElementById('hotspot-filters');
  const compFilters = document.getElementById('comp-filters');
  const dateSel = document.getElementById('date-selector');

  if (section === 'hotspot') {
    hotspotSubs.classList.remove('hidden');
    hotspotFilters.classList.remove('hidden');
    compFilters.classList.add('hidden');
    if (currentTab === 'today') {
      dateSel.style.display = 'none';
      loadToday();
    } else {
      dateSel.style.display = '';
      loadDates();
    }
  } else {
    hotspotSubs.classList.add('hidden');
    hotspotFilters.classList.add('hidden');
    compFilters.classList.remove('hidden');
    dateSel.style.display = 'none';
    loadCompetitors();
  }
}

function setupNav() {
  // 顶级导航
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      _activateBtn(btn, '.nav-btn');
      _switchSection(btn.dataset.section);
    });
  });
  // 初始化顶级导航样式
  document.querySelector('.nav-btn.active').classList.add('bg-white/[0.12]', 'text-white', 'ring-1', 'ring-inset', 'ring-white/15', 'shadow-sm');
  document.querySelectorAll('.nav-btn:not(.active)').forEach(b => b.classList.add('text-slate-400'));

  // 热点子 Tab
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      currentTab = btn.dataset.tab;
      _activateBtn(btn, '.tab-btn');
      const dateSel = document.getElementById('date-selector');
      if (currentTab === 'today') {
        dateSel.style.display = 'none';
        _selectedHistoryDate = null;
        loadToday();
      } else if (currentTab === 'history') {
        dateSel.style.display = '';
        loadDates();
      }
    });
  });
  document.querySelector('.tab-btn.active').classList.add('bg-white/[0.12]', 'text-white', 'ring-1', 'ring-inset', 'ring-white/15', 'shadow-sm');
  document.querySelectorAll('.tab-btn:not(.active)').forEach(b => b.classList.add('text-slate-400'));
}

// ── Filter Rendering ──
function renderFilterButtons() {
  const priorities = ["ALL", "P0", "P1", "P2"];
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

  document.getElementById("filter-priority").innerHTML =
    '<span class="text-xs text-slate-500 font-medium mr-2">优先级</span>' +
    priorities.map(p => {
      const cfg = p !== "ALL" ? PRIORITY_CONFIG[p] : null;
      return filterBtn(p, p === "ALL" ? "全部" : p, filterPriority === p, cfg, `setFilterPriority('${p}')`);
    }).join("");

  document.getElementById("filter-channel").innerHTML =
    '<span class="text-xs text-slate-500 font-medium mr-2">渠道</span>' +
    channels.map(c => {
      const cfg = c !== "ALL" ? CHANNEL_CONFIG[c] : null;
      const label = c === "ALL" ? "全部" : (cfg ? `${cfg.icon} ${cfg.label}` : c);
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

function setFilterPriority(v) { filterPriority = v; rerender(); }
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

// ── Data Loading ──
async function loadToday() {
  try {
    const res = await fetch(API.today);
    const data = await res.json();
    console.log("[DEBUG] loadToday got", data.cards?.length, "cards");
    _currentData = data;
    renderDashboard(data);
    console.log("[DEBUG] renderDashboard done");
  } catch (e) {
    console.error("Failed to load today:", e);
    document.getElementById("card-sections").innerHTML =
      `<pre class="text-red-400 text-xs p-4">[DEBUG ERROR] ${e.message}\n${e.stack}</pre>` + renderEmptyState();
  }
}

let _selectedHistoryDate = null;

async function loadDates() {
  try {
    const res = await fetch(API.dates);
    const data = await res.json();
    const dates = Array.isArray(data) ? data : (data.dates || []);
    renderDateTimeline(dates);
  } catch (e) { console.error("Failed to load dates:", e); }
}

function renderDateTimeline(dates) {
  const container = document.getElementById("date-selector");
  if (!dates.length) {
    container.innerHTML = '<p class="text-sm text-slate-500">暂无历史数据</p>';
    return;
  }

  const dateSet = new Set(dates);
  const todayStr = new Date().toISOString().split('T')[0];

  // Determine which months to show (from available data)
  const monthKeys = new Set();
  dates.forEach(d => { const [y, m] = d.split('-'); monthKeys.add(`${y}-${m}`); });
  const sortedMonths = [...monthKeys].sort().reverse();

  const weekHeaders = ['一','二','三','四','五','六','日'];

  let html = '<div class="w-full space-y-4">';
  for (const monthKey of sortedMonths) {
    const [y, m] = monthKey.split('-');
    const mi = parseInt(m) - 1;
    const daysInMonth = new Date(parseInt(y), mi + 1, 0).getDate();
    // Monday=0 ... Sunday=6
    let firstDow = new Date(parseInt(y), mi, 1).getDay(); // 0=Sun
    firstDow = firstDow === 0 ? 6 : firstDow - 1; // convert to Mon=0

    html += `<div>
      <div class="text-[11px] text-slate-500 font-mono mb-2">${y} 年 ${parseInt(m)} 月</div>
      <div class="grid grid-cols-7 gap-1">
        ${weekHeaders.map(w => `<div class="text-center text-[9px] text-slate-600 font-mono pb-1">${w}</div>`).join('')}`;

    // Empty cells before first day
    for (let i = 0; i < firstDow; i++) {
      html += '<div></div>';
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${y}-${String(parseInt(m)).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
      const hasData = dateSet.has(dateStr);
      const isSelected = _selectedHistoryDate === dateStr;
      const isToday = dateStr === todayStr;

      if (hasData) {
        const selCls = isSelected
          ? 'bg-cyan-500/20 border-cyan-500/40 ring-1 ring-cyan-500/20 text-cyan-300'
          : 'border-white/[0.08] text-white hover:bg-white/[0.08] hover:border-white/[0.15]';
        html += `<button onclick="selectHistoryDate('${dateStr}')"
          class="relative flex items-center justify-center h-9 rounded-md border cursor-pointer transition-all duration-150 ${selCls}">
          ${isToday ? '<span class="absolute top-0.5 right-0.5 w-1.5 h-1.5 rounded-full bg-emerald-400"></span>' : ''}
          <span class="text-xs font-semibold">${day}</span>
        </button>`;
      } else {
        html += `<div class="flex items-center justify-center h-9 rounded-md">
          ${isToday ? '<span class="text-xs font-medium text-emerald-600">' + day + '</span>' : '<span class="text-xs text-slate-700">' + day + '</span>'}
        </div>`;
      }
    }

    html += '</div></div>';
  }
  html += '</div>';
  container.innerHTML = html;
}

function selectHistoryDate(dateStr) {
  _selectedHistoryDate = dateStr;
  // Re-render timeline to update selection state
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
    if (filterPriority !== "ALL" && card.priority !== filterPriority) return false;
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

  // Group by priority
  const p0 = filtered.filter(c => c.priority === "P0");
  const p1 = filtered.filter(c => c.priority === "P1");
  const p2 = filtered.filter(c => !c.priority || c.priority === "P2");

  let html = "";
  if (p0.length > 0) html += renderPrioritySection("P0", "当日启动", p0);
  if (p1.length > 0) html += renderPrioritySection("P1", "计划跟进", p1);
  if (p2.length > 0) html += renderPrioritySection("P2", "轻量参与", p2);
  if (filtered.length === 0) html = renderEmptyState();

  document.getElementById("card-sections").innerHTML = html;
  renderSidebar(data);

  document.getElementById("footer-left").textContent = `OSL Growth Intelligence · ${data.run_date || ""}`;
  document.getElementById("footer-right").textContent = `基于四层漏斗筛选 · ${allCards.length} 个行动包`;
}

// ── Hero Stats ──
function renderHeroStats(cards) {
  const p0 = cards.filter(c => c.priority === "P0").length;
  const p1 = cards.filter(c => c.priority === "P1").length;
  const p2 = cards.filter(c => !c.priority || c.priority === "P2").length;
  document.getElementById("hero-stats").innerHTML = `
    <div class="text-center"><div class="text-xl font-display font-bold text-white">${cards.length}</div><div class="text-[10px] text-slate-500 font-mono">行动包</div></div>
    <div class="w-px h-8 bg-white/10"></div>
    <div class="text-center"><div class="text-xl font-display font-bold text-red-400">${p0}</div><div class="text-[10px] text-slate-500 font-mono">P0 紧急</div></div>
    <div class="text-center"><div class="text-xl font-display font-bold text-amber-400">${p1}</div><div class="text-[10px] text-slate-500 font-mono">P1 跟进</div></div>
    <div class="text-center"><div class="text-xl font-display font-bold text-slate-400">${p2}</div><div class="text-[10px] text-slate-500 font-mono">P2 轻量</div></div>`;
}

// ── Priority Section ──
function renderPrioritySection(priority, label, cards) {
  const cfg = PRIORITY_CONFIG[priority];
  const isP0 = priority === "P0";
  const dotHtml = isP0
    ? `<span class="relative flex h-3 w-3"><span class="animate-ping absolute inline-flex h-full w-full rounded-full ${cfg.bar} opacity-60"></span><span class="relative inline-flex rounded-full h-3 w-3 ${cfg.bar}"></span></span>`
    : `<span class="h-3 w-3 rounded-full ${cfg.bar} shrink-0"></span>`;

  return `<section>
    <div class="flex items-center gap-3 mb-4">
      ${dotHtml}
      <h2 class="text-sm font-display font-bold ${cfg.color} tracking-wide uppercase">${priority} — ${label}</h2>
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
  const p = card.priority || "P2";
  const pCfg = PRIORITY_CONFIG[p] || PRIORITY_CONFIG.P2;
  const timing = parseTimingKey(card.timing);
  const tCfg = URGENCY_CONFIG[timing] || URGENCY_CONFIG.Day;
  const site = normalizeSite(card.site);
  const sCfg = SITE_CONFIG[site] || SITE_CONFIG.Both;
  const exec = card.executability || "D";
  const eCfg = EXEC_CONFIG[exec] || EXEC_CONFIG.D;

  const pulseDot = p === "P0"
    ? '<span class="relative flex h-2.5 w-2.5 shrink-0 mt-[3px]"><span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-500 opacity-60"></span><span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-red-500"></span></span>'
    : "";

  const channelTabs = (card.channels || []).map((ch, ci) => {
    const chCfg = CHANNEL_CONFIG[ch.name] || { label: ch.name, icon: '📋', color: 'text-slate-300', bg: 'bg-slate-500/15', activeCls: 'text-slate-300 bg-slate-500/15' };
    return `<button onclick="toggleChannelTab('${card.id}',${ci})" id="ch-tab-${card.id}-${ci}" data-channel="${esc(ch.name)}"
      class="ch-tab inline-flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-medium transition-colors duration-150 text-slate-400 bg-white/[0.05] hover:bg-white/10 hover:text-slate-200">
      <span>${chCfg.icon}</span>${chCfg.label}<span class="ml-0.5 transition-transform duration-150" id="ch-arrow-${card.id}-${ci}">▾</span>
    </button>`;
  }).join("");

  const channelPanels = (card.channels || []).map((ch, ci) => {
    const chCfg = CHANNEL_CONFIG[ch.name] || { label: ch.name, icon: '📋', color: 'text-slate-300', bg: 'bg-slate-500/15' };
    return `<div id="ch-panel-${card.id}-${ci}" class="hidden border border-white/[0.08] rounded-md bg-[#0f1623] p-3 mb-2 mt-1 ch-panel" data-channel="${esc(ch.name)}">
      <div class="flex items-center justify-between mb-2">
        <span class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-medium ${chCfg.color} ${chCfg.bg}"><span>${chCfg.icon}</span>${chCfg.label}</span>
        <button onclick="copyPanelContent('ch-md-${card.id}-${ci}')" class="text-[10px] font-mono px-2 py-1 rounded border border-white/10 text-slate-400 hover:border-cyan-500/40 hover:text-cyan-400 hover:bg-cyan-500/5 transition-colors duration-150">复制</button>
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
  <div class="card-item relative rounded-lg border border-white/[0.08] bg-navy-light overflow-hidden transition-shadow duration-200 hover:shadow-lg hover:shadow-black/30"
       style="animation: fadeSlideIn 0.3s ease-out both; animation-delay: ${index * 0.06}s">
    <div class="absolute left-0 top-0 bottom-0 w-1 ${pCfg.bar}"></div>
    <div class="pl-4 pr-4 pt-4 pb-3">
      <div class="flex items-start justify-between gap-3 mb-2">
        <div class="flex items-start gap-2 min-w-0">
          ${pulseDot}
          <div class="min-w-0">
            <h3 class="text-sm font-display font-semibold text-white leading-snug">${esc(card.title)}</h3>
            <p class="text-[11px] text-slate-400 mt-0.5 font-body">${esc(card.category || "")}</p>
          </div>
        </div>
        <div class="flex items-center gap-1.5 shrink-0">
          <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-semibold ${pCfg.color} ${pCfg.bg}">${p}</span>
          <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${tCfg.color} ${tCfg.bg} ${tCfg.border}">${tCfg.label}</span>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-1.5 mb-3">
        <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-mono ${sCfg.color} ${sCfg.bg}">${sCfg.label}</span>
        <span class="text-[10px] font-mono ${eCfg.color}">${eCfg.label}</span>
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
    const btn = el.closest('.ch-panel').querySelector('button');
    if (btn) {
      const orig = btn.textContent;
      btn.textContent = '✓ 已复制';
      btn.classList.add('text-emerald-400', 'border-emerald-500/40');
      setTimeout(() => {
        btn.textContent = orig;
        btn.classList.remove('text-emerald-400', 'border-emerald-500/40');
      }, 1500);
    }
  });
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

  // Channel legend
  html += `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">渠道图例</h3>
    <div class="space-y-2">${Object.entries(CHANNEL_CONFIG).map(([, v]) =>
      `<div class="flex items-center gap-2"><span class="text-sm">${v.icon}</span><span class="text-[10px] font-mono ${v.color}">${v.label}</span></div>`
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
// ── Competitor Intelligence Module ──
// ══════════════════════════════════════════════════════════════

const REGION_CONFIG = {
  'HK':     { label: '香港站',   color: 'text-sky-400',     bg: 'bg-sky-500/10',     bar: 'bg-sky-500',     border: 'border-sky-500/25' },
  'VN':     { label: '越南站',   color: 'text-emerald-400', bg: 'bg-emerald-500/10', bar: 'bg-emerald-500', border: 'border-emerald-500/25' },
  'EU':     { label: '欧洲站',   color: 'text-indigo-400',  bg: 'bg-indigo-500/10',  bar: 'bg-indigo-500',  border: 'border-indigo-500/25' },
  'ID':     { label: '印尼站',   color: 'text-amber-400',   bg: 'bg-amber-500/10',   bar: 'bg-amber-500',   border: 'border-amber-500/25' },
  'BROKER': { label: '跨区域券商', color: 'text-violet-400', bg: 'bg-violet-500/10', bar: 'bg-violet-500', border: 'border-violet-500/25' },
};

const IMPORTANCE_CONFIG = {
  high:   { label: '重要', color: 'text-red-400', bg: 'bg-red-500/10' },
  medium: { label: '常规', color: 'text-amber-400', bg: 'bg-amber-500/10' },
  low:    { label: '日常', color: 'text-slate-400', bg: 'bg-slate-500/10' },
};

const CATEGORY_LABELS = {
  '新币上线': { color: 'text-teal-400', bg: 'bg-teal-500/10' },
  '产品更新': { color: 'text-blue-400', bg: 'bg-blue-500/10' },
  '活动推广': { color: 'text-orange-400', bg: 'bg-orange-500/10' },
  '合作伙伴': { color: 'text-purple-400', bg: 'bg-purple-500/10' },
  '监管合规': { color: 'text-yellow-400', bg: 'bg-yellow-500/10' },
  '融资/IPO': { color: 'text-green-400', bg: 'bg-green-500/10' },
  '人事变动': { color: 'text-pink-400', bg: 'bg-pink-500/10' },
  '其他':     { color: 'text-slate-400', bg: 'bg-slate-500/10' },
};

async function loadCompetitors() {
  try {
    const res = await fetch(API.compToday);
    if (!res.ok) { renderCompetitorEmpty(); return; }
    const data = await res.json();
    _compData = data;
    renderCompetitorDashboard(data);
  } catch (e) {
    console.error("Failed to load competitors:", e);
    renderCompetitorEmpty();
  }
}

function renderCompetitorEmpty() {
  document.getElementById("card-sections").innerHTML = `
    <div class="text-center py-20 text-slate-500 font-body">
      <p class="text-sm">暂无竞品动态数据</p>
      <p class="text-xs text-slate-600 mt-1">等待数据抓取与处理完成</p>
    </div>`;
}

function renderCompetitorDashboard(data) {
  const competitors = data.competitors || [];
  if (!competitors.length) { renderCompetitorEmpty(); return; }

  document.getElementById("header-date").textContent = data.run_date
    ? `数据更新于 ${data.run_date}` : "";

  // Filters
  renderCompetitorFilter(competitors);

  // Apply region + name filter
  let filtered = competitors;
  if (compFilterRegion !== "ALL") {
    filtered = filtered.filter(c => c.region === compFilterRegion);
  }
  if (compFilterName !== "ALL") {
    filtered = filtered.filter(c => c.name === compFilterName);
  }

  // Stats
  const totalEvents = competitors.reduce((s, c) => s + (c.events || []).length, 0);
  const highEvents = competitors.reduce((s, c) => s + (c.events || []).filter(e => e.importance === 'high').length, 0);
  document.getElementById("hero-stats").innerHTML = `
    <div class="text-center"><div class="text-xl font-display font-bold text-white">${competitors.length}</div><div class="text-[10px] text-slate-500 font-mono">竞品</div></div>
    <div class="w-px h-8 bg-white/10"></div>
    <div class="text-center"><div class="text-xl font-display font-bold text-cyan-400">${totalEvents}</div><div class="text-[10px] text-slate-500 font-mono">动态事件</div></div>
    <div class="text-center"><div class="text-xl font-display font-bold text-red-400">${highEvents}</div><div class="text-[10px] text-slate-500 font-mono">重要事件</div></div>`;

  // Group by region and render
  const regionOrder = ['HK', 'VN', 'EU', 'ID', 'BROKER'];
  const byRegion = {};
  filtered.forEach(c => {
    const r = c.region || 'HK';
    (byRegion[r] = byRegion[r] || []).push(c);
  });

  let html = '';
  let cardIdx = 0;
  regionOrder.forEach(region => {
    const comps = byRegion[region];
    if (!comps || !comps.length) return;
    const rc = REGION_CONFIG[region] || REGION_CONFIG.HK;
    const regionEvents = comps.reduce((s, c) => s + (c.events || []).length, 0);

    html += `<section class="mb-6">
      <div class="flex items-center gap-3 mb-4">
        <span class="h-3 w-3 rounded-full ${rc.bar} shrink-0"></span>
        <h2 class="text-sm font-display font-bold ${rc.color} tracking-wide uppercase">${rc.label}</h2>
        <div class="flex-1 h-px bg-white/[0.06]"></div>
        <span class="text-[10px] font-mono text-slate-500">${comps.length} 家 · ${regionEvents} 条动态</span>
      </div>
      <div class="space-y-3">
        ${comps.map(comp => renderCompetitorCard(comp, cardIdx++)).join('')}
      </div>
    </section>`;
  });

  if (!html) html = '<div class="text-center py-10 text-slate-500 text-sm">当前筛选无结果</div>';

  document.getElementById("card-sections").innerHTML = html;
  renderCompetitorSidebar(competitors);

  document.getElementById("footer-left").textContent = `OSL Growth Intelligence · ${data.run_date || ""}`;
  document.getElementById("footer-right").textContent = `竞品监测 · ${competitors.length} 家竞品 · ${totalEvents} 条动态`;
  document.getElementById("filter-count").textContent = `${filtered.length} / ${competitors.length} 家竞品`;
}

function renderCompetitorFilter(competitors) {
  const base = 'text-xs font-medium px-3 py-1.5 rounded-md transition-all duration-200 cursor-pointer select-none';
  const activeCls = 'bg-white/[0.12] text-white ring-1 ring-inset ring-white/15 shadow-sm';
  const inactiveCls = 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.06]';

  // Region filter
  const regions = [...new Set(competitors.map(c => c.region || 'HK'))];
  const regionBtns = ["ALL", ...regions];
  document.getElementById("comp-region-filter").innerHTML =
    '<span class="text-xs text-slate-500 font-medium mr-1">地区</span>' +
    regionBtns.map(r => {
      const rc = REGION_CONFIG[r];
      const label = r === "ALL" ? "全部" : (rc ? rc.label : r);
      const isActive = compFilterRegion === r;
      return `<button onclick="setCompRegion('${esc(r)}')" class="${base} ${isActive ? activeCls : inactiveCls}">${label}</button>`;
    }).join("");

  // Name filter (within selected region)
  let namePool = competitors;
  if (compFilterRegion !== "ALL") {
    namePool = competitors.filter(c => (c.region || 'HK') === compFilterRegion);
  }
  const names = ["ALL", ...namePool.map(c => c.name)];
  document.getElementById("comp-name-filter").innerHTML =
    '<span class="text-xs text-slate-500 font-medium mr-1">竞品</span>' +
    names.map(n => {
      const label = n === "ALL" ? "全部" : n;
      const isActive = compFilterName === n;
      return `<button onclick="setCompName('${esc(n)}')" class="${base} ${isActive ? activeCls : inactiveCls}">${label}</button>`;
    }).join("");
}

function setCompRegion(region) {
  compFilterRegion = region;
  compFilterName = "ALL";
  if (_compData) renderCompetitorDashboard(_compData);
}

function setCompName(name) {
  compFilterName = name;
  if (_compData) renderCompetitorDashboard(_compData);
}

function renderCompetitorCard(comp, index) {
  const region = comp.region || 'HK';
  const rc = REGION_CONFIG[region] || REGION_CONFIG.HK;
  const events = comp.events || [];
  const highCount = events.filter(e => e.importance === 'high').length;
  const isExpanded = _compExpandedSet.has(comp.name);

  const eventCountBadge = highCount > 0
    ? `<span class="text-[10px] font-mono text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded">${highCount} 重要</span>`
    : '';

  const eventsHtml = events.map((ev, ei) => {
    const imp = IMPORTANCE_CONFIG[ev.importance] || IMPORTANCE_CONFIG.low;
    const catStyle = CATEGORY_LABELS[ev.category] || CATEGORY_LABELS['其他'];
    const sources = (ev.sources || []).map(s =>
      `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"
        class="text-[10px] text-slate-500 hover:text-cyan-400 transition-colors underline underline-offset-2 decoration-slate-700 hover:decoration-cyan-500/50">${esc(s.name)}</a>`
    ).join('<span class="text-slate-700 mx-1">·</span>');

    return `<div class="flex items-start gap-3 py-2.5 ${ei > 0 ? 'border-t border-white/[0.05]' : ''}">
      <div class="min-w-0 flex-1">
        <div class="flex items-center gap-2 mb-1">
          <span class="text-[10px] font-mono px-1.5 py-0.5 rounded ${catStyle.color} ${catStyle.bg}">${esc(ev.category)}</span>
          <span class="text-[10px] font-mono ${imp.color}">${imp.label}</span>
        </div>
        <h4 class="text-[12px] font-display font-semibold text-white leading-snug mb-1">${esc(ev.title)}</h4>
        <div class="prose-container text-[11px] leading-relaxed text-slate-400" data-md="${encodeURIComponent(ev.summary || '')}" id="comp-md-${index}-${ei}"></div>
        ${sources ? `<div class="flex flex-wrap items-center gap-1 mt-1.5">${sources}</div>` : ''}
      </div>
    </div>`;
  }).join('');

  // Initials as avatar
  const initials = comp.name.replace(/[^A-Za-z\u4e00-\u9fff]/g, '').slice(0, 2).toUpperCase();

  return `
  <div class="comp-card relative rounded-lg border ${isExpanded ? rc.border : 'border-white/[0.08]'} bg-navy-light overflow-hidden transition-all duration-200 hover:shadow-lg hover:shadow-black/30"
       style="animation: fadeSlideIn 0.3s ease-out both; animation-delay: ${index * 0.04}s">
    <div class="absolute left-0 top-0 bottom-0 w-1 ${rc.bar}"></div>
    <div class="pl-4 pr-4 pt-3.5 pb-3">
      <button onclick="toggleCompCard('${esc(comp.name)}', ${index})" class="w-full text-left">
        <div class="flex items-center justify-between gap-3">
          <div class="flex items-center gap-3 min-w-0">
            <div class="w-8 h-8 rounded-md ${rc.bg} ${rc.color} flex items-center justify-center text-[11px] font-bold font-mono shrink-0">${initials}</div>
            <div class="min-w-0">
              <h3 class="text-sm font-display font-semibold text-white leading-snug">${esc(comp.name)}</h3>
              <p class="text-[11px] text-slate-400 mt-0.5 font-body truncate">${esc(comp.summary)}</p>
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            ${eventCountBadge}
            <span class="text-[10px] font-mono text-slate-500">${events.length} 条</span>
            <span class="text-slate-500 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}" id="comp-arrow-${index}">▾</span>
          </div>
        </div>
      </button>
      <div id="comp-detail-${index}" class="${isExpanded ? '' : 'hidden'} mt-3 pt-3 border-t border-white/[0.06]">
        ${events.length > 0 ? eventsHtml : '<p class="text-[11px] text-slate-500 py-2">今日无重大动态</p>'}
      </div>
    </div>
  </div>`;
}

function toggleCompCard(compName, index) {
  const detail = document.getElementById(`comp-detail-${index}`);
  const arrow = document.getElementById(`comp-arrow-${index}`);
  if (!detail) return;

  const wasHidden = detail.classList.contains('hidden');
  if (wasHidden) {
    detail.classList.remove('hidden');
    arrow.classList.add('rotate-180');
    _compExpandedSet.add(compName);
    detail.querySelectorAll('.prose-container[data-md]').forEach(el => {
      if (!el.dataset.rendered && el.dataset.md) {
        el.innerHTML = marked.parse(decodeURIComponent(el.dataset.md));
        el.dataset.rendered = "1";
      }
    });
  } else {
    detail.classList.add('hidden');
    arrow.classList.remove('rotate-180');
    _compExpandedSet.delete(compName);
  }
}

function renderCompetitorSidebar(competitors) {
  const catCounts = {};
  competitors.forEach(c => (c.events || []).forEach(e => {
    catCounts[e.category] = (catCounts[e.category] || 0) + 1;
  }));

  let html = '';

  html += `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">事件分类</h3>
    <div class="space-y-2">${Object.entries(catCounts).sort((a,b) => b[1]-a[1]).map(([cat, cnt]) => {
      const cs = CATEGORY_LABELS[cat] || CATEGORY_LABELS['其他'];
      return `<div class="flex items-center justify-between gap-2">
        <span class="text-[10px] font-body ${cs.color}">${cat}</span>
        <span class="text-[10px] font-mono text-slate-500">${cnt}</span>
      </div>`;
    }).join("")}</div>
  </div>`;

  // By region
  const regionOrder = ['HK', 'VN', 'EU', 'ID', 'BROKER'];
  html += `<div class="rounded-lg border border-white/[0.08] bg-navy-light p-4">
    <h3 class="text-xs font-display font-semibold text-slate-300 mb-3">竞品活跃度</h3>
    <div class="space-y-2">${competitors.map(c => {
      const rc = REGION_CONFIG[c.region] || REGION_CONFIG.HK;
      const n = (c.events || []).length;
      return `<div class="flex items-center justify-between gap-2">
        <span class="text-[10px] font-body text-slate-400">${c.name}</span>
        <div class="flex items-center gap-2">
          <span class="text-[10px] font-mono ${rc.color}">${(REGION_CONFIG[c.region] || REGION_CONFIG.HK).label}</span>
          <span class="text-[10px] font-mono text-slate-500">${n}</span>
        </div>
      </div>`;
    }).join("")}</div>
  </div>`;

  document.getElementById("sidebar-content").innerHTML = html;
}
