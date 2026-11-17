/* =====================================================================
   HedgeOne terminal — UI controller
   ===================================================================== */
import { api } from "./api.js";
import { ChartStack, PALETTE, fmtNum, fmtTime } from "./chart.js";
import { Replay } from "./replay.js";
import { $, $$, esc, highlightPy, insightCards, kpiCards, metricMap, metricTables, toast, tradeRows, TRADE_HEAD, fmtMetric } from "./ui.js";

const INTERVALS = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d", "1w"];

/* ---------------- state (remembered per browser) ---------------- */
const saved = (() => { try { return JSON.parse(localStorage.getItem("h1-state") || "{}"); } catch (e) { return {}; } })();
const S = {
  symbol: saved.symbol || null,
  interval: saved.interval || "15m",
  start: saved.start || "",
  end: saved.end || "",
  strategy: saved.strategy || null,
  params: saved.params || {},          // {strategyName: {param: value}}
  settings: saved.settings || {},
  indicators: saved.indicators || [],  // [{id, name, params, color}]
  dock: saved.dock || "right",
  termSize: saved.termSize || null,
  symbols: [], strategies: [], indicatorDefs: [], defaults: null, costs: {},
  last: null, mode: null, tradeFilter: "all", sort: null,
};
const persist = () => {
  try {
    localStorage.setItem("h1-state", JSON.stringify({
      symbol: S.symbol, interval: S.interval, start: S.start, end: S.end, strategy: S.strategy,
      params: S.params, settings: S.settings, indicators: S.indicators, dock: S.dock, termSize: S.termSize,
    }));
  } catch (e) { /* private mode */ }
};

/* ---------------- chart ---------------- */
const chart = new ChartStack($("#chart"), { theme: "dark", onTradeHover: showTradeCard });
chart.onPaneClosed = (id) => {
  if (id.startsWith("ind:")) { S.indicators = S.indicators.filter((x) => "ind:" + x.id !== id); persist(); renderActiveIndicators(); }
};

/* ---------------- busy / errors ---------------- */
let busyN = 0;
function busy(on, text = "Working…") {
  busyN += on ? 1 : -1;
  $("#busy").classList.toggle("hidden", busyN <= 0);
  if (on) $("#busyText").textContent = text;
}
async function guard(text, fn) {
  busy(true, text);
  try { return await fn(); } catch (e) { toast(e.message, "error", false, 8000); console.error(e); } finally { busy(false); }
}

/* =====================================================================
   Top bar
   ===================================================================== */
function renderIntervals() {
  $("#intervals").innerHTML = INTERVALS.map((i) => `<button data-iv="${i}" class="${i === S.interval ? "active" : ""}">${i}</button>`).join("");
  $$("#intervals button").forEach((b) => b.onclick = () => { S.interval = b.dataset.iv; persist(); renderIntervals(); reload(); });
}

function renderSymbolList(filter = "") {
  const f = filter.toLowerCase();
  const groups = {};
  S.symbols.filter((s) => !f || s.name.toLowerCase().includes(f) || s.symbol.toLowerCase().includes(f))
    .forEach((s) => (groups[s.market] = groups[s.market] || []).push(s));
  $("#symList").innerHTML = Object.entries(groups).map(([mk, list]) =>
    `<div class="sym-group">${mk}</div>` + list.map((s) => `
      <div class="sym-row ${s.name === S.symbol ? "active" : ""}" data-sym="${esc(s.name)}">
        <span class="sym-n">${esc(s.name)}</span>
        <span class="sym-meta">${s.stored.length ? `<span class="dot ok"></span>${s.stored.join(" ")}` : `<span class="dot"></span>no data`}
        · ${s.source}</span></div>`).join("")).join("") || `<div class="placeholder">No match</div>`;
  $$("#symList .sym-row").forEach((r) => r.onclick = () => {
    S.symbol = r.dataset.sym; persist(); $("#symPop").classList.add("hidden"); updateSymLabel(); reload();
  });
}
function updateSymLabel() { $("#symName").textContent = S.symbol || "—"; chart.symbolLabel = `${S.symbol || ""} · ${S.interval}`; }

$("#symBtn").onclick = (e) => {
  e.stopPropagation();
  const pop = $("#symPop");
  pop.classList.toggle("hidden");
  if (!pop.classList.contains("hidden")) { $("#symSearch").value = ""; renderSymbolList(); $("#symSearch").focus(); }
};
$("#symSearch").oninput = (e) => renderSymbolList(e.target.value);
document.addEventListener("click", (e) => { if (!e.target.closest(".sym-picker")) $("#symPop").classList.add("hidden"); });

$("#start").onchange = (e) => { S.start = e.target.value; persist(); reload(); };
$("#end").onchange = (e) => { S.end = e.target.value; persist(); reload(); };
$$("#quickRange button").forEach((b) => b.onclick = () => {
  const d = +b.dataset.days;
  if (!d) { S.start = ""; S.end = ""; }
  else {
    const last = chart.times.length ? new Date(chart.times[chart.times.length - 1] * 1000) : new Date();
    const end = S.end ? new Date(S.end) : last;
    S.start = new Date(end.getTime() - d * 864e5).toISOString().slice(0, 10);
  }
  $("#start").value = S.start; $("#end").value = S.end; persist(); reload();
});

