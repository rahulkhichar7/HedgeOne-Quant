/* =====================================================================
   Universe test report:  /universe.html?id=<id>   (or ?job=<job> while it runs)
   One strategy + one parameter set on many securities.
   - tick securities on/off: every comparison chart, the table highlight and the
     equal-weight portfolio follow the selection
   - individual analysis for any security
   ===================================================================== */
import { api } from "./api.js";
import { fmtNum } from "./chart.js";
import { heatColor, hbars, labelScatter, lines } from "./svg.js";
import { $, $$, esc, fmtMetric, highlightPy, insightCards, kpiCards, metricTables, tradeRows, TRADE_HEAD } from "./ui.js";
import { STANDALONE, TimeChart, bindToolbar, colorFor, costsNote, daySec, loadReport, paramChips, section, showError, sortableTable } from "./research.js";

const host = $("#report");
let U = null, OK = [], theme = "light", table = null;
const SEL = new Set();
const COLOR = new Map();
const charts = { eq: null, dd: null, ind: null, indDd: null };
const view = { showBh: false, showPf: true, metric: "total_return", ind: null };

const METRICS = [
  ["total_return", "Total return", "pct"], ["buy_hold", "Buy & hold", "pct"], ["excess", "Excess vs buy & hold", "pct"], ["cagr", "CAGR", "pct"],
  ["sharpe", "Sharpe", "ratio"], ["sortino", "Sortino", "ratio"], ["calmar", "Calmar", "ratio"], ["max_dd", "Max drawdown", "pct"],
  ["volatility", "Volatility", "pct"], ["win_rate", "Win rate", "pct"], ["profit_factor", "Profit factor", "ratio"],
  ["trades", "Trades", "int"], ["expectancy_pct", "Avg trade", "pct"], ["exposure", "Time in market", "pct"],
];
const mfmt = (k) => (METRICS.find((m) => m[0] === k) || [k, k, "ratio"])[2];
const mlabel = (k) => (METRICS.find((m) => m[0] === k) || [k, k])[1];
const kp = (r, k) => (r.kp ? r.kp[k] : null);
const sel = () => OK.filter((r) => SEL.has(r.symbol));
const pctCls = (v) => (Number.isFinite(v) ? (v > 0 ? "pos" : v < 0 ? "neg" : "") : "");

/* =====================================================================
   Equal-weight portfolio + correlations from the daily equity of each security
   ===================================================================== */
function dailyReturns(r, key = "eq") {
  const out = new Map();
  const d = r.daily.d, v = r.daily[key];
  let last = null;
  for (let i = 0; i < d.length; i++) {
    const x = v[i];
    if (x === null || !Number.isFinite(x)) continue;
    if (last !== null && last > 0) out.set(d[i], x / last - 1);
    last = x;
  }
  return out;
}

function portfolio(list, key = "eq") {
  if (!list.length) return null;
  const rets = list.map((r) => dailyReturns(r, key));
  const starts = list.map((r) => r.daily.d[0]);
  const dates = [...new Set(list.flatMap((r) => r.daily.d))].sort();
  const t = [], v = [], daily = [];
  let e = 1;
  for (const d of dates) {
    let s = 0, n = 0;
    rets.forEach((m, j) => { if (d >= starts[j] && m.has(d)) { s += m.get(d); n++; } });
    const r = n ? s / n : 0;
    e *= 1 + r;
    t.push(daySec(d)); v.push((e - 1) * 100); daily.push(r);
  }
  const years = Math.max((t[t.length - 1] - t[0]) / (365.25 * 86400), 1 / 365);
  let peak = 1, mdd = 0, eq = 1;
  daily.forEach((r) => { eq *= 1 + r; peak = Math.max(peak, eq); mdd = Math.min(mdd, eq / peak - 1); });
  const rr = daily.slice(1), mean = rr.reduce((a, b) => a + b, 0) / (rr.length || 1);
  const sd = Math.sqrt(rr.reduce((a, b) => a + (b - mean) ** 2, 0) / Math.max(rr.length - 1, 1));
  const per = rr.length / years;
  return { t, v, total: v[v.length - 1], cagr: (Math.pow(e, 1 / years) - 1) * 100, mdd: mdd * 100,
    sharpe: sd > 0 ? (mean / sd) * Math.sqrt(per) : null, days: dates.length };
}

