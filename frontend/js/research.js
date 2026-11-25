/* =====================================================================
   Shared helpers for the research report pages (optimize.html, universe.html):
   loading a report (or waiting for its background job), toolbar (theme / PDF / HTML),
   a multi-series time chart and a colour palette for many securities.
   ===================================================================== */
import { api } from "./api.js";
import { PALETTE, fmtTime } from "./chart.js";
import { $, esc } from "./ui.js";

const LWC = window.LightweightCharts;
export const STANDALONE = !!window.__STANDALONE__;

export function colorFor(i) {
  if (i < PALETTE.length) return PALETTE[i];
  const h = (i * 137.508) % 360;                         // golden-angle hues stay distinct
  return `hsl(${h.toFixed(0)}, 62%, ${i % 2 ? 46 : 56}%)`;
}

export const getTheme = (key) => { try { return localStorage.getItem(key) || "light"; } catch (e) { return "light"; } };
export const setTheme = (key, t) => {
  document.body.classList.toggle("dark", t === "dark");
  try { localStorage.setItem(key, t); } catch (e) { /* ignore */ }
};

/* ---------------------------------------------------------------- loading */
const RX = /^\[(\d+)\/(\d+)\]\s*(.*)$/;

/** report from: embedded data (standalone export) → ?id= → ?job= (waits, with a progress bar) */
export async function loadReport(kind, host) {
  if (window.__REPORT__) return window.__REPORT__;
  const qs = new URLSearchParams(location.search);
  let id = qs.get("id");
  const job = qs.get("job");
  if (!id && job) {
    id = await waitJob(job, host, kind);
    history.replaceState(null, "", `?id=${encodeURIComponent(id)}`);
  }
  if (!id) throw new Error("No report id in the address.");
  host.innerHTML = `<div class="loading">Loading report…</div>`;
  return api.researchReport(kind, id);
}

async function waitJob(jid, host, kind) {
  const label = kind === "optimize" ? "Optimizing parameters" : "Testing the universe";
  host.innerHTML = `<div class="jobbox"><div class="eyebrow">${label}</div>
    <h2 id="jobMsg">Starting…</h2><div class="pbar"><i id="jobBar"></i></div>
    <div class="muted small" id="jobSub">This page fills in automatically when the run is finished — you can leave it open.</div></div>`;
  const t0 = Date.now();
  for (;;) {
    let j;
    try { j = await api.job(jid); } catch (e) { throw new Error(`Job ${jid} not found — the server may have restarted. Run it again from the terminal.`); }
    const last = (j.log || [])[(j.log || []).length - 1] || "";
    const m = RX.exec(last);
    if (m) {
      const [a, b] = [+m[1], +m[2]];
      $("#jobBar").style.width = `${b ? Math.round((a / b) * 100) : 0}%`;
      $("#jobMsg").textContent = m[3] || `${a} / ${b}`;
      const sec = (Date.now() - t0) / 1000;
      if (a > 0 && a < b) $("#jobSub").textContent = `${a.toLocaleString()} of ${b.toLocaleString()} · ${sec.toFixed(0)}s elapsed · ~${Math.max(1, (sec / a) * (b - a)).toFixed(0)}s left`;
    }
    if (j.status === "done") return j.result.id;
    if (j.status === "error") throw new Error(j.error || "The run failed");
    await new Promise((r) => setTimeout(r, 700));
  }
}

export function showError(host, msg) {
  host.innerHTML = `<div class="loading"><b>Could not load the report.</b><br>${esc(msg)}<br><br><a href="/">← back to the terminal</a></div>`;
}

/* ---------------------------------------------------------------- toolbar */
/**
 * Wires #btnTheme, #btnPdf, #btnHtml.  redraw(theme) must re-render the theme-dependent charts.
 * beforePrint/afterPrint let a page add print-only content (e.g. every security's own page).
 */
export function bindToolbar({ kind, themeKey, redraw, getId, beforePrint, afterPrint }) {
  let theme = getTheme(themeKey);
  setTheme(themeKey, theme);
  if (STANDALONE) document.body.classList.add("standalone");
  $("#btnTheme").onclick = () => { theme = theme === "dark" ? "light" : "dark"; setTheme(themeKey, theme); redraw(theme); };
  $("#btnPdf").onclick = async () => {
    const prev = theme;
    theme = "light"; setTheme(themeKey, theme);
    document.body.classList.add("printing");
    if (beforePrint) await beforePrint();
    redraw(theme);
    setTimeout(() => {
      window.print();
      document.body.classList.remove("printing");
      if (afterPrint) afterPrint();
      theme = prev; setTheme(themeKey, theme); redraw(theme);
    }, 700);
  };
  const html = $("#btnHtml");
  if (html) html.onclick = () => { const id = getId(); if (id) location.href = `/api/research/export/${kind}/${encodeURIComponent(id)}`; };
  return () => theme;
}