$("#dockBtn").onclick = () => { S.dock = S.dock === "right" ? "bottom" : "right"; applyDock(); persist(); };
function applyDock() {
  document.body.classList.toggle("dock-right", S.dock === "right");
  document.body.classList.toggle("dock-bottom", S.dock === "bottom");
  const t = $("#terminal");
  t.style.width = t.style.height = "";
  if (S.termSize && S.termSize[S.dock]) t.style[S.dock === "right" ? "width" : "height"] = S.termSize[S.dock] + "px";
}
// drag splitter
$("#splitter").addEventListener("mousedown", (e) => {
  e.preventDefault();
  const t = $("#terminal"), right = S.dock === "right";
  const start = right ? e.clientX : e.clientY, size0 = right ? t.offsetWidth : t.offsetHeight;
  const move = (ev) => {
    const d = (right ? ev.clientX : ev.clientY) - start;
    const v = Math.max(right ? 320 : 180, size0 - d);
    t.style[right ? "width" : "height"] = v + "px";
    S.termSize = { ...(S.termSize || {}), [S.dock]: v };
  };
  const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); persist(); };
  document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
});

$("#fitBtn").onclick = () => chart.fit();
$("#tgZones").onchange = (e) => chart.setZonesVisible(e.target.checked);
$("#tgSignals").onchange = (e) => chart.setShowSignals(e.target.checked);

