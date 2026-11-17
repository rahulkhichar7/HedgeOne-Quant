/* =====================================================================
   Strategy report page:  /report.html?id=<report_id>
   ===================================================================== */
import { api } from "./api.js";
import { ChartStack, PALETTE, fmtNum, fmtTime } from "./chart.js";
import { bars, heatColor, histogram, lines, scatter } from "./svg.js";
import { $, $$, esc, highlightPy, insightCards, kpiCards, metricMap, metricTables, tradeRows, TRADE_HEAD } from "./ui.js";

const id = new URLSearchParams(location.search).get("id");
let R = null, chart = null;
let theme = (() => { try { return localStorage.getItem("h1-report-theme") || "light"; } catch (e) { return "light"; } })();

function section(title, inner, cls = "") {
  return `<section class="card ${cls}"><h2>${title}</h2>${inner}</section>`;
}

function paramsChips(p) {
  return Object.entries(p || {}).map(([k, v]) => `<span class="chip">${esc(k)} <b>${esc(v)}</b></span>`).join("");
}

function render() {
  const m = R.meta, a = R.analysis, mm = metricMap(R.metrics);
  document.title = `${m.strategy} · ${m.symbol} · Report`;
  const st = m.settings;
  $("#report").innerHTML = `
    <header class="hero">
      <div class="hero-l">
        <div class="eyebrow">${esc(m.category)} strategy report</div>
        <h1>${esc(m.strategy)}</h1>
        <div class="sub">${esc(m.symbol)} · ${esc(m.interval)} · ${esc(m.start.slice(0, 16))} → ${esc(m.end.slice(0, 16))} · ${m.bars.toLocaleString()} bars</div>
        <div class="chips">${paramsChips(m.params)}</div>
      </div>
      <div class="hero-r">
        <div class="big ${(mm.total_return?.value ?? 0) >= 0 ? "pos" : "neg"}">${(mm.total_return?.value ?? 0).toFixed(2)}%</div>
        <div class="muted">vs buy & hold ${(mm.buy_hold?.value ?? 0).toFixed(2)}%</div>
        <div class="muted small">Report ${esc(R.id)} · ${esc(m.created.replace("T", " "))}</div>
      </div>
    </header>

    ${kpiCards(R.metrics)}

    ${section("Price, trades & equity", `
      <div class="legend-row">
        <span><i class="sw win"></i>winning trade zone</span><span><i class="sw loss"></i>losing trade zone</span>
        <span class="muted">Box = entry → exit price. Hover a zone for details; click a row in the trade list to zoom.</span>
      </div>
      <div id="rchart" class="rchart"></div><div id="rcard" class="rcard hidden"></div>`, "chartcard")}

    ${section("Where it works · where it fails", insightCards(a.insights) || `<p class="muted">No insights.</p>`)}

    ${section("All metrics", metricTables(R.metrics) +
      `<p class="note">Costs: ${esc(m.costs.preset)} · fees ${m.costs.fees_pct.toFixed(3)}%/side · slippage ${m.costs.slippage_pct.toFixed(3)}%/side
       · fills ${st.execution === "next_open" ? "next bar open" : "same bar close"} · capital ${fmtNum(st.init_cash)} · size ${st.size_pct}%${st.square_off ? " · intraday square-off " + st.square_off_time : ""}.
       Ratios annualised on the ${esc(m.market)} trading calendar.</p>`)}

    <div class="two">
      ${section("Monthly returns", monthlyTable(a.monthly))}
      ${section("Yearly: strategy vs buy & hold", `<div id="yearly"></div>`)}
    </div>

    ${section("Breakdowns", `<p class="muted small">P&L of each bucket as % of starting capital (bars) and win rate (blue line). Buckets are by trade <b>entry</b> time.</p>
      <div class="bd-grid">${a.breakdowns.map((b, i) => `
        <div class="bd"><h3>${esc(b.title)} <span class="muted small">${esc(b.note || "")}</span></h3>
          <div id="bd${i}" class="svgbox"></div>
          <table class="tbl"><thead><tr><th></th><th>Trades</th><th>Win %</th><th>P&L %</th><th>Avg ret</th><th>PF</th></tr></thead><tbody>
          ${b.rows.map((r) => `<tr><td>${esc(r.label)}</td><td>${r.trades}</td><td>${r.win_rate?.toFixed(0) ?? "—"}</td>
            <td class="${r.pnl >= 0 ? "pos" : "neg"}">${r.pnl_pct.toFixed(2)}</td><td>${r.avg_return?.toFixed(2) ?? "—"}%</td>
            <td>${r.profit_factor?.toFixed(2) ?? "—"}</td></tr>`).join("")}</tbody></table></div>`).join("")}</div>`)}

    ${section("Trade quality", `<div class="grid4">
      <div><h3>Return distribution</h3><div id="hist" class="svgbox"></div></div>
      <div><h3>MAE vs result <span class="muted small">how far trades went against you</span></h3><div id="mae" class="svgbox"></div></div>
      <div><h3>MFE vs result <span class="muted small">how much profit was available</span></h3><div id="mfe" class="svgbox"></div></div>
      <div><h3>Holding time vs result</h3><div id="dur" class="svgbox"></div></div>
      <div><h3>Rolling ${a.rolling.n}-trade win rate <span class="muted small">is the edge stable over time?</span></h3><div id="roll" class="svgbox"></div></div>
      <div><h3>Cumulative P&L by trade #</h3><div id="cum" class="svgbox"></div></div>
    </div>`)}

    ${section("Worst drawdowns", `<table class="tbl"><thead><tr><th>Start</th><th>Bottom</th><th>Recovered</th><th>Depth</th><th>Length</th></tr></thead><tbody>
      ${a.drawdowns.map((d) => `<tr><td>${esc(d.start.slice(0, 16))}</td><td>${esc(d.valley.slice(0, 16))}</td><td>${esc(d.recovered ? d.end.slice(0, 16) : d.end)}</td>
        <td class="neg">${d.depth_pct.toFixed(2)}%</td><td>${esc(d.duration)}</td></tr>`).join("") || `<tr><td colspan="5">No drawdowns.</td></tr>`}</tbody></table>`)}

    ${section(`Trade list <span class="muted small">${R.trades.length} trades</span>`,
      `<div class="tradewrap"><table class="tbl trades">${TRADE_HEAD}<tbody>${tradeRows(R.trades)}</tbody></table></div>`, "break")}

    ${section("Strategy source", `<pre class="code"><code>${highlightPy(m.source || "")}</code></pre>`, "break")}
  `;
  drawChart();
  drawSvgs();
  $$(".trades tbody tr").forEach((tr) => tr.onclick = () => {
    chart.focusTrade(+tr.dataset.i);
    $("#rchart").scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

function monthlyTable(mt) {
  const all = mt.rows.flatMap((r) => r.months.filter((v) => v !== null));
  const mx = Math.max(1, ...all.map(Math.abs));
  return `<table class="tbl heat"><thead><tr><th>Year</th>${mt.months.map((x) => `<th>${x}</th>`).join("")}<th>Year</th></tr></thead><tbody>` +
    mt.rows.map((r) => `<tr><td><b>${r.year}</b></td>${r.months.map((v) => `<td style="background:${heatColor(v, mx)}">${v === null ? "" : v.toFixed(1)}</td>`).join("")}
      <td class="${r.total >= 0 ? "pos" : "neg"}"><b>${r.total.toFixed(1)}%</b></td></tr>`).join("") + `</tbody></table>`;
}

function drawChart() {
  if (chart) { chart.panes.forEach((p) => p.chart.remove()); }
  const host = $("#rchart");
  host.innerHTML = "";
  chart = new ChartStack(host, { theme, onTradeHover: hoverCard });
  chart.symbolLabel = `${R.meta.symbol} · ${R.meta.interval}`;
  chart.setCandles(R.candles);
  let ci = 0;
  for (const [n, v] of Object.entries(R.chart.overlays)) chart.addLine("s", chart.main, n, v, { color: PALETTE[ci++ % PALETTE.length] });
  for (const [pane, series] of Object.entries(R.chart.panes)) {
    const p = chart.pane("p:" + pane, pane, 110);
    let k = 1;
    for (const [n, v] of Object.entries(series)) /hist/i.test(n) ? chart.addHistogram("s", p, n, v) : chart.addLine("s", p, n, v, { color: PALETTE[k++ % PALETTE.length] });
    chart.addLevels(p, R.chart.levels[pane]);
  }
  const eq = chart.pane("equity", "Equity vs buy & hold", 140);
  chart.addLine("e", eq, "Equity", R.series.equity, { color: "#2962ff", width: 2 });
  chart.addLine("e", eq, "Buy & hold", R.series.benchmark, { color: "#9598a1", dashed: true });
  chart.addBaseline("e", chart.pane("dd", "Drawdown %", 90), "Drawdown %", R.series.drawdown);
  chart.setTrades(R.trades, R.chart.signals);
  chart.fit();
}

function hoverCard(t) {
  const c = $("#rcard");
  if (!t) { c.classList.add("hidden"); return; }
  c.innerHTML = `<b class="${t.pnl > 0 ? "pos" : "neg"}">${t.direction} ${t.return_pct >= 0 ? "+" : ""}${t.return_pct.toFixed(2)}%</b>
    · ${fmtTime(t.entry_t)} → ${t.status === "Open" ? "open" : fmtTime(t.exit_t)} · ${fmtNum(t.entry_price)} → ${fmtNum(t.exit_price)}
    · P&L ${fmtNum(t.pnl)} · MAE ${t.mae_pct.toFixed(2)}% · MFE ${t.mfe_pct.toFixed(2)}% · ${esc(t.exit_reason)}`;
  c.classList.remove("hidden");
}

function drawSvgs() {
  const a = R.analysis;
  if (a.yearly.length > 1) bars($("#yearly"), a.yearly.map((y) => String(y.year)), a.yearly.map((y) => y.strategy));
  if (a.yearly.length) {
    const box = $("#yearly");
    box.insertAdjacentHTML("beforeend", `<table class="tbl"><thead><tr><th>Year</th><th>Strategy</th><th>Buy & hold</th></tr></thead><tbody>` +
      a.yearly.map((y) => `<tr><td>${y.year}</td><td class="${y.strategy >= 0 ? "pos" : "neg"}">${y.strategy.toFixed(2)}%</td><td>${y.buy_hold.toFixed(2)}%</td></tr>`).join("") + `</tbody></table>`);
  }
  a.breakdowns.forEach((b, i) => bars($("#bd" + i), b.rows.map((r) => r.label), b.rows.map((r) => r.pnl_pct),
    { secondary: b.rows.map((r) => r.win_rate), h: 210 }));
  histogram($("#hist"), a.distribution.edges, a.distribution.counts);
  const sc = a.scatter;
  scatter($("#mae"), sc.mae, sc.ret, { xLabel: "MAE %", yLabel: "Return %" });
  scatter($("#mfe"), sc.mfe, sc.ret, { xLabel: "MFE %", yLabel: "Return %", diag: true });
  scatter($("#dur"), sc.bars, sc.ret, { xLabel: "Bars held", yLabel: "Return %" });
  lines($("#roll"), [{ name: "Win rate %", values: a.rolling.win_rate, color: "#2962ff", width: 2 },
    { name: "50%", values: a.rolling.win_rate.map(() => 50), color: "#9598a1", dashed: true, width: 1 }], { xLabel: "Trade #" });
  lines($("#cum"), [{ name: "Cumulative P&L", values: a.rolling.cum_pnl, color: "#089981", width: 2 }], { xLabel: "Trade #", zero: true });
}

function applyTheme() {
  document.body.classList.toggle("dark", theme === "dark");
  try { localStorage.setItem("h1-report-theme", theme); } catch (e) { /* ignore */ }
}

$("#btnTheme").onclick = () => { theme = theme === "dark" ? "light" : "dark"; applyTheme(); if (R) drawChart(); };
$("#btnPdf").onclick = () => {
  // print in light theme with a page-sized chart; the browser's "Save as PDF" creates the file
  const prev = theme;
  theme = "light"; applyTheme();
  document.body.classList.add("printing");
  drawChart();
  setTimeout(() => {
    window.print();
    document.body.classList.remove("printing");
    theme = prev; applyTheme(); drawChart();
  }, 500);
};

(async () => {
  applyTheme();
  if (!id) { $("#report").innerHTML = `<div class="loading">No report id. Run a <b>Deep backtest</b> in the terminal.</div>`; return; }
  try { R = await api.report(id); render(); }
  catch (e) { $("#report").innerHTML = `<div class="loading">Could not load report: ${esc(e.message)}</div>`; }
})();