/** send parameters to the terminal tab (it listens for this key) */
export function sendToTerminal(strategy, params, extra = {}) {
  try {
    localStorage.setItem("h1-use-params", JSON.stringify({ strategy, params, ...extra, ts: Date.now() }));
    return true;
  } catch (e) { return false; }
}

export async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {
    const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select();
    const ok = document.execCommand("copy"); ta.remove(); return ok;
  }
}

export function flash(btn, text) {
  const old = btn.textContent; btn.textContent = text; btn.disabled = true;
  setTimeout(() => { btn.textContent = old; btn.disabled = false; }, 1400);
}

/* ---------------------------------------------------------------- time chart */
const THEME = {
  light: { bg: "#ffffff", text: "#3a3e4a", grid: "rgba(220,224,232,0.7)", border: "#e0e3eb" },
  dark: { bg: "#161a24", text: "#b2b5be", grid: "rgba(42,46,57,0.6)", border: "#2a2e39" },
};

/**
 * Several time series in one interactive chart (zoom, pan, crosshair legend).
 * series: [{id, name, color, t:[sec], v:[number|null], width, dashed, visible}]
 */
export class TimeChart {
  constructor(el, { theme = "light", unit = "%", height = null, baseline = false } = {}) {
    this.el = el; this.unit = unit; this.baseline = baseline;
    el.classList.add("tchart");
    if (height) el.style.height = height + "px";
    el.innerHTML = `<div class="tlegend"></div><div class="tbody"></div>`;
    this.legend = el.querySelector(".tlegend");
    const th = THEME[theme] || THEME.light;
    this.chart = LWC.createChart(el.querySelector(".tbody"), {
      autoSize: true,
      layout: { background: { type: "solid", color: th.bg }, textColor: th.text, fontSize: 11,
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" },
      grid: { vertLines: { color: th.grid }, horzLines: { color: th.grid } },
      rightPriceScale: { borderColor: th.border, minimumWidth: 64 },
      timeScale: { borderColor: th.border, timeVisible: true, secondsVisible: false, rightOffset: 4 },
      crosshair: { mode: LWC.CrosshairMode.Normal },
      localization: { timeFormatter: (t) => fmtTime(t), priceFormatter: (v) => `${v.toFixed(2)}${unit}` },
      handleScale: { axisPressedMouseMove: { time: true, price: true } },
    });
    this.items = new Map();
    this.chart.subscribeCrosshairMove((p) => this._legend(p));
  }

  set(list) {
    for (const it of this.items.values()) this.chart.removeSeries(it.s);
    this.items.clear();
    list.forEach((sr) => this.add(sr));
    this.chart.timeScale().fitContent();
    this._legend(null);
  }

  add(sr) {
    const opts = { color: sr.color, lineWidth: sr.width || 1.6, priceLineVisible: false, lastValueVisible: false,
      lineStyle: sr.dashed ? LWC.LineStyle.Dashed : LWC.LineStyle.Solid, visible: sr.visible !== false, crosshairMarkerRadius: 3 };
    const s = sr.area
      ? this.chart.addBaselineSeries({ baseValue: { type: "price", price: 0 }, priceLineVisible: false, lastValueVisible: false,
          topLineColor: "rgba(0,0,0,0)", topFillColor1: "rgba(0,0,0,0)", topFillColor2: "rgba(0,0,0,0)",
          bottomLineColor: sr.color, bottomFillColor1: "rgba(242,54,69,0.05)", bottomFillColor2: "rgba(242,54,69,0.3)", lineWidth: 1, visible: sr.visible !== false })
      : this.chart.addLineSeries(opts);
    const data = [];
    let last = -Infinity;
    for (let i = 0; i < sr.t.length; i++) {
      const t = sr.t[i], v = sr.v[i];
      if (v === null || v === undefined || !Number.isFinite(v) || t <= last) continue;
      data.push({ time: t, value: v }); last = t;
    }
    s.setData(data);
    this.items.set(sr.id, { s, sr, data });
  }

  replace(sr) {
    const it = this.items.get(sr.id);
    if (it) { this.chart.removeSeries(it.s); this.items.delete(sr.id); }
    this.add(sr);
    this._legend(null);
  }

  visible(id, on) { const it = this.items.get(id); if (it) { it.sr.visible = on; it.s.applyOptions({ visible: on }); } this._legend(null); }
  fit() { this.chart.timeScale().fitContent(); }
  remove() { this.chart.remove(); }

  _legend(p) {
    const rows = [];
    for (const { s, sr, data } of this.items.values()) {
      if (sr.visible === false || sr.legend === false) continue;
      let v = null;
      if (p && p.time !== undefined && p.seriesData) { const d = p.seriesData.get(s); v = d ? d.value : null; }
      else if (data.length) v = data[data.length - 1].value;
      rows.push(`<span><i style="background:${sr.color}"></i>${esc(sr.name)} <b>${v === null ? "—" : v.toFixed(2) + this.unit}</b></span>`);
    }
    const when = p && p.time !== undefined ? `<span class="muted">${fmtTime(p.time)}</span>` : `<span class="muted">end</span>`;
    this.legend.innerHTML = rows.length ? when + rows.slice(0, 14).join("") + (rows.length > 14 ? `<span class="muted">+${rows.length - 14} more</span>` : "") : "";
  }
}

/** "YYYY-MM-DD" → seconds (chart time; IST wall-clock stored as UTC like the rest of the app) */
export const daySec = (d) => Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)) / 1000;

