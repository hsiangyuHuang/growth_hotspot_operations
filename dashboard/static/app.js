const REFRESH_INTERVAL = 5 * 60 * 1000;
let currentTab = "today";
let currentFilter = "all";
let _currentData = null;
let _currentPrefix = null;
let refreshTimer = null;
const headerState = { today: false, history: false };

// Auto-detect: static site (Vercel) vs local FastAPI
const IS_STATIC = !window.location.port || window.location.hostname !== 'localhost';
const API = IS_STATIC
  ? { today: "./data/latest.json", dates: "./data/dates.json", history: (d) => `./data/${d}.json` }
  : { today: "/api/today", dates: "/api/dates", history: (d) => `/api/history?date=${d}` };

const CHANNEL_ICONS = {
  "Paid Ads": { icon: "\u{1F4E2}", color: "purple" },
  "站内运营 / 用户触达": { icon: "\u{1F465}", color: "sky" },
  "SEO": { icon: "\u{1F50D}", color: "emerald" },
  "社区": { icon: "\u{1F4AC}", color: "amber" },
};

// ── Bootstrap ──
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  loadToday();
  refreshTimer = setInterval(loadToday, REFRESH_INTERVAL);
});

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      currentTab = btn.dataset.tab;
      document.querySelectorAll(".tab-btn").forEach(b => {
        b.classList.remove("active", "bg-white/10", "text-white");
        b.classList.add("text-slate-500");
      });
      btn.classList.add("active", "bg-white/10", "text-white");
      btn.classList.remove("text-slate-500");
      if (currentTab === "today") {
        document.getElementById("today-view").style.display = "";
        document.getElementById("history-view").style.display = "none";
        loadToday();
      } else {
        document.getElementById("today-view").style.display = "none";
        document.getElementById("history-view").style.display = "";
        loadDates();
      }
    });
  });
  document.querySelector('.tab-btn.active').classList.add("bg-white/10", "text-white");
  document.querySelectorAll('.tab-btn:not(.active)').forEach(b => b.classList.add("text-slate-500"));

  document.getElementById("history-date").addEventListener("change", e => {
    if (e.target.value) loadHistory(e.target.value);
  });
}

// ── Data Loading ──
async function loadToday() {
  try {
    const res = await fetch(API.today);
    const data = await res.json();
    renderDashboard(data, "today");
    document.getElementById("update-time").textContent =
      new Date().toLocaleTimeString("zh-HK", { hour: '2-digit', minute: '2-digit' });
  } catch (e) {
    console.error("Failed to load today:", e);
  }
}

async function loadDates() {
  const res = await fetch(API.dates);
  const data = await res.json();
  const select = document.getElementById("history-date");
  while (select.options.length > 1) select.remove(1);
  const dates = Array.isArray(data) ? data : (data.dates || []);
  dates.forEach(d => {
    const opt = document.createElement("option");
    opt.value = d;
    opt.textContent = d;
    select.appendChild(opt);
  });
}

async function loadHistory(dateStr) {
  try {
    const res = await fetch(API.history(dateStr));
    if (!res.ok) {
      document.getElementById("history-header-wrap").style.display = "none";
      document.getElementById("history-list").innerHTML = renderEmptyState();
      return;
    }
    const data = await res.json();
    renderDashboard(data, "history");
  } catch (e) {
    console.error("Failed to load history:", e);
  }
}

// ── Rendering ──
function renderDashboard(data, prefix) {
  _currentData = data;
  _currentPrefix = prefix;
  const cards = data.cards || [];
  window._currentCards = cards;

  renderSummaryBar(cards);

  // Header (Layer 1-3)
  const headerWrap = document.getElementById(`${prefix}-header-wrap`);
  const headerEl = document.getElementById(`${prefix}-header`);
  if (data.header_markdown) {
    headerWrap.style.display = "";
    headerEl.innerHTML = marked.parse(data.header_markdown);
    headerEl.style.display = headerState[prefix] ? "" : "none";
    updateChevron(prefix);
  } else {
    headerWrap.style.display = "none";
  }

  const listEl = document.getElementById(`${prefix}-list`);
  const filterBarEl = document.getElementById(`${prefix}-filter-bar`);

  if (!cards.length) {
    listEl.innerHTML = renderEmptyState();
    if (filterBarEl) filterBarEl.style.display = "none";
    return;
  }

  renderFilterBar(prefix);

  // Sort: P0 first, then P1, then P2
  const sorted = [...cards].sort((a, b) => {
    const order = { P0: 0, P1: 1, P2: 2 };
    return (order[a.priority] ?? 2) - (order[b.priority] ?? 2);
  });

  const filtered = currentFilter === "all"
    ? sorted
    : sorted.filter(c => {
        if (currentFilter === "P2") return !c.priority || c.priority === "P2";
        return c.priority === currentFilter;
      });

  listEl.innerHTML = filtered.map((card, i) => renderCard(card, i)).join("");
}

