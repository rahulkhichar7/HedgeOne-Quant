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
  // developer mode: develop on TRAIN, validate once on the hidden TEST period
  dev: { on: false, trainStart: "", trainEnd: "", testStart: "", testEnd: "", ...(saved.dev || {}) },
  devPeeks: saved.devPeeks || {},      // {strategy: how many times the test period was looked at}
  uniSel: saved.uniSel || null,        // last universe selection
  optCfg: saved.optCfg || {},          // {strategy: {grid, objective, min_trades, constraint}}
  devRevealed: false,
  symbols: [], strategies: [], indicatorDefs: [], defaults: null, costs: {},
  last: null, mode: null, tradeFilter: "all", sort: null,
};
const persist = () => {
  try {
    localStorage.setItem("h1-state", JSON.stringify({
      symbol: S.symbol, interval: S.interval, start: S.start, end: S.end, strategy: S.strategy,
      params: S.params, settings: S.settings, indicators: S.indicators, dock: S.dock, termSize: S.termSize,
      dev: S.dev, devPeeks: S.devPeeks, uniSel: S.uniSel, optCfg: S.optCfg,
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
const normalRange = () => ({ symbol: S.symbol, interval: S.interval, start: S.start || null, end: S.end ? S.end + " 23:59:59" : null });
/* in developer mode everything except the train/test Backtest only ever sees the TRAIN period */
const rangeParams = () => S.dev.on
  ? { symbol: S.symbol, interval: S.interval, start: S.dev.trainStart || null, end: S.dev.trainEnd ? S.dev.trainEnd + " 23:59:59" : null }
  : normalRange();

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
    hideTest();
    $("#summary").innerHTML = `${r.candles.t.length.toLocaleString()} bars · ${fmtTime(r.candles.t[0])} → ${fmtTime(r.candles.t[r.candles.t.length - 1])}`;
    await drawIndicators();
    // dev mode: re-apply on the train period, but never reveal the test period without a click on Backtest
    const again = S.mode === "deep" ? "backtest" : S.mode;
    if (again && S.strategy) await runStrategy(S.dev.on && again === "backtest" ? "apply" : again, true);
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
      <button class="btn" id="btnApply" title="Plot signals and trade zones (fast)${S.dev.on ? " — train period only" : ""}">▶ Apply</button>
      <button class="btn primary" id="btnBacktest" title="${S.dev.on ? "Backtest the TRAIN and the hidden TEST period separately and compare them" : "Apply + metrics, equity and drawdown"}">${S.dev.on ? "Train vs test" : "Backtest"}</button>
      <button class="btn accent" id="btnDeep" title="Full analysis + shareable report page${S.dev.on ? " (train period)" : ""}">${S.dev.on ? "Deep (train)" : "Deep backtest"} ↗</button>
    </div>
    <div class="actions2">
      <button class="btn" id="btnOpt" title="Grid-search the parameters${S.dev.on ? " on the TRAIN period" : ""} — report opens in a new tab">⚙ Optimize ↗</button>
      <button class="btn" id="btnUni" ${S.dev.on ? "disabled" : ""} title="${S.dev.on ? "Universe testing is off in developer mode — validate on the test period first, then switch dev mode off" : "Run these parameters on many stocks / indices / crypto — report opens in a new tab"}">🌐 Universe test ↗</button>
    </div>
    ${S.dev.on ? `<div class="devnote"><b>Developer mode.</b> Apply, indicators, replay and the optimizer only see the <b>train</b> period
      (${esc(S.dev.trainStart || "?")} → ${esc(S.dev.trainEnd || "?")}). <b>Train vs test</b> also runs the hidden <b>test</b> period and compares both.</div>` : ""}
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
  $("#btnOpt").onclick = () => { save(); openOptimizer(); };
  $("#btnUni").onclick = () => { save(); openUniverse(); };
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
  if (S.dev.on && mode === "backtest") return runDev();
  if (S.dev.on) hideTest();
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

async function drawIndicators(ids = null, range = null) {
  if (!S.symbol || !chart.times.length) return;
  if (replay && replay.active) { await replay.refresh(); return; }
  const list = S.indicators.filter((x) => !ids || ids.includes(x.id));
  if (!range && S.devRevealed) range = devFullRange();      // chart currently shows train + test
  for (const ind of list) {
    try {
      const r = await api.indicator({ ...(range || rangeParams()), name: ind.name, params: ind.params });
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
  const [deep, research] = await Promise.all([api.reports().catch(() => ({ reports: [] })), api.researchReports().catch(() => ({ reports: [] }))]);
  const box = $("#reports");
  if (!deep.reports.length && !research.reports.length) {
    box.innerHTML = `<div class="placeholder">No reports yet — run a <b>Deep backtest</b>, an <b>Optimize</b> or a <b>Universe test</b>.</div>`;
    return;
  }
  const opt = research.reports.filter((x) => x.kind === "optimize"), uni = research.reports.filter((x) => x.kind === "universe");
  const del = (attr) => `<button class="btn ghost icon sm" ${attr} title="Delete">🗑</button>`;
  const params = (p) => esc(Object.entries(p || {}).map(([k, v]) => `${k}=${v}`).join(", "));
  box.innerHTML =
    (opt.length ? `<div class="rep-sec">Optimizations</div>` + opt.map((x) => `
      <div class="rep">
        <div class="rep-main"><span class="kind opt">OPT</span>${x.dev ? `<span class="kind dev">TRAIN</span>` : ""}<a href="/optimize.html?id=${encodeURIComponent(x.id)}" target="_blank" rel="noopener"><b>${esc(x.strategy)}</b></a>
          <div class="muted small">${esc(x.symbol)} · ${esc(x.interval)} · ${esc((x.start || "").slice(0, 10))} → ${esc((x.end || "").slice(0, 10))} · ${(x.combos || 0).toLocaleString()} combinations</div>
          <div class="muted small">best: ${params(x.best_params)}</div></div>
        <div class="rep-k"><span>${esc(x.objective || "")} ${fmtMetric(x.best, x.objective && /return|CAGR|drawdown|Win|trade|Excess/i.test(x.objective) ? "pct" : "ratio")}</span>
          <span class="muted small">${esc((x.created || "").replace("T", " "))}</span></div>
        ${del(`data-rdel="optimize|${esc(x.id)}"`)}
      </div>`).join("") : "") +
    (uni.length ? `<div class="rep-sec">Universe tests</div>` + uni.map((x) => `
      <div class="rep">
        <div class="rep-main"><span class="kind uni">UNI</span><a href="/universe.html?id=${encodeURIComponent(x.id)}" target="_blank" rel="noopener"><b>${esc(x.strategy)}</b></a>
          <div class="muted small">${x.symbols} securities · ${esc(x.interval)} · ${esc((x.start || "all").slice(0, 10))} → ${esc((x.end || "").slice(0, 10))}</div>
          <div class="muted small">${params(x.params)}</div></div>
        <div class="rep-k"><span>${x.profitable ?? 0} / ${x.ok ?? 0} profitable</span>
          <span class="muted small">median ${fmtMetric(x.median_return, "pct")}</span>
          <span class="muted small">${esc((x.created || "").replace("T", " "))}</span></div>
        ${del(`data-rdel="universe|${esc(x.id)}"`)}
      </div>`).join("") : "") +
    (deep.reports.length ? `<div class="rep-sec">Deep backtests</div>` + deep.reports.map((x) => `
    <div class="rep">
      <div class="rep-main"><a href="/report.html?id=${encodeURIComponent(x.id)}" target="_blank" rel="noopener"><b>${esc(x.strategy)}</b></a>
        <div class="muted small">${esc(x.symbol)} · ${esc(x.interval)} · ${esc((x.start || "").slice(0, 10))} → ${esc((x.end || "").slice(0, 10))}</div>
        <div class="muted small">${params(x.params)}</div></div>
      <div class="rep-k"><span class="${(x.total_return ?? 0) >= 0 ? "pos" : "neg"}">${fmtMetric(x.total_return, "pct")}</span>
        <span class="muted small">Sharpe ${fmtMetric(x.sharpe, "ratio")} · ${x.trades ?? 0} trades</span>
        <span class="muted small">${esc((x.created || "").replace("T", " "))}</span></div>
      ${del(`data-del="${esc(x.id)}"`)}
    </div>`).join("") : "");
  $$("#reports [data-del]").forEach((b) => b.onclick = async () => { await api.deleteReport(b.dataset.del); loadReports(); });
  $$("#reports [data-rdel]").forEach((b) => b.onclick = async () => {
    const [kind, id] = b.dataset.rdel.split("|");
    await api.deleteResearchReport(kind, id); loadReports();
  });
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
  $("#dataModal .modal-box").classList.toggle("bulk-open", t === "bulk");
  if (t === "bulk") loadBulk();
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

/* ---------------- bulk download: many securities / intervals / periods in one go ---------------- */
const BULK = (() => {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem("h1-bulk") || "{}"); } catch (e) { /* ignore */ }
  return { rows: saved.rows || {}, common: saved.common || {}, inv: [], job: null, items: [], state: {} };
})();
const saveBulk = () => { try { localStorage.setItem("h1-bulk", JSON.stringify({ rows: BULK.rows, common: BULK.common })); } catch (e) { /* ignore */ } };
const today = () => new Date().toISOString().slice(0, 10);
const daysAgo = (n) => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);
const storedFor = (sym, iv) => BULK.inv.find((f) => f.symbol === sym && f.interval === iv);

function bulkRow(s) {
  const src = SOURCES[s.source];
  let r = BULK.rows[s.name];
  if (!r) {
    const iv = src.intervals.includes("5m") ? "5m" : src.intervals[0];
    const st = storedFor(s.name, iv);
    r = BULK.rows[s.name] = { on: false, interval: iv, start: st ? st.last.slice(0, 10) : daysAgo(365), end: today() };
  }
  if (!src.intervals.includes(r.interval)) r.interval = src.intervals[0];
  return r;
}

async function loadBulk() {
  SOURCES = await api.sources().catch(() => SOURCES);     // always fresh: login state changes
  BULK.inv = (await api.inventory().catch(() => ({ files: [] }))).files || [];
  const all = [...new Set(Object.values(SOURCES).flatMap((x) => x.intervals))];
  const order = ["1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "1d", "3d", "1w", "1M"];
  all.sort((a, b) => order.indexOf(a) - order.indexOf(b));
  const c = BULK.common;
  $("#bkIv").innerHTML = all.map((i) => `<option ${i === (c.interval || "5m") ? "selected" : ""}>${i}</option>`).join("");
  $("#bkStart").value = c.start || daysAgo(365);
  $("#bkEnd").value = c.end || today();
  renderBulk();
}

function bulkSymbols() {
  const f = $("#bkSearch").value.toLowerCase();
  return S.symbols.filter((s) => SOURCES[s.source] && (!f || s.name.toLowerCase().includes(f) || s.symbol.toLowerCase().includes(f)));
}

function renderBulk() {
  const running = !!BULK.job;
  const groups = {};
  bulkSymbols().forEach((s) => (groups[s.source] = groups[s.source] || []).push(s));
  const stTxt = (name) => {
    const x = BULK.state[name];
    if (!x) return "";
    return `<span class="st ${x.cls}">${esc(x.text)}</span>`;
  };
  $("#bkTable").innerHTML = `<thead><tr><th></th><th>Security</th><th>Interval</th><th>From</th><th>To</th><th>Stored (this interval)</th><th>Status</th></tr></thead><tbody>` +
    Object.entries(groups).map(([src, list]) => {
      const info = SOURCES[src];
      return `<tr class="grp"><td colspan="7">${esc(info.label)} · ${list.length}
          ${src === "fyers" ? `<span class="muted" style="text-transform:none;letter-spacing:0;font-weight:400;margin-left:6px" title="Earlier start dates are moved to the earliest allowed day automatically">Standard plan: intraday 1 yr · daily 5 yrs back</span>` : ""}
          ${info.ready ? "" : `<span class="srcwarn">⚠ ${esc(info.message || "not ready")}${info.login ? ` — <a href="#" data-fylogin>log in</a>` : ""}</span>`}
          <button class="btn ghost sm" data-ga="${src}">select all</button><button class="btn ghost sm" data-gn="${src}">none</button></td></tr>` +
        list.map((s) => {
          const r = bulkRow(s), st = storedFor(s.name, r.interval);
          return `<tr class="${r.on ? "" : "off"}" data-b="${esc(s.name)}">
            <td><input type="checkbox" data-k="on" ${r.on ? "checked" : ""} ${running ? "disabled" : ""}></td>
            <td class="nm"><b>${esc(s.name)}</b><small>${esc(s.symbol)}</small></td>
            <td><select data-k="interval" ${running ? "disabled" : ""}>${info.intervals.map((i) => `<option ${i === r.interval ? "selected" : ""}>${i}</option>`).join("")}</select></td>
            <td><input type="date" data-k="start" value="${esc(r.start)}" ${running ? "disabled" : ""}></td>
            <td><input type="date" data-k="end" value="${esc(r.end)}" ${running ? "disabled" : ""}></td>
            <td class="stored">${st ? `${esc(st.first.slice(0, 10))} → ${esc(st.last.slice(0, 10))} · ${st.rows.toLocaleString()}` : "—"}</td>
            <td class="stc">${stTxt(s.name)}</td></tr>`;
        }).join("");
    }).join("") + `</tbody>`;
  $$("#bkTable tr[data-b]").forEach((tr) => {
    const r = BULK.rows[tr.dataset.b];
    $$("[data-k]", tr).forEach((el) => el.onchange = () => {
      r[el.dataset.k] = el.type === "checkbox" ? el.checked : el.value;
      saveBulk();
      if (el.dataset.k === "on") { tr.classList.toggle("off", !el.checked); bulkCount(); }
      if (el.dataset.k === "interval") renderBulk();       // refresh the "stored" column
    });
  });
  const inGroup = (src) => bulkSymbols().filter((s) => s.source === src);
  $$("#bkTable [data-ga]").forEach((b) => b.onclick = () => { if (!running) { inGroup(b.dataset.ga).forEach((s) => { BULK.rows[s.name].on = true; }); saveBulk(); renderBulk(); } });
  $$("#bkTable [data-gn]").forEach((b) => b.onclick = () => { if (!running) { inGroup(b.dataset.gn).forEach((s) => { BULK.rows[s.name].on = false; }); saveBulk(); renderBulk(); } });
  $$("#bkTable [data-fylogin]").forEach((a) => a.onclick = (e) => { e.preventDefault(); showDataTab("fyers"); });
  bulkCount();
}

function bulkSelected() { return S.symbols.filter((s) => SOURCES[s.source] && BULK.rows[s.name] && BULK.rows[s.name].on); }
function bulkCount() {
  const sel = bulkSelected();
  const notReady = sel.filter((s) => !SOURCES[s.source].ready).length;
  const running = !!BULK.job;
  $("#bkCount").innerHTML = running ? `Downloading… <b>${BULK.done || 0}</b> of ${BULK.items.length} finished` :
    `<b>${sel.length}</b> selected` + (notReady ? ` · <span class="neg">${notReady} from a source that isn't ready</span> (they'll fail — log in first)` : "");
  $("#bkGo").disabled = running || !sel.length;
  ["#bkApply", "#bkFill"].forEach((id) => { $(id).disabled = running; });
}

$("#bkSearch").oninput = () => renderBulk();
$$("#bkQuick button").forEach((b) => b.onclick = () => {
  if (BULK.job) return;
  const q = b.dataset.q;
  if (q === "failed" && !Object.values(BULK.state).some((x) => x.cls === "err")) { toast("Nothing failed in the last run.", "info"); return; }
  bulkSymbols().forEach((s) => {
    bulkRow(s).on = q === "all" ? true : q === "data" ? s.stored.length > 0
      : q === "failed" ? (BULK.state[s.name] || {}).cls === "err" : false;
  });
  saveBulk(); renderBulk();
});
["bkIv", "bkStart", "bkEnd"].forEach((id) => { $("#" + id).onchange = () => {
  BULK.common = { interval: $("#bkIv").value, start: $("#bkStart").value, end: $("#bkEnd").value }; saveBulk();
}; });
$("#bkApply").onclick = () => {
  const iv = $("#bkIv").value, a = $("#bkStart").value, b = $("#bkEnd").value;
  const skipped = [];
  bulkSelected().forEach((s) => {
    const r = BULK.rows[s.name];
    if (SOURCES[s.source].intervals.includes(iv)) r.interval = iv; else skipped.push(s.name);
    if (a) r.start = a;
    if (b) r.end = b;
  });
  saveBulk(); renderBulk();
  if (skipped.length) toast(`${iv} isn't offered by the source of: ${skipped.join(", ")} — their interval was left as it was.`, "info", false, 9000);
};
$("#bkFill").onclick = () => {
  let n = 0;
  bulkSelected().forEach((s) => {
    const r = BULK.rows[s.name], st = storedFor(s.name, r.interval);
    if (st) { r.start = st.last.slice(0, 10); r.end = today(); n++; }
  });
  saveBulk(); renderBulk();
  toast(n ? `${n} row(s) now start at their last stored candle (only missing data will be fetched).` : "None of the selected rows has data stored for its interval yet.", n ? "ok" : "info");
};

$("#bkGo").onclick = async () => {
  const sel = bulkSelected();
  const bad = sel.filter((s) => { const r = BULK.rows[s.name]; return !r.start || (r.end && r.end < r.start); });
  if (bad.length) { toast(`Check the dates of: ${bad.map((s) => s.name).join(", ")}`, "error", false, 8000); return; }
  const items = sel.map((s) => { const r = BULK.rows[s.name]; return { symbol: s.name, interval: r.interval, start: r.start + "T00:00:00", end: (r.end || today()) + "T23:59:59" }; });
  try {
    const { job } = await api.downloadMany(items);
    BULK.job = job; BULK.items = items; BULK.done = 0; BULK.state = {};
    items.forEach((it) => { BULK.state[it.symbol] = { cls: "queued", text: "queued" }; });
    $("#bkBar").classList.remove("hidden");
    renderBulk();
    pollBulk();
  } catch (e) { toast(e.message, "error", false, 9000); }
};

async function pollBulk() {
  let j;
  try { j = await api.job(BULK.job); } catch (e) { BULK.job = null; renderBulk(); return; }
  let done = 0;
  for (const line of j.log || []) {
    const m = /^@item (\d+) (\w+) ?(.*)$/.exec(line);
    if (!m) continue;
    const it = BULK.items[+m[1]];
    if (!it) continue;
    if (m[2] === "running") BULK.state[it.symbol] = { cls: "run", text: "downloading…" };
    else if (m[2] === "done") { const [f, st] = m[3].split(" ").map(Number); BULK.state[it.symbol] = { cls: "ok", text: `✓ ${f.toLocaleString()} fetched · ${st.toLocaleString()} stored` }; }
    else if (m[2] === "error") BULK.state[it.symbol] = { cls: "err", text: "✗ " + m[3] };
  }
  for (const line of j.log || []) {       // latest progress text of the running item
    const m = /^@log (\d+) (.*)$/.exec(line);
    if (m && BULK.items[+m[1]] && BULK.state[BULK.items[+m[1]].symbol].cls === "run")
      BULK.state[BULK.items[+m[1]].symbol].text = (/^waiting|rate limit/.test(m[2]) ? "⏸ " : "downloading… ") + m[2].slice(0, 90);
  }
  if (j.status !== "running" && j.result) {
    j.result.results.forEach((r) => {
      const it = BULK.items[r.i];
      BULK.state[it.symbol] = r.ok ? { cls: "ok", text: `✓ ${r.fetched.toLocaleString()} fetched · ${r.stored.toLocaleString()} stored` } : { cls: "err", text: "✗ " + r.error };
    });
  }
  done = Object.values(BULK.state).filter((x) => x.cls === "ok" || x.cls === "err").length;
  BULK.done = done;
  $("#bkBar i").style.width = `${Math.round((done / BULK.items.length) * 100)}%`;
  if (j.status === "running") {
    if (!$("#dataModal").classList.contains("hidden") && $("[data-dpanel=bulk]").classList.contains("active")) renderBulk(); else bulkCount();
    setTimeout(pollBulk, 1000);
    return;
  }
  BULK.job = null;
  const ok = j.result ? j.result.ok : 0, failed = j.result ? j.result.failed : 0;
  toast(j.status === "error" ? `Bulk download failed: ${j.error}` : `Bulk download finished — ${ok} done${failed ? `, ${failed} failed (see the Status column)` : ""}.`,
    j.status === "error" || failed ? "error" : "ok", false, 9000);
  await refreshSymbols();
  BULK.inv = (await api.inventory().catch(() => ({ files: [] }))).files || [];
  renderBulk();
  reload();
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
$("#fyGo").onclick = async () => {
  const b = $("#fyGo"); b.disabled = true;
  try {
    await api.fyersToken($("#fyCode").value.trim());
    toast("Fyers token saved — you're logged in for today.", "ok");
    $("#fyCode").value = "";
    loadFyers();
    SOURCES = await api.sources().catch(() => SOURCES);
  } catch (e) {
    toast(/auth|code|expired|invalid/i.test(e.message) ? e.message + " — the auth_code is single-use and expires within minutes: log in again and paste the new URL." : e.message, "error", false, 12000);
  } finally { b.disabled = false; }
};

/* =====================================================================
   Developer mode — develop on TRAIN, validate on a hidden TEST period
   ===================================================================== */
const dayAdd = (d, n) => { const x = new Date(d + "T00:00:00Z"); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
const DEV_KEYS = { trStart: "trainStart", trEnd: "trainEnd", teStart: "testStart", teEnd: "testEnd" };

function applyDevUi() {
  document.body.classList.toggle("dev", S.dev.on);
  $("#devBtn").classList.toggle("on", S.dev.on);
  $("#devBtn").textContent = S.dev.on ? "🧪 Dev mode: on" : "🧪 Dev mode";
  Object.entries(DEV_KEYS).forEach(([id, k]) => { $("#" + id).value = S.dev[k] || ""; });
  updateTestState();
}
function updateTestState() {
  const el = $("#testState");
  el.textContent = S.devRevealed ? "👁" : "🔒";
  el.title = S.devRevealed ? "Test period shown (you pressed Backtest)" : "Test period hidden until you press Backtest";
  el.classList.toggle("open", S.devRevealed);
}

function devError() {
  const d = S.dev;
  if (!d.trainStart || !d.trainEnd || !d.testStart || !d.testEnd) return "Set all four train / test dates (or click 70/30).";
  if (d.trainEnd < d.trainStart) return "Train period: the end is before the start.";
  if (d.testEnd < d.testStart) return "Test period: the end is before the start.";
  if (!(d.trainEnd < d.testStart || d.testEnd < d.trainStart)) return "Train and test periods overlap — the test must be data the strategy has never seen.";
  return null;
}

function devFullRange() {
  const a = [S.dev.trainStart, S.dev.testStart].sort()[0], b = [S.dev.trainEnd, S.dev.testEnd].sort()[1];
  return { symbol: S.symbol, interval: S.interval, start: a, end: b + " 23:59:59" };
}

/** split the stored data (or the normal date range, if one is set) into train / test */
async function devSplit(frac, quiet = false) {
  let a = S.start, b = S.end;
  if (!a || !b) {
    const inv = await api.inventory().catch(() => ({ files: [] }));
    const rows = (inv.files || []).filter((f) => f.symbol === S.symbol && f.first);
    if (!rows.length) { if (!quiet) toast("No stored data for this symbol yet — download it first.", "error"); return; }
    a = a || rows.map((r) => r.first.slice(0, 10)).sort()[0];
    b = b || rows.map((r) => r.last.slice(0, 10)).sort().slice(-1)[0];
  }
  const days = Math.round((Date.parse(b) - Date.parse(a)) / 864e5);
  if (days < 4) { if (!quiet) toast("The date range is too short to split.", "error"); return; }
  const cut = dayAdd(a, Math.max(1, Math.floor(days * frac)));
  Object.assign(S.dev, { trainStart: a, trainEnd: cut, testStart: dayAdd(cut, 1), testEnd: b });
  persist(); applyDevUi();
  if (!quiet) { S.devRevealed = false; renderStrategyDetail(); reload(); toast(`Train ${a} → ${cut} · test ${dayAdd(cut, 1)} → ${b}`, "ok"); }
}

async function toggleDev() {
  if (replay && (replay.active || replay.selecting)) { toast("Exit replay first.", "error"); return; }
  S.dev.on = !S.dev.on;
  S.devRevealed = false;
  if (S.dev.on && devError()) await devSplit(0.7, true);
  persist(); applyDevUi(); renderStrategyDetail();
  $("#results").innerHTML = `<div class="placeholder">${S.dev.on ? "Developer mode — press <b>Train vs test</b> to backtest both periods and compare them." : "Run <b>Backtest</b> to see metrics."}</div>`;
  toast(S.dev.on ? "Developer mode on — the chart now shows the TRAIN period only. The test period stays hidden until you press Backtest."
    : "Developer mode off — back to the normal date range.", "ok", false, 7000);
  await reload();
}
$("#devBtn").onclick = toggleDev;
$$("#devSplit button").forEach((b) => b.onclick = () => devSplit(+b.dataset.split));
Object.entries(DEV_KEYS).forEach(([id, k]) => {
  $("#" + id).onchange = (e) => {
    S.dev[k] = e.target.value; S.devRevealed = false; persist(); updateTestState();
    const err = devError();
    if (err) { toast(err, "error"); return; }
    renderStrategyDetail(); reload();
  };
});

async function runDev() {
  const err = devError();
  if (err) { toast(err, "error"); return; }
  const body = { symbol: S.symbol, interval: S.interval, strategy: S.strategy, params: S.params[S.strategy] || {}, settings: S.settings,
    train: { start: S.dev.trainStart, end: S.dev.trainEnd }, test: { start: S.dev.testStart, end: S.dev.testEnd } };
  await guard("Backtesting train + test…", async () => {
    const r = await api.devBacktest(body);
    S.devPeeks[S.strategy] = (S.devPeeks[S.strategy] || 0) + 1;
    persist();
    S.last = r; S.mode = "backtest"; S.devRevealed = true; S.lastDeep = null;
    drawDev(r);
    renderDevResults(r);
    renderTrades();
    updateTestState();
    showTab("results");
    await drawIndicators(null, devFullRange());
  });
}

function drawDev(r) {
  chart.clearGroup("strategy"); chart.clearGroup("equity");
  chart.setCandles(r.full.candles);
  drawStrategyLayers(r.full.chart, null);
  // each period starts from fresh capital -> show % return from its own start so both are comparable
  const init = r.meta.settings.init_cash;
  const pct = (arr) => arr.map((v) => (v === null || v === undefined ? null : (v / init) * 100 - 100));
  const eq = chart.pane("equity", "Return % — train (blue) | test (orange), each from its own start", 150);
  chart.addLine("equity", eq, "Train return %", pct(r.train.series.equity), { color: "#2962ff", width: 2 });
  chart.addLine("equity", eq, "Test return %", pct(r.test.series.equity), { color: "#ff9800", width: 2 });
  chart.addLine("equity", eq, "Buy & hold %", pct(r.train.series.benchmark.map((v, i) => v ?? r.test.series.benchmark[i])), { color: "#787b86", dashed: true });
  const dd = chart.pane("drawdown", "Drawdown %", 100);
  chart.addBaseline("equity", dd, "Drawdown %", r.train.series.drawdown.map((v, i) => v ?? r.test.series.drawdown[i]));
  chart.setTrades(r.trades, r.full.chart.signals);
  const k = (x, key) => x.kp[key];
  $("#summary").innerHTML = `<b>${esc(r.meta.strategy)}</b> · <span class="dv-tag train">Train</span> ${fmtMetric(k(r.train, "total_return"), "pct")}, Sharpe ${fmtMetric(k(r.train, "sharpe"), "ratio")}
    · <span class="dv-tag test">Test</span> <b class="${(k(r.test, "total_return") ?? 0) >= 0 ? "pos" : "neg"}">${fmtMetric(k(r.test, "total_return"), "pct")}</b>, Sharpe ${fmtMetric(k(r.test, "sharpe"), "ratio")}
    · <span class="muted">${r.meta.elapsed_ms} ms</span>`;
  $("#tradeCount").textContent = r.trades.length || "";
  showTest(r.test.offset > r.train.offset ? r.test.offset : null);
  // new panes make the chart re-layout for a moment: fit (show both periods) once it has a width again
  const settle = (n = 0) => {
    if (axisScale().width() > 0 || n > 40) { chart.fit(); setTimeout(positionShade, 40); }
    else setTimeout(() => settle(n + 1), 50);
  };
  setTimeout(settle, 80);
}

/* orange overlay over the test period of the chart */
let shadeIdx = null;
/* all panes share one time range, but only the bottom pane shows (and measures) the time axis */
const axisScale = () => chart.panes[chart.panes.length - 1].chart.timeScale();
function showTest(idx) { shadeIdx = idx; positionShade(); }
function hideTest() { shadeIdx = null; S.devRevealed = false; positionShade(); if (S.dev.on) updateTestState(); }
function positionShade() {
  const el = $("#devShade");
  if (shadeIdx === null || !chart.times.length) { el.classList.add("hidden"); return; }
  const ts = axisScale(), host = $("#chart");
  const w = ts.width();
  if (w <= 0) {                      // chart is re-laying out (panes added): try again shortly
    if ((positionShade.retry = (positionShade.retry || 0) + 1) < 20) setTimeout(positionShade, 60);
    return;
  }
  positionShade.retry = 0;
  const vr = ts.getVisibleLogicalRange(), at = shadeIdx - 0.5;
  if (!vr || at >= vr.to) { el.classList.add("hidden"); return; }          // test period is off-screen right
  // bars are evenly spaced, so the visible logical range maps linearly onto the plot width
  const x = Math.max(0, ((at - vr.from) / (vr.to - vr.from || 1)) * w);
  if (x >= w) { el.classList.add("hidden"); return; }
  Object.assign(el.style, { left: host.offsetLeft + x + "px", width: w - x + "px", top: host.offsetTop + "px", height: host.offsetHeight + "px" });
  el.classList.remove("hidden");
}
chart.main.chart.timeScale().subscribeVisibleLogicalRangeChange(() => positionShade());
new ResizeObserver(() => positionShade()).observe($("#chart"));
new ResizeObserver(() => positionShade()).observe(chart.main.el);

const BETTER_LOW = new Set(["volatility"]);
const NEUTRAL = new Set(["trades", "exposure"]);
function renderDevResults(r) {
  const m = r.meta, v = r.verdict, peeks = S.devPeeks[m.strategy] || 1;
  const icon = { good: "✔", warn: "!", bad: "✖" }[v.level] || "•";
  const rows = r.compare.map((c) => {
    let dtext = "", cls = "";
    if (c.diff !== null && c.diff !== undefined && Number.isFinite(c.diff)) {
      const sign = c.diff > 0 ? "+" : "";
      dtext = c.fmt === "pct" ? `${sign}${c.diff.toFixed(2)} pts` : c.fmt === "int" ? `${sign}${Math.round(c.diff)}` : `${sign}${c.diff.toFixed(2)}`;
      if (!NEUTRAL.has(c.key)) cls = (BETTER_LOW.has(c.key) ? -c.diff : c.diff) >= 0 ? "pos" : "neg";
    }
    return `<tr><td>${esc(c.label)}</td><td>${fmtMetric(c.train, c.fmt)}</td><td><b>${fmtMetric(c.test, c.fmt)}</b></td><td class="d ${cls}">${dtext}</td></tr>`;
  }).join("");
  $("#results").innerHTML = `
    <div class="res-head"><div><b>${esc(m.strategy)}</b> <span class="muted">· ${esc(m.symbol)} · ${m.interval} · train vs test</span></div>
      <div class="muted small"><span class="dv-tag train">Train</span> ${esc(r.train.start.slice(0, 10))} → ${esc(r.train.end.slice(0, 10))} · ${r.train.bars.toLocaleString()} bars
        &nbsp; <span class="dv-tag test">Test</span> ${esc(r.test.start.slice(0, 10))} → ${esc(r.test.end.slice(0, 10))} · ${r.test.bars.toLocaleString()} bars</div></div>
    <div class="verdict ${v.level}"><span class="vi">${icon}</span><div><div class="vt">${esc(v.title)}</div><div class="vx">${esc(v.text)}</div></div></div>
    <table class="tt"><thead><tr><th>Metric</th><th class="tr">Train</th><th class="te">Test</th><th>Test − train</th></tr></thead><tbody>${rows}</tbody></table>
    ${insightCards(r.insights)}
    <div class="tt-links">
      <button class="btn" id="ttDeepTrain" title="Full deep-backtest report of the train period">📄 Deep report — train ↗</button>
      <button class="btn" id="ttDeepTest" title="Full deep-backtest report of the test period">📄 Deep report — test ↗</button>
    </div>
    <button class="btn accent wide" id="ttUni" title="Switch developer mode off and test these parameters on many securities">Next: universe test with these parameters →</button>
    <details class="more"><summary>All train metrics</summary>${metricTables(r.train.metrics)}</details>
    <details class="more"><summary>All test metrics</summary>${metricTables(r.test.metrics)}</details>
    <p class="hint">Signals are computed on one continuous run (indicators are already warmed up when the test starts); each period is then traded
      separately from fresh capital, so a position open at the split is closed at the end of train.
      You've looked at the test period <b>${peeks}×</b> for this strategy — if you keep tuning until the test looks good, the test quietly becomes training data.</p>`;
  const deep = async (range, label) => {
    const w = window.open("", "_blank");
    if (w) w.document.write(`<p style="font:14px sans-serif;padding:40px">Running deep backtest (${label})…</p>`);
    try {
      const d = await api.deep({ symbol: S.symbol, interval: S.interval, start: range.start, end: range.end + " 23:59:59",
        strategy: S.strategy, params: S.params[S.strategy] || {}, settings: S.settings });
      if (w) w.location.href = d.url; else window.open(d.url, "_blank");
    } catch (e) { if (w) w.close(); toast(e.message, "error"); }
  };
  $("#ttDeepTrain").onclick = () => deep({ start: S.dev.trainStart, end: S.dev.trainEnd }, "train");
  $("#ttDeepTest").onclick = () => deep({ start: S.dev.testStart, end: S.dev.testEnd }, "test");
  $("#ttUni").onclick = async () => {
    S.start = [S.dev.trainStart, S.dev.testStart].sort()[0];
    S.end = [S.dev.trainEnd, S.dev.testEnd].sort()[1];
    $("#start").value = S.start; $("#end").value = S.end;
    S.dev.on = false; S.devRevealed = false; persist(); applyDevUi(); renderStrategyDetail();
    await reload();
    openUniverse();
  };
}

/* =====================================================================
   Parameter optimizer dialog
   ===================================================================== */
const OBJECTIVES = [["sharpe", "Sharpe ratio"], ["sortino", "Sortino ratio"], ["calmar", "Calmar ratio (CAGR / max DD)"],
  ["total_return", "Total return"], ["cagr", "CAGR"], ["excess", "Excess return vs buy & hold"], ["max_dd", "Smallest max drawdown"],
  ["profit_factor", "Profit factor"], ["win_rate", "Win rate"], ["expectancy_pct", "Average trade return"]];
const optModal = $("#optModal");
optModal.addEventListener("click", (e) => { if (e.target === optModal || e.target.closest("[data-close]")) optModal.classList.add("hidden"); });

const niceStep = (span) => {
  const raw = span / 8, p = Math.pow(10, Math.floor(Math.log10(raw || 1))), f = raw / p;
  return +((f < 1.5 ? 1 : f < 3.5 ? 2 : f < 7.5 ? 5 : 10) * p).toPrecision(6);
};
function suggestRange(p, v) {
  v = Number(v ?? p.default);
  let a = v > 0 ? v * 0.5 : v - 1, b = v > 0 ? v * 2 : v + 1;
  if (p.min !== null && p.min !== undefined) a = Math.max(a, p.min);
  if (p.max !== null && p.max !== undefined) b = Math.min(b, p.max);
  if (p.type === "int") { a = Math.round(a); b = Math.round(b); return { start: a, stop: b, step: Math.max(1, Math.round(niceStep(b - a))) }; }
  const step = niceStep(b - a || 1);
  return { start: +(Math.round(a / step) * step).toFixed(6), stop: +(Math.round(b / step) * step).toFixed(6), step };
}

function optVals(p, mode, value, spec) {
  const num = p.type === "int" || p.type === "float";
  const st = p.step ?? (p.type === "int" ? 1 : "any");
  if (mode === "range") {
    const r = spec && spec.mode === "range" ? spec : suggestRange(p, value);
    return `<label>from<input type="number" step="${st}" data-r="start" value="${r.start}"></label>
      <label>to<input type="number" step="${st}" data-r="stop" value="${r.stop}"></label>
      <label>step<input type="number" step="any" min="0" data-r="step" value="${r.step}"></label>`;
  }
  if (mode === "list") {
    if (p.type === "bool") return `<span class="muted">true and false</span>`;
    if (p.type === "select") {
      const on = new Set((spec && spec.values) || p.options);
      return p.options.map((o) => `<label><input type="checkbox" data-opt="${esc(o)}" ${on.has(o) ? "checked" : ""}>${esc(o)}</label>`).join("");
    }
    const vals = spec && spec.mode === "list" ? spec.values.join(", ") : String(value ?? p.default);
    return `<input class="wide" data-l value="${esc(vals)}" placeholder="comma-separated, e.g. ${num ? "10, 20, 50" : "09:30, 10:00"}">`;
  }
  const v = spec && spec.mode === "fixed" && spec.value !== undefined ? spec.value : (value ?? p.default);
  if (p.type === "bool") return `<label><input type="checkbox" data-f ${v === true || v === "true" ? "checked" : ""}> on</label>`;
  if (p.type === "select") return `<select data-f>${p.options.map((o) => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
  return `<input data-f ${num ? `type="number" step="${st}"` : ""} value="${esc(v)}">`;
}

function optRow(p, value, spec) {
  const num = p.type === "int" || p.type === "float";
  const modes = num ? [["fixed", "Fixed"], ["range", "Range"], ["list", "List"]]
    : p.type === "bool" ? [["fixed", "Fixed"], ["list", "Both"]] : [["fixed", "Fixed"], ["list", "List"]];
  const mode = spec && modes.some(([k]) => k === spec.mode) ? spec.mode : num ? "range" : "fixed";
  return `<tr data-p="${esc(p.name)}"><td class="pn">${esc(p.name)}<small>${esc(p.help || (p.min !== null && p.min !== undefined ? `${p.min} … ${p.max ?? ""}` : p.type))}</small></td>
    <td><select class="om">${modes.map(([k, l]) => `<option value="${k}" ${k === mode ? "selected" : ""}>${l}</option>`).join("")}</select></td>
    <td><div class="vals">${optVals(p, mode, value, spec)}</div></td><td class="n" data-n></td></tr>`;
}

function readGrid(def) {
  const grid = {};
  $$("#optGrid tr[data-p]").forEach((tr) => {
    const p = def.params.find((x) => x.name === tr.dataset.p), mode = $(".om", tr).value;
    let spec, n = 1;
    if (mode === "range") {
      const g = (k) => parseFloat($(`[data-r="${k}"]`, tr).value);
      spec = { mode, start: g("start"), stop: g("stop"), step: g("step") };
      n = spec.step > 0 ? Math.floor(Math.abs(spec.stop - spec.start) / spec.step + 1e-9) + 1 : NaN;
    } else if (mode === "list") {
      if (p.type === "bool") spec = { mode, values: [true, false] };
      else if (p.type === "select") spec = { mode, values: $$("[data-opt]", tr).filter((c) => c.checked).map((c) => c.dataset.opt) };
      else spec = { mode, values: $("[data-l]", tr).value.split(",").map((x) => x.trim()).filter(Boolean) };
      n = spec.values.length;
    } else {
      const el = $("[data-f]", tr);
      spec = { mode, value: el.type === "checkbox" ? el.checked : el.value };
    }
    $("[data-n]", tr).textContent = Number.isFinite(n) ? `×${n}` : "×?";
    grid[p.name] = spec;
  });
  return grid;
}

let optTimer = null;
function openOptimizer() {
  const def = S.strategies.find((x) => x.name === S.strategy);
  if (!def || !S.symbol) return;
  const cur = { ...Object.fromEntries(def.params.map((p) => [p.name, p.default])), ...(S.params[def.name] || {}) };
  const cfg = S.optCfg[def.name] || {};
  const rp = rangeParams();
  $("#optStrat").textContent = "· " + def.name;
  $("#optWhere").innerHTML = `On <b>${esc(S.symbol)}</b> · ${esc(S.interval)} · ${esc(rp.start || "first bar")} → ${esc((rp.end || "last bar").slice(0, 10))}
    ${S.dev.on ? `<span class="dv-tag train">train period only</span>` : ""} — every combination is a full backtest with your current backtest settings (costs, fills, stops).`;
  $("#optGrid").innerHTML = `<thead><tr><th>Parameter</th><th>Test</th><th>Values</th><th></th></tr></thead><tbody>` +
    def.params.map((p) => optRow(p, cur[p.name], cfg.grid && cfg.grid[p.name])).join("") + `</tbody>`;
  if (!def.params.length) $("#optGrid").innerHTML = `<tr><td class="muted">This strategy has no parameters to optimize.</td></tr>`;
  $("#optObj").innerHTML = OBJECTIVES.map(([k, l]) => `<option value="${k}" ${k === (cfg.objective || "sharpe") ? "selected" : ""}>${l}</option>`).join("");
  $("#optMin").value = cfg.min_trades ?? 5;
  $("#optCons").value = cfg.constraint || "";
  const recount = () => { clearTimeout(optTimer); optTimer = setTimeout(() => countCombos(def), 250); };
  $$("#optGrid .om").forEach((sel) => sel.onchange = () => {
    const tr = sel.closest("tr"), p = def.params.find((x) => x.name === tr.dataset.p);
    $(".vals", tr).innerHTML = optVals(p, sel.value, cur[p.name], null);
    recount();
  });
  $("#optGrid").oninput = recount;
  $("#optGrid").onchange = recount;
  $("#optCons").oninput = recount;
  $("#optGo").onclick = () => runOptimizer(def);
  optModal.classList.remove("hidden");
  countCombos(def);
}

async function countCombos(def) {
  const box = $("#optCount");
  const grid = readGrid(def);
  try {
    const r = await api.optimizeCount({ ...rangeParams(), strategy: def.name, grid, constraint: $("#optCons").value || null });
    box.className = "grow " + (r.combos > 3000 ? "warn" : "muted");
    box.innerHTML = `<b>${r.combos.toLocaleString()}</b> combination${r.combos === 1 ? "" : "s"}${r.dropped ? ` (${r.dropped.toLocaleString()} removed by the constraint)` : ""}` +
      (r.combos > 3000 ? " — this can take a few minutes" : "");
    $("#optGo").disabled = r.combos < 1;
  } catch (e) {
    box.className = "grow bad"; box.textContent = e.message.replace(/^\w+Error: /, "");
    $("#optGo").disabled = true;
  }
}

async function runOptimizer(def) {
  const grid = readGrid(def);
  const cfg = { grid, objective: $("#optObj").value, min_trades: +$("#optMin").value || 0, constraint: $("#optCons").value.trim() || null };
  const w = window.open("", "_blank");
  if (w) w.document.write(`<p style="font:14px sans-serif;padding:40px">Starting the optimization…</p>`);
  try {
    const r = await api.optimize({ ...rangeParams(), strategy: def.name, settings: S.settings, ...cfg,
      context: S.dev.on ? { dev: true, train: { start: S.dev.trainStart, end: S.dev.trainEnd } } : {} });
    S.optCfg[def.name] = cfg; persist();
    if (w) w.location.href = r.page; else window.open(r.page, "_blank");
    optModal.classList.add("hidden");
    toast("Optimization running — the report fills in in the new tab. Use <b>↩ Use in terminal</b> there to load the best parameters here.", "ok", true, 9000);
  } catch (e) {
    if (w) w.close();
    toast(e.message, "error", false, 8000);
  }
}

/* =====================================================================
   Universe test dialog
   ===================================================================== */
const uniModal = $("#uniModal");
uniModal.addEventListener("click", (e) => { if (e.target === uniModal || e.target.closest("[data-close]")) uniModal.classList.add("hidden"); });
const secType = (s) => (s.market === "CRYPTO" ? "Crypto" : /INDEX/i.test(s.symbol) ? "Index" : "Stock");
const TYPE_LABEL = { Stock: "Stocks", Index: "Indices", Crypto: "Crypto" };
let uniSel = new Set();

function openUniverse() {
  if (S.dev.on) { toast("Universe testing is off in developer mode — switch dev mode off first.", "error"); return; }
  const def = S.strategies.find((x) => x.name === S.strategy);
  if (!def) return;
  const known = new Set(S.symbols.map((x) => x.name));
  uniSel = new Set((S.uniSel || S.symbols.filter((x) => x.stored.length).map((x) => x.name)).filter((n) => known.has(n)));
  const p = { ...Object.fromEntries(def.params.map((x) => [x.name, x.default])), ...(S.params[def.name] || {}) };
  const rp = normalRange();
  $("#uniStrat").textContent = "· " + def.name;
  $("#uniWhere").innerHTML = `Parameters <b>${esc(Object.entries(p).map(([k, v]) => `${k}=${v}`).join(", ") || "—")}</b> · interval <b>${esc(S.interval)}</b>
    · ${esc(rp.start || "all data")}${rp.end ? " → " + esc(rp.end.slice(0, 10)) : ""} · your current backtest settings. Each market uses its own default costs unless you chose a cost model.`;
  $("#uniSearch").value = "";
  renderUniList();
  uniModal.classList.remove("hidden");
}

function renderUniList() {
  const f = $("#uniSearch").value.toLowerCase();
  const groups = {};
  S.symbols.filter((s) => !f || s.name.toLowerCase().includes(f) || s.symbol.toLowerCase().includes(f))
    .forEach((s) => (groups[secType(s)] = groups[secType(s)] || []).push(s));
  $("#uniList").innerHTML = ["Stock", "Index", "Crypto"].filter((t) => groups[t]).map((t) => `
    <div class="uni-group">${TYPE_LABEL[t]} <span>${groups[t].length}</span><span class="spacer"></span>
      <button class="btn ghost sm" data-ga="${t}">select all</button><button class="btn ghost sm" data-gn="${t}">none</button></div>
    <div class="uni-rows">${groups[t].map((s) => `<label class="uni-row ${s.stored.length ? "" : "nodata"}" title="${esc(s.symbol)} · ${esc(s.source)}">
      <input type="checkbox" data-u="${esc(s.name)}" ${uniSel.has(s.name) ? "checked" : ""}>
      <span class="dot ${s.stored.length ? "ok" : ""}"></span><span class="nm">${esc(s.name)}</span>
      <span class="iv">${s.stored.length ? esc(s.stored.join(" ")) : "no data"}</span></label>`).join("")}</div>`).join("") || `<div class="placeholder">No match</div>`;
  $$("#uniList [data-u]").forEach((c) => c.onchange = () => { c.checked ? uniSel.add(c.dataset.u) : uniSel.delete(c.dataset.u); uniCount(); });
  const inGroup = (t) => S.symbols.filter((s) => secType(s) === t && (!f || s.name.toLowerCase().includes(f) || s.symbol.toLowerCase().includes(f)));
  $$("#uniList [data-ga]").forEach((b) => b.onclick = () => { inGroup(b.dataset.ga).forEach((s) => uniSel.add(s.name)); renderUniList(); });
  $$("#uniList [data-gn]").forEach((b) => b.onclick = () => { inGroup(b.dataset.gn).forEach((s) => uniSel.delete(s.name)); renderUniList(); });
  uniCount();
}
function uniCount() {
  const noData = [...uniSel].filter((n) => !(S.symbols.find((s) => s.name === n) || { stored: [] }).stored.length).length;
  $("#uniCount").innerHTML = `<b>${uniSel.size}</b> selected` + (noData ? ` · <span class="neg">${noData} without data</span> (they'll be listed as not tested)` : "");
  $("#uniGo").disabled = uniSel.size < 1;
}
$("#uniSearch").oninput = renderUniList;
$$("#uniQuick button").forEach((b) => b.onclick = () => {
  const q = b.dataset.q;
  uniSel = new Set(q === "all" ? S.symbols.map((s) => s.name) : q === "data" ? S.symbols.filter((s) => s.stored.length).map((s) => s.name) : []);
  renderUniList();
});
$("#uniGo").onclick = async () => {
  const def = S.strategies.find((x) => x.name === S.strategy);
  const symbols = S.symbols.map((s) => s.name).filter((n) => uniSel.has(n));
  const rp = normalRange();
  const w = window.open("", "_blank");
  if (w) w.document.write(`<p style="font:14px sans-serif;padding:40px">Starting the universe test…</p>`);
  try {
    const r = await api.universe({ symbols, interval: S.interval, start: rp.start, end: rp.end, strategy: def.name,
      params: S.params[def.name] || {}, settings: S.settings });
    S.uniSel = symbols; persist();
    if (w) w.location.href = r.page; else window.open(r.page, "_blank");
    uniModal.classList.add("hidden");
    toast(`Universe test running on ${symbols.length} securities — the report fills in in the new tab.`, "ok", false, 7000);
  } catch (e) {
    if (w) w.close();
    toast(e.message, "error", false, 8000);
  }
};

/* =====================================================================
   Parameters sent from an optimizer report ("↩ Use in terminal")
   ===================================================================== */
function useParams(raw) {
  let d;
  try { d = JSON.parse(raw); } catch (e) { return; }
  if (!d || !d.strategy || !S.strategies.find((x) => x.name === d.strategy)) return;
  S.strategy = d.strategy;
  S.params[d.strategy] = { ...(S.params[d.strategy] || {}), ...d.params };
  persist();
  renderStrategyList($("#stratSearch").value);
  renderStrategyDetail();
  showTab("strategy");
  toast(`Loaded from the optimizer: <b>${esc(Object.entries(d.params).map(([k, v]) => `${k}=${v}`).join(", "))}</b>` +
    (S.dev.on ? " — press <b>Train vs test</b> to validate." : ""), "ok", true, 9000);
  if (d.symbol && (d.symbol !== S.symbol || d.interval !== S.interval))
    toast(`Note: these were optimized on ${esc(d.symbol)} ${esc(d.interval)}; the chart shows ${esc(S.symbol)} ${esc(S.interval)}.`, "info", false, 9000);
}
window.addEventListener("storage", (e) => { if (e.key === "h1-use-params" && e.newValue) useParams(e.newValue); });

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
  applyDevUi();
  renderIntervals();
  $("#start").value = S.start; $("#end").value = S.end;
  try {
    const [, , ind, def] = await Promise.all([refreshSymbols(), loadStrategies(), api.indicators(), api.defaults()]);
    S.indicatorDefs = ind.indicators; S.defaults = def; S.costs = def.costs;
    renderIndicatorList(); renderActiveIndicators(); renderStrategyDetail();
    try {                              // "Use in terminal" clicked while this tab was closed
      const raw = localStorage.getItem("h1-use-params");
      if (raw && Date.now() - (JSON.parse(raw).ts || 0) < 15 * 60e3) useParams(raw);
      localStorage.removeItem("h1-use-params");
    } catch (e) { /* ignore */ }
    await reload();
  } catch (e) {
    toast("Backend not reachable: " + e.message, "error", false, 15000);
  }
}
boot();