/* tabs */
function showTab(name) {
  $$("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  $$(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
  if (name === "reports") loadReports();
}
$$("#tabs button").forEach((b) => b.onclick = () => showTab(b.dataset.tab));

/* =====================================================================
   Loading candles
   ===================================================================== */
const rangeParams = () => ({ symbol: S.symbol, interval: S.interval, start: S.start || null, end: S.end ? S.end + " 23:59:59" : null });

async function reload() {
  updateSymLabel();
  if (!S.symbol) return;
  const sym = S.symbols.find((s) => s.name === S.symbol);
  if (sym && !sym.stored.length) {
    $("#empty").classList.remove("hidden");
    return;
  }
  $("#empty").classList.add("hidden");
  if (replay && replay.active) { await replay.refresh(); return; }
  await guard("Loading candles…", async () => {
    const r = await api.candles(rangeParams());
    chart.clearGroup("strategy"); chart.clearGroup("equity");
    chart.setTrades([], null);
    chart.setCandles(r.candles);
    S.last = null;
    $("#summary").innerHTML = `${r.candles.t.length.toLocaleString()} bars · ${fmtTime(r.candles.t[0])} → ${fmtTime(r.candles.t[r.candles.t.length - 1])}`;
    await drawIndicators();
    if (S.mode && S.strategy) await runStrategy(S.mode === "deep" ? "backtest" : S.mode, true);
  });
}

/* =====================================================================
   Strategy library
   ===================================================================== */
function renderStrategyList(filter = "") {
  const f = filter.toLowerCase();
  const groups = {};
  S.strategies.filter((s) => !f || s.name.toLowerCase().includes(f) || s.category.toLowerCase().includes(f) || s.description.toLowerCase().includes(f))
    .forEach((s) => (groups[s.category] = groups[s.category] || []).push(s));
  $("#stratList").innerHTML = Object.entries(groups).map(([cat, list]) =>
    `<div class="lib-group">${esc(cat)} <span class="muted">${list.length}</span></div>` +
    list.map((s) => `<div class="lib-item ${s.name === S.strategy ? "active" : ""}" data-name="${esc(s.name)}" title="${esc(s.description)}">${esc(s.name)}</div>`).join("")
  ).join("") || `<div class="placeholder">No strategies found.</div>`;
  $$("#stratList .lib-item").forEach((el) => el.onclick = () => { S.strategy = el.dataset.name; persist(); renderStrategyList($("#stratSearch").value); renderStrategyDetail(); });
}
$("#stratSearch").oninput = (e) => renderStrategyList(e.target.value);

function paramInput(p, value, prefix) {
  const id = `${prefix}-${p.name}`;
  const v = value ?? p.default;
  if (p.type === "bool") return `<label class="chk" title="${esc(p.help)}"><input type="checkbox" id="${id}" data-p="${esc(p.name)}" ${v ? "checked" : ""}> ${esc(p.name)}</label>`;
  if (p.type === "select") return `<label title="${esc(p.help)}">${esc(p.name)}<select id="${id}" data-p="${esc(p.name)}">${p.options.map((o) => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select></label>`;
  const num = p.type === "int" || p.type === "float";
  return `<label title="${esc(p.help)}">${esc(p.name)}<input id="${id}" data-p="${esc(p.name)}" ${num ? `type="number" step="${p.step ?? "any"}"` : ""}
    ${p.min !== null && num ? `min="${p.min}"` : ""} ${p.max !== null && num ? `max="${p.max}"` : ""} value="${esc(v)}"></label>`;
}
function readParams(root) {
  const out = {};
  $$("[data-p]", root).forEach((el) => { out[el.dataset.p] = el.type === "checkbox" ? el.checked : el.value; });
  return out;
}

function settingsForm() {
  const st = { ...((S.defaults && S.defaults.settings) || {}), ...S.settings };
  const opt = (k, lab) => `<option value="${k}" ${st.cost_preset === k ? "selected" : ""}>${esc(lab)}</option>`;
  return `
  <details class="settings" ${S.settingsOpen ? "open" : ""}><summary>Backtest settings</summary>
    <div class="form-grid tight" id="setForm">
      <label>Capital<input type="number" data-s="init_cash" value="${st.init_cash}"></label>
      <label>Position size %<input type="number" data-s="size_pct" value="${st.size_pct}" min="1" max="100"></label>
      <label class="wide">Cost model<select data-s="cost_preset"><option value="">Market default</option>${Object.entries(S.costs).map(([k, c]) => opt(k, c.label)).join("")}</select></label>
      <label>Fees % / side<input type="number" step="0.001" data-s="fees_pct" value="${st.fees_pct ?? ""}" placeholder="preset"></label>
      <label>Slippage % / side<input type="number" step="0.001" data-s="slippage_pct" value="${st.slippage_pct ?? ""}" placeholder="preset"></label>
      <label>Fixed fee / order<input type="number" step="0.01" data-s="fixed_fee" value="${st.fixed_fee ?? ""}" placeholder="preset"></label>
      <label>Fill<select data-s="execution"><option value="next_open" ${st.execution === "next_open" ? "selected" : ""}>Next bar open</option><option value="close" ${st.execution === "close" ? "selected" : ""}>Same bar close</option></select></label>
      <label>Stop-loss % <input type="number" step="0.1" data-s="sl_pct" value="${st.sl_pct ?? ""}" placeholder="strategy"></label>
      <label>Take-profit %<input type="number" step="0.1" data-s="tp_pct" value="${st.tp_pct ?? ""}" placeholder="strategy"></label>
      <label class="chk"><input type="checkbox" data-s="trailing" ${st.trailing ? "checked" : ""}> Trailing stop</label>
      <label class="chk"><input type="checkbox" data-s="square_off" ${st.square_off ? "checked" : ""}> Intraday square-off</label>
      <label>Square-off at<input data-s="square_off_time" value="${st.square_off_time}"></label>
      <label>No entry after<input data-s="no_entry_after" value="${st.no_entry_after}"></label>
    </div>
    <button class="btn ghost sm" id="resetSet">Reset to defaults</button>
  </details>`;
}
function readSettings() {
  const out = {};
  $$("[data-s]").forEach((el) => {
    const k = el.dataset.s;
    if (el.type === "checkbox") out[k] = k === "trailing" ? (el.checked || null) : el.checked;
    else if (el.value === "") out[k] = null;
    else out[k] = el.type === "number" ? +el.value : el.value;
  });
  return out;
}

function renderStrategyDetail() {
  const s = S.strategies.find((x) => x.name === S.strategy);
  const box = $("#stratDetail");
  if (!s) { box.innerHTML = `<div class="placeholder">Select a strategy from the library.</div>`; return; }
  const vals = S.params[s.name] || {};
  box.innerHTML = `
    <div class="d-head"><div><div class="d-cat">${esc(s.category)}</div><h3>${esc(s.name)}</h3></div></div>
    <p class="d-desc">${esc(s.description || "")}</p>
    <div class="form-grid tight" id="paramForm">${s.params.map((p) => paramInput(p, vals[p.name], "p")).join("") || '<span class="muted small">No parameters.</span>'}</div>
    ${settingsForm()}
    <div class="actions">
      <button class="btn" id="btnApply" title="Plot signals and trade zones (fast)">▶ Apply</button>
      <button class="btn primary" id="btnBacktest" title="Apply + metrics, equity and drawdown">Backtest</button>
      <button class="btn accent" id="btnDeep" title="Full analysis + shareable report page">Deep backtest ↗</button>
    </div>
    <div id="deepLink"></div>
    <details class="code"><summary>Source · <span class="muted">${esc(s.module.replace(/\./g, "/"))}.py</span></summary>
      <pre><code>${highlightPy(s.source || "")}</code></pre></details>`;
  const save = () => { S.params[s.name] = readParams($("#paramForm")); S.settings = readSettings(); persist(); };
  $$("#paramForm [data-p], #setForm [data-s]").forEach((el) => el.onchange = save);
  $("details.settings").ontoggle = (e) => { S.settingsOpen = e.target.open; };
  $("#resetSet").onclick = () => { S.settings = {}; persist(); renderStrategyDetail(); };
  $("#btnApply").onclick = () => { save(); runStrategy("apply"); };
  $("#btnBacktest").onclick = () => { save(); runStrategy("backtest"); };
  $("#btnDeep").onclick = () => { save(); runStrategy("deep"); };
}

$("#reloadBtn").onclick = () => guard("Reloading strategies…", async () => {
  const r = await api.reload();
  await loadStrategies();
  toast(`Reloaded ${r.count} strategies` + (Object.keys(r.errors).length ? ` — ${Object.keys(r.errors).length} file(s) with errors` : ""),
    Object.keys(r.errors).length ? "error" : "ok");
});

async function loadStrategies() {
  const r = await api.strategies();
  S.strategies = r.strategies;
  $("#stratErrors").innerHTML = Object.entries(r.errors || {}).map(([f, e]) =>
    `<details class="err"><summary>⚠ ${esc(f)}.py failed to load</summary><pre>${esc(e)}</pre></details>`).join("");
  if (!S.strategies.find((x) => x.name === S.strategy))
    S.strategy = (S.strategies.find((x) => x.name === "EMA Crossover") || S.strategies[0] || {}).name || null;
  renderStrategyList($("#stratSearch").value);
  if (S.defaults) renderStrategyDetail();
}

/* =====================================================================
   Run strategy (apply / backtest / deep)
   ===================================================================== */
async function runStrategy(mode, silent = false) {
  if (!S.symbol || !S.strategy) return;
  const body = { ...rangeParams(), strategy: S.strategy, params: S.params[S.strategy] || {}, settings: S.settings };
  const label = { apply: "Applying strategy…", backtest: "Backtesting…", deep: "Running deep analysis…" }[mode];
  if (replay && replay.active) return runInReplay(mode, body, label);
  await guard(label, async () => {
    if (mode === "deep") {
      const d = await api.deep(body);
      const link = `<a class="btn accent wide" href="${d.url}" target="_blank" rel="noopener">📄 Open full report ↗</a>`;
      $("#deepLink").innerHTML = link;
      toast(`Report ready — <a href="${d.url}" target="_blank" rel="noopener">open it</a>`, "ok", true, 9000);
      mode = "backtest";                        // also refresh chart + results in the terminal
      S.lastDeep = d;
    }
    const r = await (mode === "apply" ? api.apply(body) : api.backtest(body));
    S.last = r; S.mode = mode;
    drawStrategy(r);
    if (mode === "backtest") { renderResults(r); if (!silent) showTab("results"); }
    renderTrades();
  });
}

function drawStrategy(r) {
  chart.clearGroup("strategy"); chart.clearGroup("equity");
  chart.setCandles(r.candles);
  drawStrategyLayers(r.chart, r.series);
  chart.setTrades(r.trades, r.chart.signals);
  const n = r.trades.length, w = r.trades.filter((t) => t.pnl > 0).length, pnl = r.trades.reduce((a, t) => a + t.pnl, 0);
  $("#summary").innerHTML = `<b>${esc(r.meta.strategy)}</b> · ${n} trades · win ${n ? ((w / n) * 100).toFixed(0) : 0}% · ` +
    `P&L <b class="${pnl >= 0 ? "pos" : "neg"}">${fmtNum(pnl)}</b> · <span class="muted">${r.meta.costs.preset}, ${r.meta.elapsed_ms} ms</span>`;
  $("#tradeCount").textContent = n || "";
}

/** strategy lines / panes / equity. update=true replaces values in place (replay exact mode). */
function drawStrategyLayers(c, series, update = false) {
  if (update) {
    let ok = true;
    for (const [name, vals] of Object.entries(c.overlays)) ok = chart.updateValues("strategy", name, vals) && ok;
    for (const ser of Object.values(c.panes)) for (const [name, vals] of Object.entries(ser)) ok = chart.updateValues("strategy", name, vals) && ok;
    if (series) {
      ok = chart.updateValues("equity", "Equity", series.equity) && ok;
      ok = chart.updateValues("equity", "Buy & hold", series.benchmark) && ok;
      ok = chart.updateValues("equity", "Drawdown %", series.drawdown) && ok;
    }
    if (ok) return;
  }
  chart.clearGroup("strategy"); chart.clearGroup("equity");
  let ci = 0;
  for (const [name, vals] of Object.entries(c.overlays)) chart.addLine("strategy", chart.main, name, vals, { color: PALETTE[ci++ % PALETTE.length] });
  for (const [pane, ser] of Object.entries(c.panes)) {
    const p = chart.pane("strat:" + pane, pane, 140);
    let k = 0;
    for (const [name, vals] of Object.entries(ser)) {
      if (/hist/i.test(name)) chart.addHistogram("strategy", p, name, vals);
      else chart.addLine("strategy", p, name, vals, { color: PALETTE[(k++ + 1) % PALETTE.length] });
    }
    chart.addLevels(p, c.levels[pane]);
  }
  if (series) {
    const eq = chart.pane("equity", "Equity vs buy & hold", 150);
    chart.addLine("equity", eq, "Equity", series.equity, { color: "#2962ff", width: 2 });
    chart.addLine("equity", eq, "Buy & hold", series.benchmark, { color: "#787b86", dashed: true });
    const dd = chart.pane("drawdown", "Drawdown %", 100);
    chart.addBaseline("equity", dd, "Drawdown %", series.drawdown);
  }
}

/* hovered trade card */
function showTradeCard(t, p) {
  const card = $("#tradeCard");
  if (!t || !p || !p.point) { card.classList.add("hidden"); return; }
  card.innerHTML = `
    <div class="tc-h"><span class="dir ${t.direction === "Long" ? "long" : "short"}">${t.direction}</span>
      <b class="${t.pnl > 0 ? "pos" : "neg"}">${t.return_pct >= 0 ? "+" : ""}${t.return_pct.toFixed(2)}%</b>
      <span class="muted">#${t.id + 1} · ${esc(t.exit_reason)}</span></div>
    <div class="tc-g">
      <span>Entry</span><b>${fmtNum(t.entry_price)}</b><span class="muted">${fmtTime(t.entry_t)}</span>
      <span>Exit</span><b>${fmtNum(t.exit_price)}</b><span class="muted">${t.status === "Open" ? "still open" : fmtTime(t.exit_t)}</span>
      <span>P&L</span><b class="${t.pnl > 0 ? "pos" : "neg"}">${fmtNum(t.pnl)}</b><span class="muted">fees ${fmtNum(t.fees)}</span>
      <span>MAE / MFE</span><b><span class="neg">${t.mae_pct.toFixed(2)}%</span> / <span class="pos">${t.mfe_pct.toFixed(2)}%</span></b><span class="muted">${t.bars} bars</span>
    </div>
    ${t.pnl <= 0 && t.mfe_pct > Math.abs(t.return_pct) ? `<div class="tc-note">Was up ${t.mfe_pct.toFixed(2)}% before closing red</div>` : ""}`;
  card.classList.remove("hidden");
}

/* =====================================================================
   Results & trades
   ===================================================================== */
function renderResults(r) {
  const m = metricMap(r.metrics);
  const deep = S.lastDeep && S.lastDeep.report_id ? `<a class="btn accent wide" href="${S.lastDeep.url}" target="_blank" rel="noopener">📄 Open full report ↗</a>` : "";
  $("#results").innerHTML = `
    <div class="res-head"><div><b>${esc(r.meta.strategy)}</b> <span class="muted">· ${esc(r.meta.symbol)} · ${r.meta.interval}</span></div>
      <div class="muted small">${r.meta.start} → ${r.meta.end} · ${r.meta.bars.toLocaleString()} bars</div></div>
    ${kpiCards(r.metrics)}
    ${S.lastDeep && S.lastDeep.insights ? `<h4 class="sub">Where it works / fails</h4>` + insightCards(S.lastDeep.insights.slice(0, 6)) : ""}
    ${deep}
    ${metricTables(r.metrics)}
    <p class="hint">Costs: ${esc(r.meta.costs.preset)} — fees ${r.meta.costs.fees_pct.toFixed(3)}%/side, slippage ${r.meta.costs.slippage_pct.toFixed(3)}%/side.
      ${esc(r.meta.costs.note || "")} Fills: ${r.meta.settings.execution === "next_open" ? "next bar open" : "same bar close"}.</p>`;
  S.lastDeep = null;
  void m;
}

function renderTrades() {
  const all = S.replayTrades || (S.last && S.last.trades) || [];
  let list = all.map((t, i) => ({ ...t, _i: i }));
  if (S.tradeFilter === "win") list = list.filter((t) => t.pnl > 0);
  if (S.tradeFilter === "loss") list = list.filter((t) => t.pnl <= 0);
  if (S.sort) {
    const { k, dir } = S.sort;
    list.sort((a, b) => (a[k] > b[k] ? 1 : a[k] < b[k] ? -1 : 0) * dir);
  }
  const keys = ["id", "direction", "entry_t", "exit_t", "entry_price", "exit_price", "pnl", "return_pct", "mae_pct", "mfe_pct", "bars", "exit_reason"];
  $("#tradeTable").innerHTML = TRADE_HEAD + `<tbody>${tradeRows(list).replace(/data-i="(\d+)"/g, (_, j) => `data-i="${list[+j]._i}"`)}</tbody>`;
  $$("#tradeTable th").forEach((th, j) => th.onclick = () => {
    const k = keys[j];
    S.sort = S.sort && S.sort.k === k ? { k, dir: -S.sort.dir } : { k, dir: -1 };
    renderTrades();
  });
  $$("#tradeTable tbody tr").forEach((tr) => tr.onclick = () => {
    $$("#tradeTable tr.sel").forEach((x) => x.classList.remove("sel"));
    tr.classList.add("sel");
    chart.focusTrade(+tr.dataset.i);
  });
}
$$("#tradeFilter button").forEach((b) => b.onclick = () => {
  $$("#tradeFilter button").forEach((x) => x.classList.toggle("active", x === b));
  S.tradeFilter = b.dataset.f; renderTrades();
});

/* =====================================================================
   Indicators
   ===================================================================== */
function renderIndicatorList(filter = "") {
  const f = filter.toLowerCase();
  const groups = {};
  S.indicatorDefs.filter((d) => !f || d.name.toLowerCase().includes(f) || d.category.toLowerCase().includes(f))
    .forEach((d) => (groups[d.category] = groups[d.category] || []).push(d));
  $("#indList").innerHTML = Object.entries(groups).map(([cat, list]) =>
    `<div class="lib-group">${esc(cat)}</div>` + list.map((d) => `<div class="lib-item" data-name="${esc(d.name)}">${esc(d.name)}
      <span class="tag">${d.overlay ? "overlay" : "pane"}</span></div>`).join("")).join("");
  $$("#indList .lib-item").forEach((el) => el.onclick = () => addIndicator(el.dataset.name));
}
$("#indSearch").oninput = (e) => renderIndicatorList(e.target.value);

function addIndicator(name) {
  const def = S.indicatorDefs.find((d) => d.name === name);
  const params = Object.fromEntries(def.params.map((p) => [p.name, p.default]));
  const id = Math.random().toString(36).slice(2, 8);
  S.indicators.push({ id, name, params, color: PALETTE[(S.indicators.length + 3) % PALETTE.length] });
  persist(); renderActiveIndicators(); drawIndicators([id]);
}

function renderActiveIndicators() {
  const box = $("#activeInd");
  if (!S.indicators.length) { box.innerHTML = `<div class="placeholder">Click an indicator to add it.</div>`; return; }
  box.innerHTML = S.indicators.map((ind) => {
    const def = S.indicatorDefs.find((d) => d.name === ind.name);
    if (!def) return "";
    return `<div class="ind-card" data-id="${ind.id}">
      <div class="ind-h"><input type="color" value="${ind.color}" data-color><b>${esc(ind.name)}</b>
        <button class="btn ghost icon sm" data-del title="Remove">×</button></div>
      <div class="form-grid tight">${def.params.map((p) => paramInput(p, ind.params[p.name], "i" + ind.id)).join("")}</div></div>`;
  }).join("");
  $$(".ind-card").forEach((card) => {
    const ind = S.indicators.find((x) => x.id === card.dataset.id);
    $$("[data-p]", card).forEach((el) => el.onchange = () => { ind.params = readParams(card); persist(); drawIndicators([ind.id]); });
    $("[data-color]", card).onchange = (e) => { ind.color = e.target.value; persist(); drawIndicators([ind.id]); };
    $("[data-del]", card).onclick = () => {
      chart.clearGroup("ind:" + ind.id); chart.removePane("ind:" + ind.id);
      S.indicators = S.indicators.filter((x) => x !== ind); persist(); renderActiveIndicators();
    };
  });
}

async function drawIndicators(ids = null) {
  if (!S.symbol || !chart.times.length) return;
  if (replay && replay.active) { await replay.refresh(); return; }
  const list = S.indicators.filter((x) => !ids || ids.includes(x.id));
  for (const ind of list) {
    try {
      const r = await api.indicator({ ...rangeParams(), name: ind.name, params: ind.params });
      drawIndicatorResult(ind, r);
    } catch (e) { toast(`${ind.name}: ${e.message}`, "error"); }
  }
}

function drawIndicatorResult(ind, r, update = false) {
  const label = `${ind.name} ${Object.values(r.params).join(", ")}`;
  const names = Object.keys(r.series);
  if (update && names.every((k) => chart.updateValues("ind:" + ind.id, names.length > 1 ? k : label, r.series[k]))) return;
  chart.clearGroup("ind:" + ind.id);
  const target = r.overlay ? chart.main : chart.pane("ind:" + ind.id, label, 130);
  names.forEach((k, j) => {
    const vals = r.series[k];
    const nm = names.length > 1 ? k : label;
    if (!r.overlay && (/hist/i.test(k) || ind.name === "Volume")) chart.addHistogram("ind:" + ind.id, target, nm, vals);
    else chart.addLine("ind:" + ind.id, target, nm, vals, { color: j === 0 ? ind.color : PALETTE[(j + 5) % PALETTE.length], width: 1.3 });
  });
  if (!r.overlay) chart.addLevels(target, r.levels);
}

/* =====================================================================
   Replay
   ===================================================================== */
function marketFee() {
  const st = { ...((S.defaults && S.defaults.settings) || {}), ...S.settings };
  if (st.fees_pct !== null && st.fees_pct !== undefined) return st.fees_pct + (st.slippage_pct ?? 0);
  const sym = S.symbols.find((x) => x.name === S.symbol);
  const key = st.cost_preset || (S.defaults && sym && S.defaults.market_costs[sym.market]);
  const c = S.costs[key];
  return c ? c.fees_pct + c.slippage_pct : 0;
}

const replay = new Replay(chart, api, {
  request: () => ({
    ...rangeParams(),
    strategy: S.mode && S.strategy ? S.strategy : null,
    params: S.params[S.strategy] || {}, settings: S.settings,
    indicators: S.indicators.map((i) => ({ key: i.id, name: i.name, params: i.params })),
  }),
  clearLayers: () => {
    chart.clearGroup("strategy"); chart.clearGroup("equity");
    Object.keys(chart.groups).filter((g) => g.startsWith("ind:")).forEach((g) => chart.clearGroup(g));
    chart.setTrades([], null);
  },
  drawStrategy: (part, update) => drawStrategyLayers(part.chart, part.series, update),
  drawIndicators: (list, update) => list.forEach((r) => {
    const ind = S.indicators.find((x) => x.id === r.key);
    if (ind) drawIndicatorResult(ind, r, update);
  }),
  onTrades: (trades) => { S.replayTrades = trades; $("#tradeCount").textContent = trades.length || ""; renderTrades(); },
  onExit: () => { S.replayTrades = null; $("#replayBtn").classList.remove("on"); reload(); },
  onLoaded: (rp) => {
    $("#summary").innerHTML = `<b>Replay</b> · ${esc(S.symbol)} ${S.interval} · the chart only knows the past
      <span class="muted">· Space play/pause · ←/→ step · Shift+→ ×10 · B/S/C trade · Esc exit</span>`;
  },
  feePct: marketFee,
  capital: () => ({ ...((S.defaults && S.defaults.settings) || {}), ...S.settings }).init_cash || 100000,
  busy,
});

$("#replayBtn").onclick = () => {
  if (replay.active || replay.selecting) { replay.exit(); return; }
  $("#replayBtn").classList.add("on");
  $("#results").innerHTML = `<div class="placeholder">Replay mode — results are hidden so the future stays unknown.<br>
    Press <b>Backtest</b> to compute metrics <b>up to the replay cursor</b>.</div>`;
  $("#summary").innerHTML = `<b>Replay</b> · click a candle to choose the starting point`;
  replay.pick();
};

async function runInReplay(mode, body, label) {
  if (mode === "apply") { S.mode = "apply"; persist(); await replay.refresh(); return; }
  // backtest / deep only see data up to the replay cursor
  const upto = replay.cursorEnd();
  await guard(label + " (up to replay cursor)", async () => {
    const b = { ...body, end: upto };
    if (mode === "deep") {
      const d = await api.deep(b);
      $("#deepLink").innerHTML = `<a class="btn accent wide" href="${d.url}" target="_blank" rel="noopener">📄 Open report (up to ${esc(upto)}) ↗</a>`;
      S.lastDeep = d;
    }
    const r = await api.backtest(b);
    renderResults(r);
    $("#results").insertAdjacentHTML("afterbegin", `<div class="hint warnbox">Replay: metrics computed on data up to <b>${esc(upto)}</b> only.</div>`);
    showTab("results");
    if (!S.mode) { S.mode = "apply"; await replay.refresh(); }
  });
}

/* =====================================================================
   Reports
   ===================================================================== */
async function loadReports() {
  const r = await api.reports().catch(() => ({ reports: [] }));
  const box = $("#reports");
  if (!r.reports.length) { box.innerHTML = `<div class="placeholder">No reports yet — run a <b>Deep backtest</b>.</div>`; return; }
  box.innerHTML = r.reports.map((x) => `
    <div class="rep">
      <div class="rep-main"><a href="/report.html?id=${encodeURIComponent(x.id)}" target="_blank" rel="noopener"><b>${esc(x.strategy)}</b></a>
        <div class="muted small">${esc(x.symbol)} · ${esc(x.interval)} · ${esc((x.start || "").slice(0, 10))} → ${esc((x.end || "").slice(0, 10))}</div>
        <div class="muted small">${esc(Object.entries(x.params || {}).map(([k, v]) => `${k}=${v}`).join(", "))}</div></div>
      <div class="rep-k"><span class="${(x.total_return ?? 0) >= 0 ? "pos" : "neg"}">${fmtMetric(x.total_return, "pct")}</span>
        <span class="muted small">Sharpe ${fmtMetric(x.sharpe, "ratio")} · ${x.trades ?? 0} trades</span>
        <span class="muted small">${esc((x.created || "").replace("T", " "))}</span></div>
      <button class="btn ghost icon sm" data-del="${esc(x.id)}" title="Delete">🗑</button>
    </div>`).join("");
  $$("#reports [data-del]").forEach((b) => b.onclick = async () => { await api.deleteReport(b.dataset.del); loadReports(); });
}

/* =====================================================================
   Data manager
   ===================================================================== */
const modal = $("#dataModal");
function openData(tab = "download") {
  modal.classList.remove("hidden");
  showDataTab(tab);
  fillDataForms();
}
$("#dataBtn").onclick = () => openData();
$("#emptyData").onclick = () => openData();
modal.addEventListener("click", (e) => { if (e.target === modal || e.target.closest("[data-close]")) modal.classList.add("hidden"); });
function showDataTab(t) {
  $$("#dataTabs button").forEach((b) => b.classList.toggle("active", b.dataset.dtab === t));
  $$("[data-dpanel]").forEach((p) => p.classList.toggle("active", p.dataset.dpanel === t));
  if (t === "stored") loadStored();
  if (t === "fyers") loadFyers();
}
$$("#dataTabs button").forEach((b) => b.onclick = () => showDataTab(b.dataset.dtab));

let SOURCES = {};
async function fillDataForms() {
  SOURCES = await api.sources().catch(() => ({}));
  const opts = S.symbols.map((s) => `<option ${s.name === S.symbol ? "selected" : ""}>${esc(s.name)}</option>`).join("");
  $("#dlSymbol").innerHTML = opts; $("#imSymbol").innerHTML = opts;
  const syncSrc = () => {
    const s = S.symbols.find((x) => x.name === $("#dlSymbol").value);
    const src = SOURCES[s?.source];
    $("#dlSource").value = src ? `${src.label} (${s.symbol})${src.ready ? "" : " — " + src.message}` : `${s?.source} (no downloader)`;
    $("#dlInterval").innerHTML = (src ? src.intervals : []).map((i) => `<option ${i === "5m" ? "selected" : ""}>${i}</option>`).join("");
  };
  $("#dlSymbol").onchange = syncSrc; syncSrc();
  if (!$("#dlStart").value) $("#dlStart").value = new Date(Date.now() - 365 * 864e5).toISOString().slice(0, 10);
  if (!$("#dlEnd").value) $("#dlEnd").value = new Date().toISOString().slice(0, 10);
}

$("#dlGo").onclick = async () => {
  try {
    const { job } = await api.download({ symbol: $("#dlSymbol").value, interval: $("#dlInterval").value,
      start: $("#dlStart").value + "T00:00:00", end: $("#dlEnd").value + "T23:59:59" });
    $("#dlStatus").textContent = "Downloading…"; $("#dlLog").textContent = "";
    pollJob(job);
  } catch (e) { $("#dlStatus").textContent = e.message; }
};
async function pollJob(id) {
  const j = await api.job(id);
  $("#dlLog").textContent = j.log.join("\n");
  $("#dlLog").scrollTop = 1e9;
  if (j.status === "running") return setTimeout(() => pollJob(id), 1000);
  if (j.status === "done") {
    $("#dlStatus").innerHTML = `<span class="pos">Done</span> — fetched ${j.result.fetched.toLocaleString()} candles, ${j.result.stored.toLocaleString()} stored.`;
    await refreshSymbols(); reload();
  } else $("#dlStatus").innerHTML = `<span class="neg">${esc(j.error)}</span>`;
}

async function loadStored() {
  const r = await api.inventory();
  $("#storedTable").innerHTML = `<thead><tr><th>Symbol</th><th>Source</th><th>Interval</th><th>Rows</th><th>First</th><th>Last</th><th></th></tr></thead><tbody>` +
    (r.files.map((f) => `<tr><td>${esc(f.symbol)}</td><td>${f.source}</td><td>${f.interval}</td><td class="num">${f.rows.toLocaleString()}</td>
      <td>${esc(f.first)}</td><td>${esc(f.last)}</td><td><button class="btn ghost sm" data-up="${esc(f.symbol)}|${f.interval}">Update</button></td></tr>`).join("")
      || `<tr><td colspan="7" class="muted">Nothing stored yet.</td></tr>`) + `</tbody>`;
  $$("[data-up]").forEach((b) => b.onclick = async () => {
    const [sym, iv] = b.dataset.up.split("|");
    try { const { job } = await api.update(sym, iv); showDataTab("download"); $("#dlStatus").textContent = `Updating ${sym}…`; pollJob(job); }
    catch (e) { toast(e.message, "error"); }
  });
}

$("#imGo").onclick = async () => {
  $("#imStatus").textContent = "Importing…";
  try {
    const r = await api.importCsv({ symbol: $("#imSymbol").value, interval: $("#imInterval").value, path: $("#imPath").value, dayfirst: $("#imDayfirst").checked });
    $("#imStatus").innerHTML = `<span class="pos">Imported ${r.imported.toLocaleString()} rows</span> (${r.stored.toLocaleString()} stored)`;
    await refreshSymbols(); reload();
  } catch (e) { $("#imStatus").innerHTML = `<span class="neg">${esc(e.message)}</span>`; }
};
$("#asGo").onclick = async () => {
  try {
    await api.addSymbol({ name: $("#asName").value.trim(), source: $("#asSource").value, symbol: $("#asSymbol").value.trim(), market: $("#asMarket").value });
    $("#asStatus").innerHTML = `<span class="pos">Added.</span> Now download its data.`;
    await refreshSymbols(); fillDataForms();
  } catch (e) { $("#asStatus").innerHTML = `<span class="neg">${esc(e.message)}</span>`; }
};
async function loadFyers() {
  const s = (await api.sources().catch(() => ({}))).fyers;
  $("#fyStatus").innerHTML = s ? (s.ready ? `<span class="pos">● ${esc(s.message)}</span>` : `<span class="neg">● ${esc(s.message)}</span>`) : "";
}
$("#fyLogin").onclick = async () => { try { const { url } = await api.fyersUrl(); window.open(url, "_blank"); } catch (e) { toast(e.message, "error"); } };
$("#fyGo").onclick = async () => { try { await api.fyersToken($("#fyCode").value.trim()); toast("Fyers token saved", "ok"); loadFyers(); } catch (e) { toast(e.message, "error"); } };

/* =====================================================================
   Boot
   ===================================================================== */
async function refreshSymbols() {
  const r = await api.symbols();
  S.symbols = r.symbols; S.costs = r.costs;
  if (!S.symbol || !S.symbols.find((s) => s.name === S.symbol)) S.symbol = (S.symbols.find((s) => s.stored.length) || S.symbols[0])?.name;
  updateSymLabel();
}

async function boot() {
  applyDock();
  renderIntervals();
  $("#start").value = S.start; $("#end").value = S.end;
  try {
    const [, , ind, def] = await Promise.all([refreshSymbols(), loadStrategies(), api.indicators(), api.defaults()]);
    S.indicatorDefs = ind.indicators; S.defaults = def; S.costs = def.costs;
    renderIndicatorList(); renderActiveIndicators(); renderStrategyDetail();
    await reload();
  } catch (e) {
    toast("Backend not reachable: " + e.message, "error", false, 15000);
  }
}
boot();