function renderSummaryBar(cards) {
  const bar = document.getElementById("summary-bar");
  if (!cards.length) { bar.style.display = "none"; return; }
  bar.style.display = "";
  const p0 = cards.filter(c => c.priority === "P0").length;
  const p1 = cards.filter(c => c.priority === "P1").length;
  const p2 = cards.filter(c => !c.priority || c.priority === "P2").length;
  bar.innerHTML =
    statCard("PACKAGES", cards.length, "bg-emerald-500/10 text-emerald-400 border-emerald-500/20") +
    statCard("P0 URGENT", p0, "bg-red-500/10 text-red-400 border-red-500/20", p0 > 0) +
    statCard("P1 PLANNED", p1, "bg-blue-500/10 text-blue-400 border-blue-500/20") +
    statCard("P2 LIGHT", p2, "bg-slate-500/10 text-slate-400 border-slate-500/20");
}

function renderFilterBar(prefix) {
  const filterBarEl = document.getElementById(`${prefix}-filter-bar`);
  if (!filterBarEl) return;
  filterBarEl.style.display = "";
  const pills = [
    { f: "all", label: "全部" },
    { f: "P0", label: "P0 紧急" },
    { f: "P1", label: "P1 计划" },
    { f: "P2", label: "P2 轻量" },
  ];
  filterBarEl.innerHTML = pills.map(({ f, label }) => {
    const active = currentFilter === f;
    const cls = active
      ? "bg-white/10 text-white border-white/20"
      : "text-slate-500 border-slate-700 hover:border-slate-500 hover:text-slate-300";
    return `<button onclick="setFilter('${f}')" data-filter="${f}"
      class="px-3 py-1.5 rounded-lg text-xs font-mono border transition-all duration-150 ${cls}">${label}</button>`;
  }).join("");
}

function setFilter(f) {
  currentFilter = f;
  if (_currentData && _currentPrefix) {
    renderDashboard(_currentData, _currentPrefix);
  }
}

function statCard(label, count, classes, pulse = false) {
  return `<div class="rounded-xl border ${classes} p-4 transition-all duration-300 hover:scale-[1.02]"
    style="animation: fadeSlideIn 0.4s ease-out both">
    <div class="text-[10px] font-mono tracking-widest opacity-60 mb-2">${label}</div>
    <div class="text-3xl font-display font-800 tabular-nums ${pulse ? 'animate-pulse' : ''}">${count}</div>
  </div>`;
}

// ── Card ──
function renderCard(card, index) {
  const p = card.priority || "P2";
  const borderColor = { P0: "border-l-red-500", P1: "border-l-blue-500", P2: "border-l-slate-600" }[p];
  const isP0 = p === "P0";
  const glowStyle = isP0
    ? "box-shadow: inset 0 0 80px -20px rgba(239,68,68,0.1), 0 0 40px -10px rgba(239,68,68,0.15);"
    : p === "P1" ? "box-shadow: inset 0 0 60px -20px rgba(59,130,246,0.04);" : "";
  const topBorder = isP0 ? "border-t-2 border-t-red-500" : "";
  const titleSize = isP0 ? "text-xl" : "text-[17px]";

  const badges = [
    priorityBadge(p),
    card.category ? tagBadge(card.category, "bg-slate-700/50 text-slate-300") : "",
    card.timing ? timingBadge(card.timing) : "",
    card.site ? tagBadge(card.site, "bg-indigo-500/10 text-indigo-300 border border-indigo-500/20") : "",
    card.executability ? execBadge(card.executability) : "",
  ].filter(Boolean).join("");

  const summary = card.summary
    ? `<p class="text-sm text-slate-300 leading-relaxed mt-3">${esc(card.summary)}</p>` : "";

  const dontDo = card.dont_do
    ? `<p class="text-xs text-slate-500 mt-2 border-l-2 border-slate-600 pl-2"><span class="text-slate-600">⚠ 不做：</span>${esc(card.dont_do)}</p>`
    : "";

  // Sources
  const sources = (card.sources || []).map(s =>
    `<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer"
        class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono bg-slate-700/40 text-slate-400 border border-slate-600/30 hover:bg-slate-600/50 hover:text-slate-200 transition-colors duration-150">
      <svg class="w-3 h-3 opacity-60" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"/></svg>
      ${esc(s.name)}</a>`
  ).join("");
  const sourcesHtml = sources ? `<div class="flex flex-wrap gap-1.5 mt-3">${sources}</div>` : "";

  // Channel sub-cards
  const channels = (card.channels || []).map((ch, ci) => renderChannelCard(ch, card.id, ci)).join("");

  return `
  <div class="rounded-xl bg-surface border border-white/5 border-l-[3px] ${borderColor} ${topBorder} overflow-hidden transition-all duration-300 hover:border-white/10"
       style="${glowStyle} animation: fadeSlideIn 0.5s ease-out both; animation-delay: ${index * 0.08}s"
       id="card-${card.id}">
    <div class="p-5">
      <div class="flex flex-wrap items-center gap-2 mb-3">${badges}</div>
      <h3 class="font-display font-700 ${titleSize} text-white leading-snug tracking-tight">${esc(card.title)}</h3>
      ${summary}
      ${dontDo}
      ${sourcesHtml}
    </div>
    <!-- Channel sub-cards -->
    ${channels ? `<div class="px-5 pb-5 grid gap-3 sm:grid-cols-2">${channels}</div>` : ""}
  </div>`;
}

