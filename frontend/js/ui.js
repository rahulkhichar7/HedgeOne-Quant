/* Small shared UI helpers (terminal + report). */
import { fmtNum, fmtTime } from "./chart.js";

export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function fmtMetric(v, fmt) {
  if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "—";
  switch (fmt) {
    case "pct": return `${v >= 0 ? "" : ""}${v.toFixed(2)}%`;
    case "money": return fmtNum(v, 2);
    case "int": return String(v);
    case "ratio": return v.toFixed(2);
    default: return esc(v);
  }
}

const COLORED = new Set(["net_profit", "total_return", "cagr", "buy_hold", "excess", "expectancy", "expectancy_pct",
  "avg_win", "avg_loss", "best", "worst", "max_dd", "alpha", "pnl", "pnl_pct", "avg_return", "strategy"]);
export function signClass(v, fmt, key) {
  if (typeof v !== "number" || !Number.isFinite(v)) return "";
  if (key ? !COLORED.has(key) : !["pct", "money"].includes(fmt)) return "";
  return v > 0 ? "pos" : v < 0 ? "neg" : "";
}

export function metricMap(groups) {
  const m = {};
  (groups || []).forEach((g) => g.items.forEach((i) => { m[i.key] = i; }));
  return m;
}

const KPIS = [["net_profit", "Net profit"], ["total_return", "Return"], ["cagr", "CAGR"], ["max_dd", "Max DD"],
  ["sharpe", "Sharpe"], ["win_rate", "Win rate"], ["profit_factor", "Profit factor"], ["trades", "Trades"]];

export function kpiCards(groups) {
  const m = metricMap(groups);
  return `<div class="kpis">` + KPIS.map(([k, lab]) => {
    const it = m[k]; if (!it) return "";
    return `<div class="kpi"><div class="kpi-l">${lab}</div><div class="kpi-v ${signClass(it.value, it.fmt, k)}">${fmtMetric(it.value, it.fmt)}</div></div>`;
  }).join("") + `</div>`;
}

export function metricTables(groups) {
  return `<div class="mgroups">` + (groups || []).map((g) => `
    <div class="mgroup"><h5>${esc(g.title)}</h5><table class="mtable">` +
      g.items.map((i) => `<tr><td>${esc(i.label)}</td><td class="${signClass(i.value, i.fmt, i.key)}">${fmtMetric(i.value, i.fmt)}</td></tr>`).join("") +
    `</table></div>`).join("") + `</div>`;
}

const ICON = { bad: "▼", warn: "!", info: "i", good: "▲" };
export function insightCards(list) {
  if (!list || !list.length) return "";
  return `<div class="insights">` + list.map((x) => `
    <div class="insight ${x.level}"><span class="ic">${ICON[x.level] || "•"}</span>
      <div><div class="it">${esc(x.title)}</div><div class="ix">${esc(x.text)}</div></div></div>`).join("") + `</div>`;
}

export function tradeRows(trades) {
  return trades.map((t, i) => `<tr data-i="${i}" class="${t.pnl > 0 ? "win" : "loss"}">
    <td>${t.id + 1}</td><td><span class="dir ${t.direction === "Long" ? "long" : "short"}">${t.direction}</span></td>
    <td>${fmtTime(t.entry_t)}</td><td>${t.status === "Open" ? "open" : fmtTime(t.exit_t)}</td>
    <td class="num">${fmtNum(t.entry_price)}</td><td class="num">${fmtNum(t.exit_price)}</td>
    <td class="num ${t.pnl > 0 ? "pos" : "neg"}">${fmtNum(t.pnl)}</td>
    <td class="num ${t.return_pct > 0 ? "pos" : "neg"}">${t.return_pct.toFixed(2)}%</td>
    <td class="num neg">${t.mae_pct.toFixed(2)}%</td><td class="num pos">${t.mfe_pct.toFixed(2)}%</td>
    <td class="num">${t.bars}</td><td>${esc(t.exit_reason)}</td></tr>`).join("");
}

export const TRADE_HEAD = `<thead><tr><th>#</th><th>Side</th><th>Entry</th><th>Exit</th><th>Entry ₹</th><th>Exit ₹</th>
  <th>P&L</th><th>Return</th><th title="Max adverse excursion">MAE</th><th title="Max favourable excursion">MFE</th><th>Bars</th><th>Exit reason</th></tr></thead>`;

export function toast(msg, kind = "info", html = false, ms = 5000) {
  const box = document.getElementById("toasts");
  if (!box) return alert(msg);
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el[html ? "innerHTML" : "textContent"] = msg;
  box.appendChild(el);
  setTimeout(() => el.classList.add("out"), ms);
  setTimeout(() => el.remove(), ms + 400);
}

/* very small python highlighter for the read-only code viewer */
export function highlightPy(code) {
  const re = /(#[^\n]*)|("""[\s\S]*?"""|'''[\s\S]*?'''|f?"(?:\\.|[^"\\\n])*"|f?'(?:\\.|[^'\\\n])*')|(@[\w.]+)|\b(def|return|if|else|elif|for|in|and|or|not|import|from|as|lambda|True|False|None|with|while|class)\b|\b(\d+\.?\d*)\b/g;
  let out = "", last = 0, m;
  while ((m = re.exec(code))) {
    out += esc(code.slice(last, m.index));
    const cls = m[1] ? "c" : m[2] ? "s" : m[3] ? "d" : m[4] ? "k" : "n";
    out += `<span class="${cls}">${esc(m[0])}</span>`;
    last = re.lastIndex;
  }
  return out + esc(code.slice(last));
}
