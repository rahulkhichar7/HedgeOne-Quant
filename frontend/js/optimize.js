/* =====================================================================
   Parameter optimization report:  /optimize.html?id=<id>   (or ?job=<job> while it runs)
   ===================================================================== */
import { fmtNum } from "./chart.js";
import { catLines, heatGrid, histogram, labelScatter } from "./svg.js";
import { $, $$, esc, fmtMetric, highlightPy, insightCards, kpiCards, metricTables } from "./ui.js";
import { STANDALONE, TimeChart, bindToolbar, copyText, costsNote, flash, loadReport, paramChips, section, sendToTerminal, showError, sortableTable } from "./research.js";

const host = $("#report");
let P = null, theme = "light";
const charts = [];
const st = { hx: null, hy: null, metric: null, agg: "best", limit: 100, eligibleOnly: true };

const CENTER = { win_rate: 50, profit_factor: 1, max_dd: -1e9, trades: -1e9, exposure: -1e9 };
const fmtOf = (key) => (P.metric_defs.find((d) => d.key === key) || { fmt: "ratio" }).fmt;
const labelOf = (key) => (P.metric_defs.find((d) => d.key === key) || { label: key }).label;
const short = (v, fmt) => v === null || v === undefined || !Number.isFinite(v) ? "—" : fmt === "pct" ? v.toFixed(1) + "%" : fmt === "int" ? String(Math.round(v)) : v.toFixed(2);
const pkey = (v) => typeof v === "number" ? +v.toFixed(10) : String(v);