// ── Channel Sub-Card ──
function renderChannelCard(ch, cardId, chIndex) {
  const cfg = CHANNEL_ICONS[ch.name] || { icon: "\u{1F539}", color: "slate" };
  const colorMap = {
    purple: { border: "border-purple-500/20", bg: "bg-purple-500/5", text: "text-purple-300", icon: "text-purple-400" },
    sky:    { border: "border-sky-500/20",    bg: "bg-sky-500/5",    text: "text-sky-300",    icon: "text-sky-400" },
    emerald:{ border: "border-emerald-500/20",bg: "bg-emerald-500/5",text: "text-emerald-300",icon: "text-emerald-400" },
    amber:  { border: "border-amber-500/20",  bg: "bg-amber-500/5",  text: "text-amber-300",  icon: "text-amber-400" },
    slate:  { border: "border-slate-500/20",  bg: "bg-slate-500/5",  text: "text-slate-300",  icon: "text-slate-400" },
  };
  const c = colorMap[cfg.color] || colorMap.slate;
  const chId = `${cardId}-ch-${chIndex}`;

  return `
  <div class="rounded-lg border ${c.border} ${c.bg} overflow-hidden transition-all duration-200 hover:border-opacity-40">
    <button onclick="toggleChannel('${chId}')"
      class="w-full flex items-center justify-between px-4 py-3 cursor-pointer">
      <div class="flex items-center gap-2">
        <span class="${c.icon}">${cfg.icon}</span>
        <span class="text-sm font-medium ${c.text}">${esc(ch.name)}</span>
      </div>
      <svg class="w-3.5 h-3.5 text-slate-500 transition-transform duration-200" id="ch-chevron-${chId}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
      </svg>
    </button>
    <div id="ch-body-${chId}" class="channel-body px-4 pb-4 prose-container text-[13px] leading-relaxed" style="display:none"
         data-md="${encodeURIComponent(ch.markdown)}"></div>
  </div>`;
}

function toggleChannel(chId) {
  const body = document.getElementById(`ch-body-${chId}`);
  const chevron = document.getElementById(`ch-chevron-${chId}`);
  const isHidden = body.style.display === "none";

  if (isHidden) {
    if (!body.dataset.rendered) {
      body.innerHTML = marked.parse(decodeURIComponent(body.dataset.md));
      body.dataset.rendered = "1";
    }
    body.style.display = "";
    chevron.style.transform = "rotate(180deg)";
  } else {
    body.style.display = "none";
    chevron.style.transform = "";
  }
}

// ── Badges ──
function priorityBadge(p) {
  const s = {
    P0: "bg-red-500/15 text-red-400 border-red-500/30 ring-1 ring-red-500/20",
    P1: "bg-blue-500/15 text-blue-400 border-blue-500/30",
    P2: "bg-slate-600/30 text-slate-400 border-slate-500/30",
  };
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-mono font-600 border ${s[p] || s.P2}">${p}</span>`;
}

function timingBadge(timing) {
  const icon = timing === "Day" ? "\u26A1" : timing === "Wave" ? "\u{1F30A}" : "\u{1F4C8}";
  return `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">${icon} ${esc(timing)}</span>`;
}

function execBadge(exec) {
  const c = {
    A: "bg-emerald-500/10 text-emerald-300 border-emerald-500/20",
    B: "bg-sky-500/10 text-sky-300 border-sky-500/20",
    C: "bg-amber-500/10 text-amber-300 border-amber-500/20",
    D: "bg-slate-600/20 text-slate-400 border-slate-500/20",
  };
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-mono border ${c[exec] || c.D}">Exec:${exec}</span>`;
}

function tagBadge(text, cls) {
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-mono ${cls}">${esc(text)}</span>`;
}

function renderEmptyState() {
  return `<div class="text-center py-20">
    <div class="text-4xl mb-3 opacity-20">\u25D1</div>
    <p class="text-sm text-slate-500 font-mono">NO DATA AVAILABLE</p>
    <p class="text-xs text-slate-600 mt-1">Waiting for today's pipeline to complete</p>
  </div>`;
}

// ── Header Toggle ──
function toggleHeader(prefix) {
  headerState[prefix] = !headerState[prefix];
  document.getElementById(`${prefix}-header`).style.display = headerState[prefix] ? "" : "none";
  updateChevron(prefix);
}

function updateChevron(prefix) {
  const ch = document.getElementById(`${prefix}-header-chevron`);
  if (ch) ch.style.transform = headerState[prefix] ? "rotate(90deg)" : "";
}

function esc(str) {
  return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