function corr(a, b) {
  const xs = [], ys = [];
  for (const [d, x] of a) if (b.has(d)) { xs.push(x); ys.push(b.get(d)); }
  if (xs.length < 10) return null;
  const mx = xs.reduce((p, c) => p + c, 0) / xs.length, my = ys.reduce((p, c) => p + c, 0) / ys.length;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < xs.length; i++) { const dx = xs[i] - mx, dy = ys[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
  return sxx > 0 && syy > 0 ? sxy / Math.sqrt(sxx * syy) : null;
}

/* =====================================================================
   Page
   ===================================================================== */
function render() {
  const m = U.meta, S = U.summary || {};
  document.title = `${m.strategy} · universe test (${OK.length})`;
  const types = [...new Set(OK.map((r) => r.type))];
  const range = `${esc((m.start || OK[0]?.start || "").slice(0, 10))} → ${esc((m.end || OK[0]?.end || "").slice(0, 10))}`;
  host.innerHTML = `
    <header class="hero">
      <div class="hero-l">
        <div class="eyebrow">${esc(m.category)} · universe test</div>
        <h1>${esc(m.strategy)}</h1>
        <div class="sub">${m.symbols.length} securities · ${esc(m.interval)} · ${range}${m.failed ? ` · <span class="neg">${m.failed} failed</span>` : ""} · ${(m.elapsed_ms / 1000).toFixed(1)}s</div>
        <div class="chips">${paramChips(m.params)}</div>
      </div>
      <div class="hero-r">
        <div class="muted small">Profitable on</div>
        <div class="big ${S.profitable >= (S.n || 0) / 2 ? "pos" : "neg"}">${S.profitable ?? 0} / ${S.n ?? 0}</div>
        <div class="muted">median return ${fmtMetric(S.median_return, "pct")} · beats B&H on ${S.beat_bh ?? 0}</div>
        <div class="muted small">Report ${esc(U.id)} · ${esc(m.created.replace("T", " "))}</div>
      </div>
    </header>

    <div class="card stickysel no-print screen-only" id="selbar"></div>

    ${section(`Securities <span class="muted small">tick to include in the comparison charts, the table highlight and the combined portfolio</span>`,
      `<div class="symgrid" id="symgrid"></div>`, "", "selcard")}

    <div id="pfk"></div>
    ${section("Highlights", insightCards(U.insights) || `<p class="muted">No notes.</p>`)}

    ${section(`Comparison <span class="muted small">click a name for its own analysis · click a header to sort</span>`,
      `<div class="tablewrap"><table class="tbl" id="cmp"></table></div>`)}

    ${section("Equity curves — % return", `
      <div class="ctrl screen-only">
        <label><input type="checkbox" id="tgPf" ${view.showPf ? "checked" : ""}> equal-weight portfolio of the selection</label>
        <label><input type="checkbox" id="tgBh" ${view.showBh ? "checked" : ""}> buy & hold (dashed)</label>
        <button class="btn sm" id="fitEq">Fit</button>
      </div>
      <div id="eqChart" class="tchart"></div>
      <div id="ddChart" class="tchart short" style="margin-top:8px"></div>
      <p class="note">Portfolio = equal capital in every selected security, rebalanced daily (from daily closes); its buy & hold line uses the same weights.</p>`)}

    <div class="chartgrid">
      ${section("Compare a metric", `<div class="ctrl"><label>Metric <select id="mSel">${METRICS.map(([k, l]) => `<option value="${k}" ${k === view.metric ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></label></div><div id="mBars"></div>`)}
      ${section("Risk vs return", `<div id="rr"></div><p class="note">Up and to the right is better: more return for a shallower drawdown.</p>`)}
    </div>

    ${section("Yearly returns <span class=\"muted small\">strategy, % per calendar year</span>", `<div class="tablewrap"><table class="tbl mtx" id="yr"></table></div>`)}
    ${section("Correlation of daily strategy returns", `<div class="tablewrap"><table class="tbl mtx" id="corr"></table></div>
      <p class="note">Green = moves independently or opposite (good for diversification), red = moves together. Low or negative correlation between securities means combining them smooths the portfolio. Pairs with fewer than 10 common days are blank.</p>`)}

    ${section("Individual analysis", `<div class="indhead">
        <button class="btn sm" id="indPrev">◀</button>
        <select id="indSel">${OK.map((r) => `<option value="${esc(r.symbol)}">${esc(r.symbol)}</option>`).join("")}</select>
        <button class="btn sm" id="indNext">▶</button>
        <span class="spacer"></span>
        <button class="btn accent live-only" id="indDeep" title="Full deep-backtest report for this security">Deep report ↗</button>
      </div><div id="indBody"></div>`, "break", "indcard")}

    ${U.results.some((r) => !r.ok) ? section("Not tested", `<ul class="errlist">${U.results.filter((r) => !r.ok).map((r) => `<li><b>${esc(r.symbol)}</b> — ${esc(r.error)}</li>`).join("")}</ul>`) : ""}

    ${section("Settings", `<p class="note" style="margin:0">${costsNote(m.settings, null)}. Costs follow each security's market default unless a cost model was chosen:
      ${[...new Set(OK.map((r) => r.costs.preset))].map(esc).join(", ")}. Ratios annualised on each security's own trading calendar.</p>`)}
    ${section("Strategy source", `<pre class="code"><code>${highlightPy(m.source || "")}</code></pre>`, "break")}
    <div id="printInd" class="print-only"></div>
  `;
  void types;
  drawSelector();
  $("#tgPf").onchange = (e) => { view.showPf = e.target.checked; refreshEquityVisibility(); };
  $("#tgBh").onchange = (e) => { view.showBh = e.target.checked; refreshEquityVisibility(); };
  $("#fitEq").onclick = () => { charts.eq.fit(); charts.dd.fit(); };
  $("#mSel").onchange = (e) => { view.metric = e.target.value; drawCompare(); };
  $("#indSel").onchange = (e) => showInd(e.target.value);
  $("#indPrev").onclick = () => stepInd(-1);
  $("#indNext").onclick = () => stepInd(1);
  $("#indDeep").onclick = openDeep;
  drawTable();
  drawCharts();
  update();
  showInd(view.ind || OK[0]?.symbol);
}

/* ---------------- selection */
function drawSelector() {
  const types = [...new Set(OK.map((r) => r.type))];
  const btn = (id, label, title = "") => `<button class="btn sm" data-q="${id}" title="${esc(title)}">${label}</button>`;
  $("#selbar").innerHTML = `<div class="selbar">
    ${btn("all", "All")}${btn("none", "None")}${btn("invert", "Invert")}
    ${types.length > 1 ? types.map((t) => btn("type:" + t, t === "Index" ? "Indices" : t === "Crypto" ? "Crypto" : t + "s", `Only ${t.toLowerCase()} securities`)).join("") : ""}
    ${btn("prof", "Profitable")}${btn("beat", "Beat B&H")}${btn("top5", "Top 5 Sharpe")}${btn("bot5", "Bottom 5")}
    <span class="count" id="selCount"></span><a href="#selcard" class="small">edit ↓</a></div>`;
  $$("#selbar [data-q]").forEach((b) => b.onclick = () => quick(b.dataset.q));
  $("#symgrid").innerHTML = U.results.map((r) => {
    if (!r.ok) return `<label class="symchk fail" title="${esc(r.error)}"><input type="checkbox" disabled><span class="nm">${esc(r.symbol)}</span><span class="rv muted">n/a</span></label>`;
    const v = kp(r, "total_return");
    return `<label class="symchk" data-sym="${esc(r.symbol)}"><input type="checkbox" data-sym="${esc(r.symbol)}">
      <span class="sw2" style="background:${COLOR.get(r.symbol)}"></span><span class="nm" title="${esc(r.symbol)}">${esc(r.symbol)}</span>
      <span class="typ">${esc(r.type)}</span><span class="rv ${pctCls(v)}">${fmtMetric(v, "pct")}</span></label>`;
  }).join("");
  $$("#symgrid input[data-sym]").forEach((c) => c.onchange = () => { c.checked ? SEL.add(c.dataset.sym) : SEL.delete(c.dataset.sym); update(); });
}

function quick(q) {
  const all = OK.map((r) => r.symbol);
  const by = (k, dir = -1) => OK.slice().sort((a, b) => ((kp(b, k) ?? -1e18) - (kp(a, k) ?? -1e18)) * -dir).map((r) => r.symbol);
  let pick;
  if (q === "all") pick = all;
  else if (q === "none") pick = [];
  else if (q === "invert") pick = all.filter((s) => !SEL.has(s));
  else if (q.startsWith("type:")) pick = OK.filter((r) => r.type === q.slice(5)).map((r) => r.symbol);
  else if (q === "prof") pick = OK.filter((r) => (kp(r, "total_return") ?? 0) > 0).map((r) => r.symbol);
  else if (q === "beat") pick = OK.filter((r) => (kp(r, "excess") ?? 0) > 0).map((r) => r.symbol);
  else if (q === "top5") pick = by("sharpe", -1).slice(0, 5);
  else if (q === "bot5") pick = by("sharpe", 1).slice(0, 5);
  SEL.clear(); pick.forEach((s) => SEL.add(s));
  update();
}

function update() {
  $$("#symgrid input[data-sym]").forEach((c) => { c.checked = SEL.has(c.dataset.sym); c.closest(".symchk").classList.toggle("on", c.checked); });
  $("#selCount").textContent = `${SEL.size} of ${OK.length} selected`;
  drawPortfolioKpis();
  if (table) table.redraw();
  refreshEquityVisibility();
  drawCompare();
  drawYearly();
  drawCorr();
}

/* ---------------- portfolio KPIs */
function drawPortfolioKpis() {
  const L = sel();
  const pf = portfolio(L), bh = portfolio(L, "px");
  const avg = (k) => { const v = L.map((r) => kp(r, k)).filter(Number.isFinite); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; };
  const prof = L.filter((r) => (kp(r, "total_return") ?? 0) > 0).length;
  const tr = L.reduce((a, r) => a + (kp(r, "trades") || 0), 0);
  const k = (lab, v, fmt, cls = "") => `<div class="kpi"><div class="kpi-l">${lab}</div><div class="kpi-v ${cls}">${fmtMetric(v, fmt)}</div></div>`;
  $("#pfk").innerHTML = !L.length ? `<div class="card"><p class="muted" style="margin:0">Select at least one security to see the combined results.</p></div>` :
    `<div class="eyebrow" style="margin:0 0 6px">Equal-weight portfolio of the ${L.length} selected</div><div class="kpis">
      ${k("Return", pf.total, "pct", pctCls(pf.total))}${k("CAGR", pf.cagr, "pct", pctCls(pf.cagr))}${k("Max DD", pf.mdd, "pct", "neg")}
      ${k("Sharpe", pf.sharpe, "ratio")}${k("Buy & hold", bh.total, "pct", pctCls(bh.total))}
      ${k("Avg security", avg("total_return"), "pct", pctCls(avg("total_return")))}
      <div class="kpi"><div class="kpi-l">Profitable</div><div class="kpi-v">${prof} / ${L.length}</div></div>${k("Trades", tr, "int")}</div>`;
}

/* ---------------- comparison table */
function drawTable() {
  const SHORT = { total_return: "Return", buy_hold: "Buy & hold", excess: "Excess", cagr: "CAGR", max_dd: "Max DD", win_rate: "Win %",
    profit_factor: "PF", expectancy_pct: "Avg trade", exposure: "In market" };
  const n = (k, f = mfmt(k)) => ({ key: k, label: esc(SHORT[k] || mlabel(k)), title: mlabel(k), cls: "num", sort: (r) => kp(r, k),
    fmt: (r) => `<span class="${["total_return", "excess", "cagr", "expectancy_pct", "buy_hold"].includes(k) ? pctCls(kp(r, k)) : ""}">${fmtMetric(kp(r, k), f)}</span>` });
  const cols = [
    { key: "chk", label: "", nosort: true, fmt: (r) => `<input type="checkbox" data-row="${esc(r.symbol)}" ${SEL.has(r.symbol) ? "checked" : ""}>` },
    { key: "symbol", label: "Security", sort: (r) => r.symbol, fmt: (r) => `<span class="namecell"><span class="sw2" style="width:10px;height:10px;border-radius:3px;background:${COLOR.get(r.symbol)}"></span><a class="symlink" data-ind="${esc(r.symbol)}">${esc(r.symbol)}</a><span class="typ">${esc(r.type)}</span></span>` },
    n("total_return"), n("buy_hold"), n("excess"), n("cagr"), n("max_dd"), n("sharpe"), n("sortino"),
    n("win_rate"), n("profit_factor"), n("trades"), n("expectancy_pct"), n("exposure"),
    { key: "bars", label: "Bars", cls: "num", fmt: (r) => r.bars.toLocaleString() },
  ];
  table = sortableTable($("#cmp"), OK, cols, {
    initial: { key: "total_return", dir: -1 },
    rowAttrs: (r) => `class="${SEL.has(r.symbol) ? "" : "dim"}"`,
    onRender: (el) => {
      $$("[data-row]", el).forEach((c) => c.onchange = () => { c.checked ? SEL.add(c.dataset.row) : SEL.delete(c.dataset.row); update(); });
      $$("[data-ind]", el).forEach((a) => a.onclick = () => { showInd(a.dataset.ind); $("#indcard").scrollIntoView({ behavior: "smooth" }); });
    },
  });
}

/* ---------------- equity + drawdown (interactive) */
function drawCharts() {
  ["eq", "dd"].forEach((k) => { if (charts[k]) charts[k].remove(); });
  charts.eq = new TimeChart($("#eqChart"), { theme });
  charts.dd = new TimeChart($("#ddChart"), { theme });
  const list = [];
  OK.forEach((r) => {
    list.push({ id: "s:" + r.symbol, name: r.symbol, color: COLOR.get(r.symbol), t: r.curve.t, v: r.curve.eq, width: 1.5 });
    list.push({ id: "b:" + r.symbol, name: r.symbol + " B&H", color: COLOR.get(r.symbol), t: r.curve.t, v: r.curve.bh, dashed: true, width: 1, visible: false, legend: false });
  });
  charts.eq.set(list);
  charts.dd.set(OK.map((r) => ({ id: "d:" + r.symbol, name: r.symbol, color: COLOR.get(r.symbol), t: r.curve.t, v: r.curve.dd, width: 1.2 })));
  refreshEquityVisibility(true);
}

function refreshEquityVisibility(fit = false) {
  if (!charts.eq) return;
  OK.forEach((r) => {
    const on = SEL.has(r.symbol);
    charts.eq.visible("s:" + r.symbol, on);
    charts.eq.visible("b:" + r.symbol, on && view.showBh);
    charts.dd.visible("d:" + r.symbol, on);
  });
  const L = sel();
  const pf = view.showPf && L.length > 1 ? portfolio(L) : null;
  const pb = pf && view.showBh ? portfolio(L, "px") : null;
  charts.eq.replace({ id: "pf", name: `Portfolio (${L.length})`, color: theme === "dark" ? "#ffffff" : "#0b0d12", width: 3, t: pf ? pf.t : [], v: pf ? pf.v : [], visible: !!pf });
  charts.eq.replace({ id: "pfb", name: "Portfolio B&H", color: theme === "dark" ? "#ffffff" : "#0b0d12", width: 1.5, dashed: true, t: pb ? pb.t : [], v: pb ? pb.v : [], visible: !!pb });
  if (fit) { charts.eq.fit(); charts.dd.fit(); }
}

/* ---------------- svg comparisons */
function drawCompare() {
  const L = sel(), k = view.metric, f = mfmt(k);
  const rows = L.map((r) => ({ label: r.symbol, values: k === "total_return" ? [kp(r, k), kp(r, "buy_hold")] : [kp(r, k)],
    color: ["sharpe", "sortino", "calmar", "win_rate", "profit_factor", "trades", "exposure", "volatility"].includes(k) ? COLOR.get(r.symbol) : null }))
    .sort((a, b) => (b.values[0] ?? -1e18) - (a.values[0] ?? -1e18));
  const fmt = (v) => f === "pct" ? v.toFixed(1) + "%" : f === "int" ? String(Math.round(v)) : v.toFixed(2);
  hbars($("#mBars"), rows, { names: k === "total_return" ? ["Strategy", "Buy & hold"] : [], fmt, center: k === "profit_factor" ? 1 : k === "win_rate" ? 50 : 0 });
  if (!rows.length) $("#mBars").innerHTML = `<p class="muted">Nothing selected.</p>`;
  labelScatter($("#rr"), L.map((r) => ({ x: kp(r, "max_dd"), y: kp(r, "total_return"), label: r.symbol, color: COLOR.get(r.symbol) })),
    { xLabel: "Max drawdown %", yLabel: "Total return %", xFmt: (v) => v.toFixed(0), yFmt: (v) => v.toFixed(0) });
  if (!L.length) $("#rr").innerHTML = "";
}

function drawYearly() {
  const L = sel();
  const years = [...new Set(L.flatMap((r) => r.yearly.map((y) => y.year)))].sort();
  const all = L.flatMap((r) => r.yearly.map((y) => y.strategy)).filter(Number.isFinite);
  const mx = Math.max(1, ...all.map(Math.abs));
  const pfY = (() => {           // portfolio yearly from the combined curve
    const p = portfolio(L);
    if (!p) return {};
    const out = {}; let prevE = 1;
    const byYear = {};
    p.t.forEach((t, i) => { byYear[new Date(t * 1000).getUTCFullYear()] = 1 + p.v[i] / 100; });
    Object.keys(byYear).sort().forEach((y) => { out[y] = (byYear[y] / prevE - 1) * 100; prevE = byYear[y]; });
    return out;
  })();
  $("#yr").innerHTML = !L.length ? "" : `<thead><tr><th>Security</th>${years.map((y) => `<th>${y}</th>`).join("")}<th>Total</th></tr></thead><tbody>` +
    L.map((r) => {
      const m = Object.fromEntries(r.yearly.map((y) => [y.year, y.strategy]));
      return `<tr><td><span class="namecell"><span class="sw2" style="width:9px;height:9px;border-radius:2px;background:${COLOR.get(r.symbol)}"></span>${esc(r.symbol)}</span></td>` +
        years.map((y) => `<td style="background:${heatColor(m[y] ?? null, mx)}">${m[y] === undefined || m[y] === null ? "" : m[y].toFixed(1)}</td>`).join("") +
        `<td class="${pctCls(kp(r, "total_return"))}"><b>${fmtMetric(kp(r, "total_return"), "pct")}</b></td></tr>`;
    }).join("") +
    (L.length > 1 ? `<tr><td><b>Portfolio</b></td>${years.map((y) => `<td style="background:${heatColor(pfY[y] ?? null, mx)}"><b>${pfY[y] === undefined ? "" : pfY[y].toFixed(1)}</b></td>`).join("")}<td></td></tr>` : "") + `</tbody>`;
}

function drawCorr() {
  const L = sel().slice(0, 30);
  const R = L.map((r) => dailyReturns(r));
  $("#corr").innerHTML = L.length < 2 ? `<tbody><tr><td class="muted">Select two or more securities.</td></tr></tbody>` :
    `<thead><tr><th></th>${L.map((r) => `<th title="${esc(r.symbol)}">${esc(r.symbol.length > 10 ? r.symbol.slice(0, 9) + "…" : r.symbol)}</th>`).join("")}</tr></thead><tbody>` +
    L.map((r, i) => `<tr><td>${esc(r.symbol)}</td>${L.map((_, j) => {
      const c = i === j ? 1 : corr(R[i], R[j]);
      return `<td style="background:${i === j ? "var(--bg)" : heatColor(c === null ? null : -c * 100, 100)}">${c === null ? "" : c.toFixed(2)}</td>`;
    }).join("")}</tr>`).join("") + `</tbody>` + (sel().length > 30 ? `<caption class="muted small">first 30 selected</caption>` : "");
}

/* ---------------- individual analysis */
function stepInd(d) {
  const i = OK.findIndex((r) => r.symbol === view.ind);
  showInd(OK[(i + d + OK.length) % OK.length].symbol);
}

function monthlyTable(mt) {
  const all = mt.rows.flatMap((r) => r.months.filter((v) => v !== null));
  const mx = Math.max(1, ...all.map(Math.abs));
  return `<table class="tbl heat"><thead><tr><th>Year</th>${mt.months.map((x) => `<th>${x}</th>`).join("")}<th>Year</th></tr></thead><tbody>` +
    mt.rows.map((r) => `<tr><td><b>${r.year}</b></td>${r.months.map((v) => `<td style="background:${heatColor(v, mx)}">${v === null ? "" : v.toFixed(1)}</td>`).join("")}
      <td class="${r.total >= 0 ? "pos" : "neg"}"><b>${r.total.toFixed(1)}%</b></td></tr>`).join("") + `</tbody></table>`;
}

function indHtml(r, printMode = false) {
  return `
    <div class="sub" style="margin-bottom:8px">${esc(r.type)} · ${esc(r.market)} · ${esc(r.start.slice(0, 16))} → ${esc(r.end.slice(0, 16))} · ${r.bars.toLocaleString()} bars · ${esc(r.costs.preset)}</div>
    ${kpiCards(r.metrics)}
    ${printMode ? `<div class="chartgrid"><div><h3>Return % vs buy & hold</h3><div class="svgeq"></div></div><div><h3>Drawdown %</h3><div class="svgdd"></div></div></div>` : `<div class="tchart" id="indEq"></div><div class="tchart short" id="indDd" style="margin-top:8px"></div>`}
    <div style="margin-top:14px">${metricTables(r.metrics)}</div>
    <div class="two" style="margin-top:14px">
      <div><h3>Monthly returns</h3>${monthlyTable(r.monthly)}</div>
      <div><h3>Worst drawdowns</h3><table class="tbl"><thead><tr><th>Start</th><th>Bottom</th><th>Recovered</th><th>Depth</th><th>Length</th></tr></thead><tbody>
        ${(r.drawdowns || []).map((d) => `<tr><td>${esc(d.start.slice(0, 10))}</td><td>${esc(d.valley.slice(0, 10))}</td><td>${esc(d.recovered ? d.end.slice(0, 10) : d.end)}</td>
        <td class="neg">${d.depth_pct.toFixed(2)}%</td><td>${esc(d.duration)}</td></tr>`).join("") || `<tr><td colspan="5">No drawdowns.</td></tr>`}</tbody></table></div>
    </div>
    ${printMode ? "" : `<h3 style="margin-top:14px">Trades <span class="muted small">${r.trade_count > r.trades.length ? `last ${r.trades.length} of ${r.trade_count}` : r.trade_count}</span></h3>
      <div class="tradewrap"><table class="tbl trades">${TRADE_HEAD}<tbody>${tradeRows(r.trades)}</tbody></table></div>`}`;
}

function showInd(symbol) {
  const r = OK.find((x) => x.symbol === symbol);
  if (!r) { $("#indBody").innerHTML = `<p class="muted">No security could be tested.</p>`; return; }
  view.ind = symbol;
  $("#indSel").value = symbol;
  $("#indBody").innerHTML = indHtml(r);
  drawIndCharts();
}

function drawIndCharts() {
  const r = OK.find((x) => x.symbol === view.ind);
  if (!r) return;
  ["ind", "indDd"].forEach((k) => { if (charts[k]) { charts[k].remove(); charts[k] = null; } });
  charts.ind = new TimeChart($("#indEq"), { theme });
  charts.ind.set([
    { id: "eq", name: "Strategy", color: COLOR.get(r.symbol), width: 2, t: r.curve.t, v: r.curve.eq },
    { id: "bh", name: "Buy & hold", color: "#9598a1", dashed: true, t: r.curve.t, v: r.curve.bh },
  ]);
  charts.indDd = new TimeChart($("#indDd"), { theme });
  charts.indDd.set([{ id: "dd", name: "Drawdown", color: "#f23645", area: true, t: r.curve.t, v: r.curve.dd }]);
}

async function openDeep() {
  const m = U.meta, symbol = view.ind;
  const w = window.open("", "_blank");
  if (w) w.document.write(`<p style="font:14px sans-serif;padding:40px">Running deep backtest for ${esc(symbol)}…</p>`);
  try {
    const d = await api.deep({ symbol, interval: m.interval, start: m.start, end: m.end, strategy: m.strategy, params: m.params, settings: m.settings });
    if (w) w.location.href = d.url; else location.href = d.url;
  } catch (e) {
    if (w) w.document.body.innerHTML = `<p style="font:14px sans-serif;padding:40px;color:#c00">${esc(e.message)}</p>`;
  }
}

/* ---------------- print: a page for every selected security (static SVG charts) */
function preparePrint() {
  const box = $("#printInd");
  box.innerHTML = "";
  document.body.classList.toggle("print-ind", $("#pdfInd").checked);
  if (!$("#pdfInd").checked) return;
  box.innerHTML = sel().map((r, i) => `<section class="card ind-print" data-i="${i}"><h2>${esc(r.symbol)}</h2>${indHtml(r, true)}</section>`).join("");
  sel().forEach((r, i) => {
    const sec = box.querySelector(`[data-i="${i}"]`);
    lines(sec.querySelector(".svgeq"), [{ name: "Strategy %", values: r.curve.eq, color: "#2962ff", width: 2 },
      { name: "Buy & hold %", values: r.curve.bh, color: "#9598a1", dashed: true, width: 1.2 }], { zero: true });
    lines(sec.querySelector(".svgdd"), [{ name: "Drawdown %", values: r.curve.dd, color: "#f23645", width: 1.4 }], { zero: true });
  });
}

/* =====================================================================
   Boot
   ===================================================================== */
(async () => {
  const getTheme = bindToolbar({
    kind: "universe", themeKey: "h1-report-theme", getId: () => U && U.id,
    redraw: (t) => { theme = t; if (U) { drawCharts(); drawIndCharts(); } },
    beforePrint: preparePrint, afterPrint: () => { $("#printInd").innerHTML = ""; document.body.classList.remove("print-ind"); },
  });
  theme = getTheme();
  try {
    U = await loadReport("universe", host);
    OK = U.results.filter((r) => r.ok);
    OK.forEach((r, i) => COLOR.set(r.symbol, colorFor(i)));
    OK.forEach((r) => SEL.add(r.symbol));
    render();
  } catch (e) { console.error(e); showError(host, e.message); }
})();