function render() {
  const m = P.meta, best = P.rows[0], obj = m.objective;
  document.title = `${m.strategy} · optimization · ${m.symbol}`;
  const fixed = Object.fromEntries(Object.entries(m.values).filter(([k, v]) => v.length === 1).map(([k, v]) => [k, v[0]]));
  const prof = P.rows.filter((r) => (r.total_return ?? 0) > 0).length;
  const scores = P.rows.map((r) => r[obj]).filter((v) => v !== null && Number.isFinite(v)).sort((a, b) => a - b);
  const median = scores.length ? scores[Math.floor(scores.length / 2)] : null;
  const dev = m.context && m.context.dev;
  st.metric = st.metric || obj;
  st.hx = st.hx || m.varying[0] || null;
  st.hy = st.hy || m.varying[1] || null;

  host.innerHTML = `
    <header class="hero">
      <div class="hero-l">
        <div class="eyebrow">${esc(m.category)} · parameter optimization ${dev ? `<span class="badge dev">Developer mode · train period only</span>` : ""}</div>
        <h1>${esc(m.strategy)}</h1>
        <div class="sub">${esc(m.symbol)} · ${esc(m.interval)} · ${esc(m.start.slice(0, 16))} → ${esc(m.end.slice(0, 16))} · ${m.bars.toLocaleString()} bars</div>
        <div class="sub">${m.tested.toLocaleString()} combinations tested${m.failed ? ` · ${m.failed} failed` : ""}${m.dropped_by_constraint ? ` · ${m.dropped_by_constraint} removed by constraint <code>${esc(m.constraint)}</code>` : ""}
          · ranked by <b>${esc(m.objective_label)}</b> (min ${m.min_trades} trades) · ${(m.elapsed_ms / 1000).toFixed(1)}s</div>
        ${Object.keys(fixed).length ? `<div class="chips"><span class="muted small">Fixed:</span> ${paramChips(fixed)}</div>` : ""}
      </div>
      <div class="hero-r">
        <div class="muted small">Best ${esc(m.objective_label)}</div>
        <div class="big ${(best[obj] ?? 0) >= 0 ? "pos" : "neg"}">${short(best[obj], fmtOf(obj))}</div>
        <div class="muted">median of all: ${short(median, fmtOf(obj))} · ${((prof / P.rows.length) * 100).toFixed(0)}% profitable</div>
        <div class="muted small">Report ${esc(P.id)} · ${esc(m.created.replace("T", " "))}</div>
      </div>
    </header>

    ${section("Best parameters", `
      <div class="bestbox">
        <div>
          <div class="bp-grid">${m.varying.map((k) => {
            const vals = m.values[k];
            return `<div class="bp"><div class="k">${esc(k)}</div><div class="v">${esc(best.params[k])}</div>
              <div class="r">tested ${esc(vals[0])} → ${esc(vals[vals.length - 1])} (${vals.length} values)</div></div>`;
          }).join("") || `<span class="muted">No parameter was varied.</span>`}</div>
          <div class="row-actions">
            <button class="btn primary live-only" id="useBest" title="Load these values into the strategy form of the terminal">↩ Use in terminal</button>
            <button class="btn" id="copyBest" title="Copy as JSON">Copy params</button>
          </div>
          <p class="note">Ranking uses ${esc(m.objective_label)}; combinations with fewer than ${m.min_trades} trades are listed but never ranked first.
            ${dev ? "Next step: press <b>Backtest</b> in developer mode to see these parameters on the held-out test period." : "Next step: check these parameters on other securities with a <b>universe test</b>."}</p>
        </div>
        <div class="statlist">
          ${statRows(best)}
        </div>
      </div>`)}

    ${kpiCards(P.best.metrics)}

    ${section("What the search says", insightCards(P.insights) || `<p class="muted">No notes.</p>`)}

    ${m.varying.length ? section("Parameter landscape", `
      <div class="ctrl screen-only">
        ${m.varying.length > 1 ? `<label>X <select id="hx">${m.varying.map((k) => `<option ${k === st.hx ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>
        <label>Y <select id="hy">${m.varying.map((k) => `<option ${k === st.hy ? "selected" : ""}>${esc(k)}</option>`).join("")}</select></label>` : ""}
        <label>Metric <select id="hm">${P.metric_defs.map((d) => `<option value="${d.key}" ${d.key === st.metric ? "selected" : ""}>${esc(d.label)}</option>`).join("")}</select></label>
        ${m.varying.length > 2 ? `<label>Other parameters <select id="ha">
          <option value="best" ${st.agg === "best" ? "selected" : ""}>best value over them</option>
          <option value="mean" ${st.agg === "mean" ? "selected" : ""}>average over them</option>
          <option value="atbest" ${st.agg === "atbest" ? "selected" : ""}>fixed at the best combination</option></select></label>` : ""}
      </div>
      <div id="heat"></div>
      <p class="note">Look for a broad green area, not a single bright cell: parameters in the middle of a plateau keep working when the market changes a little. The outlined cell is the best combination. Click a cell to filter the table below.</p>`) : ""}

    ${m.varying.length ? section("Sensitivity — one parameter at a time", `<div class="chartgrid" id="sens"></div>
      <p class="note">For each tested value: the best and the average <span id="sensMetric"></span> over all other parameter values. A flat, high line means the parameter barely matters (good); a sharp spike means fragile.</p>`) : ""}

    ${section("Top equity curves", `<div id="topEq" class="tchart"></div>
      <p class="note">The 10 best eligible combinations (% return) — similar curves mean the result doesn't depend on exact values.</p>`)}

    <div class="chartgrid">
      ${section("Risk vs return — every combination", `<div id="rr"></div>`)}
      ${section(`Distribution of ${esc(m.objective_label)}`, `<div id="dist"></div>`)}
    </div>

    ${section("Best combination — equity vs buy & hold", `<div id="bestEq" class="tchart"></div><div id="bestDd" class="tchart short" style="margin-top:8px"></div>`)}

    ${section(`All results <span class="muted small" id="rowsInfo"></span>`, `
      <div class="ctrl screen-only">
        <label><input type="checkbox" id="elig" ${st.eligibleOnly ? "checked" : ""}> only ≥ ${m.min_trades} trades</label>
        <label>Show <select id="lim"><option value="50">top 50</option><option value="100" selected>top 100</option><option value="500">top 500</option><option value="0">all</option></select></label>
        <span id="cellFilter"></span>
      </div>
      <div class="tablewrap"><table class="tbl" id="rows"></table></div>`, "break")}

    ${section("Best combination — all metrics", metricTables(P.best.metrics) + `<p class="note">${costsNote(m.settings, m.costs)}. Ratios annualised on the ${esc(m.market)} calendar.</p>`)}

    ${P.errors && P.errors.length ? section(`Failed combinations <span class="muted small">${m.failed}</span>`,
      `<ul class="errlist">${P.errors.slice(0, 20).map((e) => `<li><code>${esc(JSON.stringify(e.params))}</code> — ${esc(e.error)}</li>`).join("")}</ul>`) : ""}

    ${section("Strategy source", `<pre class="code"><code>${highlightPy(m.source || "")}</code></pre>`, "break")}
  `;

  const use = $("#useBest");
  if (use) use.onclick = () => { if (sendToTerminal(m.strategy, best.params, { symbol: m.symbol, interval: m.interval })) flash(use, "✓ Sent to terminal"); };
  $("#copyBest").onclick = (e) => copyText(JSON.stringify(best.params)).then(() => flash(e.target, "✓ Copied"));
  ["hx", "hy", "hm", "ha"].forEach((id) => { const el = $("#" + id); if (el) el.onchange = () => { st.hx = $("#hx")?.value || st.hx; st.hy = $("#hy")?.value || st.hy; st.metric = $("#hm").value; st.agg = $("#ha")?.value || st.agg; st.cell = null; drawLandscape(); drawTable(); }; });
  $("#elig").onchange = (e) => { st.eligibleOnly = e.target.checked; drawTable(); };
  $("#lim").onchange = (e) => { st.limit = +e.target.value; drawTable(); };
  drawLandscape();
  drawSvgs();
  drawCharts();
  drawTable();
}

function statRows(best) {
  const nb = P.neighbours, m = P.meta, obj = m.objective;
  const rows = [
    ["Return", fmtMetric(best.total_return, "pct")], ["Max drawdown", fmtMetric(best.max_dd, "pct")],
    ["Sharpe", fmtMetric(best.sharpe, "ratio")], ["Trades", best.trades],
    ["Win rate", fmtMetric(best.win_rate, "pct")], ["Profit factor", fmtMetric(best.profit_factor, "ratio")],
    ["Buy & hold", fmtMetric(m.buy_hold, "pct")],
  ];
  if (nb && nb.count) rows.push([`Neighbours (±1 step, ${nb.count})`, `avg ${short(nb.mean, fmtOf(obj))} · worst ${short(nb.min, fmtOf(obj))}`]);
  return rows.map(([a, b]) => `<span>${a}</span><b>${b}</b>`).join("");
}

/* ---------------- heatmap / sensitivity (computed in the browser from the result table) */
function aggregate(vals, how) {
  const v = vals.filter((x) => x !== null && Number.isFinite(x));
  if (!v.length) return null;
  if (how === "mean") return v.reduce((a, b) => a + b, 0) / v.length;
  return Math.max(...v);
}

function drawLandscape() {
  const m = P.meta, metric = st.metric, best = P.rows[0];
  if (!m.varying.length) return;
  const others = (keys) => m.varying.filter((k) => !keys.includes(k));
  const rowsFor = (keys) => st.agg === "atbest" ? P.rows.filter((r) => others(keys).every((k) => r.params[k] === best.params[k])) : P.rows;
  const how = st.agg === "mean" ? "mean" : "best";
  const fmt = (v) => short(v, fmtOf(metric));
  const center = CENTER[metric] ?? 0;
  const box = $("#heat");
  if (m.varying.length === 1 || st.hx === st.hy || !st.hy) {
    const k = st.hx || m.varying[0];
    const vals = m.values[k];
    const rs = rowsFor([k]);
    catLines(box, vals.map(String), [
      { name: `best ${labelOf(metric)}`, values: vals.map((v) => aggregate(rs.filter((r) => r.params[k] === v).map((r) => r[metric]), "best")), color: "#089981" },
      { name: "average", values: vals.map((v) => aggregate(rs.filter((r) => r.params[k] === v).map((r) => r[metric]), "mean")), color: "#2962ff", dashed: true },
    ], { xLabel: k, yFmt: fmt, zero: center === 0, mark: vals.findIndex((v) => pkey(v) === pkey(best.params[k])) });
    return;
  }
  const X = m.values[st.hx], Y = m.values[st.hy], rs = rowsFor([st.hx, st.hy]);
  const cell = new Map();
  rs.forEach((r) => {
    const key = pkey(r.params[st.hx]) + "|" + pkey(r.params[st.hy]);
    (cell.get(key) || cell.set(key, []).get(key)).push(r[metric]);
  });
  const z = Y.map((yv) => X.map((xv) => aggregate(cell.get(pkey(xv) + "|" + pkey(yv)) || [], how)));
  heatGrid(box, X.map(String), Y.map(String), z, {
    fmt, xTitle: st.hx, yTitle: st.hy, center,
    highlight: [X.findIndex((v) => pkey(v) === pkey(best.params[st.hx])), Y.findIndex((v) => pkey(v) === pkey(best.params[st.hy]))],
    onCell: (xi, yi) => { st.cell = { [st.hx]: X[xi], [st.hy]: Y[yi] }; drawTable(); $("#rows").scrollIntoView({ behavior: "smooth", block: "start" }); },
  });
}

function drawSvgs() {
  const m = P.meta, obj = m.objective, metric = st.metric || obj, best = P.rows[0];
  const sens = $("#sens");
  if (sens) {
    $("#sensMetric").textContent = labelOf(metric);
    sens.innerHTML = m.varying.map((k, i) => `<div><h3>${esc(k)}</h3><div id="sens${i}" class="svgbox"></div></div>`).join("");
    m.varying.forEach((k, i) => {
      const vals = m.values[k];
      const by = vals.map((v) => P.rows.filter((r) => pkey(r.params[k]) === pkey(v)).map((r) => r[metric]));
      catLines($("#sens" + i), vals.map(String), [
        { name: "best", values: by.map((x) => aggregate(x, "best")), color: "#089981" },
        { name: "average", values: by.map((x) => aggregate(x, "mean")), color: "#2962ff", dashed: true },
      ], { xLabel: k, yFmt: (v) => short(v, fmtOf(metric)), mark: vals.findIndex((v) => pkey(v) === pkey(best.params[k])) });
    });
  }
  // risk / return scatter (all combos; best highlighted)
  let pts = P.rows.map((r, i) => ({ x: r.max_dd, y: r.total_return, color: r.eligible ? ((r.total_return ?? 0) >= 0 ? "#089981" : "#f23645") : "#9598a1", big: i === 0, label: i === 0 ? "best" : "" }));
  if (pts.length > 2500) pts = pts.slice(0, 500).concat(pts.slice(500).filter((_, i) => i % Math.ceil((pts.length - 500) / 2000) === 0));
  labelScatter($("#rr"), pts.map((p, i) => ({ ...p, label: i === 0 ? "★ best" : "" })), { xLabel: "Max drawdown %", yLabel: "Return %", xFmt: (v) => v.toFixed(0), yFmt: (v) => v.toFixed(0) });
  // distribution
  const sc = P.rows.map((r) => r[obj]).filter((v) => v !== null && Number.isFinite(v));
  if (sc.length) {
    const lo = Math.min(...sc), hi = Math.max(...sc), bins = Math.min(30, Math.max(5, Math.ceil(Math.sqrt(sc.length))));
    const w = (hi - lo) / bins || 1;
    const edges = Array.from({ length: bins + 1 }, (_, i) => lo + i * w);
    const counts = new Array(bins).fill(0);
    sc.forEach((v) => counts[Math.min(bins - 1, Math.floor((v - lo) / w))]++);
    histogram($("#dist"), edges, counts);
    const ax = $("#dist").querySelector("text.axis");
    if (ax) ax.textContent = m.objective_label;
    if (fmtOf(obj) !== "pct") $$("#dist text.tick").forEach((t) => { t.textContent = t.textContent.replace("%", ""); });
  }
}

function drawCharts() {
  charts.splice(0).forEach((c) => c.remove());
  const m = P.meta, init = m.settings.init_cash;
  const top = new TimeChart($("#topEq"), { theme });
  const COLORS = ["#2962ff", "#ff9800", "#e040fb", "#00bcd4", "#8d6e63", "#ff4081", "#66bb6a", "#7e57c2", "#26c6da", "#ef5350"];
  const t = P.curves.t;
  top.set([
    ...P.curves.top.map((c, i) => ({ id: "c" + i, name: `#${c.rank} ` + m.varying.map((k) => `${k}=${c.params[k]}`).join(" "), color: COLORS[i % 10], width: i === 0 ? 2.4 : 1.3, t, v: c.values })),
    { id: "bh", name: "Buy & hold", color: "#9598a1", dashed: true, t: P.best.series.t, v: P.best.series.benchmark.map((v) => v === null ? null : (v / init) * 100 - 100) },
  ]);
  const be = new TimeChart($("#bestEq"), { theme });
  be.set([
    { id: "eq", name: "Best combination", color: "#2962ff", width: 2, t: P.best.series.t, v: P.best.series.equity.map((v) => v === null ? null : (v / init) * 100 - 100) },
    { id: "bh", name: "Buy & hold", color: "#9598a1", dashed: true, t: P.best.series.t, v: P.best.series.benchmark.map((v) => v === null ? null : (v / init) * 100 - 100) },
  ]);
  const dd = new TimeChart($("#bestDd"), { theme });
  dd.set([{ id: "dd", name: "Drawdown", color: "#f23645", area: true, t: P.best.series.t, v: P.best.series.drawdown }]);
  charts.push(top, be, dd);
}