export function paramChips(p) {
  return Object.entries(p || {}).map(([k, v]) => `<span class="chip">${esc(k)} <b>${esc(v)}</b></span>`).join("");
}

export function section(title, inner, cls = "", id = "") {
  return `<section class="card ${cls}" ${id ? `id="${id}"` : ""}><h2>${title}</h2>${inner}</section>`;
}

export function costsNote(st, costs) {
  if (!st) return "";
  const c = costs ? `${esc(costs.preset)} · fees ${(+costs.fees_pct).toFixed(3)}%/side · slippage ${(+costs.slippage_pct).toFixed(3)}%/side · ` : "";
  return `${c}fills ${st.execution === "next_open" ? "next bar open" : "same bar close"} · capital ${Number(st.init_cash).toLocaleString("en-IN")} · size ${st.size_pct}%` +
    `${st.square_off ? " · intraday square-off " + esc(st.square_off_time) : ""}${st.sl_pct ? " · SL " + st.sl_pct + "%" : ""}${st.tp_pct ? " · TP " + st.tp_pct + "%" : ""}`;
}

/** sortable table helper: columns [{key, label, fmt(row)->html, sort(row)->value, cls}] */
export function sortableTable(el, rows, columns, { initial = null, rowAttrs = () => "", onRender = null } = {}) {
  let sort = initial || { key: null, dir: -1 };
  const draw = () => {
    let list = rows.slice();
    if (sort.key) {
      const col = columns.find((c) => c.key === sort.key);
      const val = col.sort || ((r) => r[col.key]);
      list.sort((a, b) => {
        const x = val(a), y = val(b);
        const nx = x === null || x === undefined || (typeof x === "number" && !Number.isFinite(x));
        const ny = y === null || y === undefined || (typeof y === "number" && !Number.isFinite(y));
        if (nx && ny) return 0; if (nx) return 1; if (ny) return -1;
        return (x > y ? 1 : x < y ? -1 : 0) * sort.dir;
      });
    }
    el.innerHTML = `<thead><tr>${columns.map((c) => `<th data-k="${c.key}" class="${c.cls || ""} ${c.nosort ? "" : "sortable"} ${sort.key === c.key ? (sort.dir > 0 ? "asc" : "desc") : ""}" title="${esc(c.title || "")}">${c.label}</th>`).join("")}</tr></thead>
      <tbody>${list.map((r) => `<tr ${rowAttrs(r)}>${columns.map((c) => `<td class="${c.cls || ""}">${c.fmt ? c.fmt(r) : esc(r[c.key])}</td>`).join("")}</tr>`).join("")}</tbody>`;
    el.querySelectorAll("th.sortable").forEach((th) => th.onclick = () => {
      const k = th.dataset.k;
      sort = sort.key === k ? { key: k, dir: -sort.dir } : { key: k, dir: -1 };
      draw();
    });
    if (onRender) onRender(el, list);
  };
  draw();
  return { redraw: (newRows) => { if (newRows) rows = newRows; draw(); } };
}