function drawTable() {
  const m = P.meta, obj = m.objective;
  let rows = P.rows;
  if (st.eligibleOnly) rows = rows.filter((r) => r.eligible);
  if (st.cell) rows = rows.filter((r) => Object.entries(st.cell).every(([k, v]) => pkey(r.params[k]) === pkey(v)));
  const shown = st.limit ? rows.slice(0, st.limit) : rows;
  $("#rowsInfo").textContent = `${shown.length.toLocaleString()} of ${rows.length.toLocaleString()} shown`;
  $("#cellFilter").innerHTML = st.cell ? `<span class="chip">${Object.entries(st.cell).map(([k, v]) => `${esc(k)}=${esc(v)}`).join(" · ")} <a href="#" id="clrCell">✕</a></span>` : "";
  const clr = $("#clrCell");
  if (clr) clr.onclick = (e) => { e.preventDefault(); st.cell = null; drawTable(); };
  const keys = [obj, ...["total_return", "cagr", "max_dd", "sharpe", "sortino", "calmar", "win_rate", "profit_factor", "trades", "expectancy_pct", "exposure", "excess"].filter((k) => k !== obj)];
  const cols = [
    { key: "rank", label: "#", cls: "num" },
    ...m.varying.map((k) => ({ key: "p:" + k, label: esc(k), cls: "num", sort: (r) => r.params[k], fmt: (r) => `<b>${esc(r.params[k])}</b>` })),
    ...keys.map((k) => ({ key: k, label: esc(labelOf(k)) + (k === obj ? " ★" : ""), cls: "num", fmt: (r) => {
      const v = r[k], f = fmtOf(k);
      const color = ["total_return", "cagr", "excess", "expectancy_pct", "max_dd"].includes(k) && Number.isFinite(v) ? (v > 0 ? "pos" : v < 0 ? "neg" : "") : "";
      return `<span class="${color}">${fmtMetric(v, f)}</span>`;
    } })),
    ...(STANDALONE ? [] : [{ key: "use", label: "", nosort: true, fmt: (r) => `<button class="btn sm" data-use="${r.rank}" title="Load into the terminal">Use</button>` }]),
  ];
  sortableTable($("#rows"), shown, cols, {
    rowAttrs: (r) => `class="${r.rank === 1 ? "best" : ""} ${r.eligible ? "" : "inel"}"`,
    onRender: (el) => $$("[data-use]", el).forEach((b) => b.onclick = () => {
      const r = P.rows.find((x) => x.rank === +b.dataset.use);
      if (r && sendToTerminal(m.strategy, r.params, { symbol: m.symbol, interval: m.interval })) flash(b, "✓");
    }),
  });
}

(async () => {
  const getTheme = bindToolbar({
    kind: "optimize", themeKey: "h1-report-theme", getId: () => P && P.id,
    redraw: (t) => { theme = t; if (P) drawCharts(); },
  });
  theme = getTheme();
  try {
    P = await loadReport("optimize", host);
    render();
  } catch (e) { console.error(e); showError(host, e.message); }
})();
