/* Tiny dependency-free SVG charts for the report page (bar, histogram, scatter, line). */
const NS = "http://www.w3.org/2000/svg";
const W = 640, H = 230, M = { t: 14, r: 14, b: 42, l: 52 };
const GREEN = "#089981", RED = "#f23645", BLUE = "#2962ff", GREY = "#9598a1";

function svg(el, h = H) {
  el.innerHTML = "";
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("viewBox", `0 0 ${W} ${h}`);
  s.setAttribute("class", "svgc");
  el.appendChild(s);
  return s;
}
function node(parent, tag, attrs = {}, text) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  parent.appendChild(n);
  return n;
}
const nice = (v) => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(1) + "k" : Math.abs(v) < 10 ? v.toFixed(2) : v.toFixed(0));
function ticks(lo, hi, n = 4) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const step = (hi - lo) / n;
  return Array.from({ length: n + 1 }, (_, i) => lo + i * step);
}
function yAxis(s, lo, hi, y, h, fmt = nice) {
  ticks(lo, hi).forEach((v) => {
    const yy = y(v);
    node(s, "line", { x1: M.l, x2: W - M.r, y1: yy, y2: yy, class: "grid" });
    node(s, "text", { x: M.l - 6, y: yy + 3, "text-anchor": "end", class: "tick" }, fmt(v));
  });
}

/* bars with optional secondary 0..100 line (e.g. win rate) */
export function bars(el, labels, values, { secondary = null, secLabel = "Win rate", fmt = (v) => v.toFixed(2) + "%", h = H } = {}) {
  const s = svg(el, h);
  if (!values.length) return;
  const lo = Math.min(0, ...values), hi = Math.max(0, ...values);
  const ih = h - M.t - M.b, iw = W - M.l - M.r;
  const y = (v) => M.t + ih - ((v - lo) / (hi - lo || 1)) * ih;
  yAxis(s, lo, hi, y, h, (v) => nice(v));
  const bw = iw / values.length;
  values.forEach((v, i) => {
    const x = M.l + i * bw + bw * 0.15, y0 = y(0), y1 = y(v);
    const r = node(s, "rect", { x, y: Math.min(y0, y1), width: bw * 0.7, height: Math.max(Math.abs(y1 - y0), 1), fill: v >= 0 ? GREEN : RED, rx: 2 });
    node(r, "title", {}, `${labels[i]}: ${fmt(v)}`);
    const rot = labels.length > 10;
    node(s, "text", { x: x + bw * 0.35, y: h - M.b + 14, "text-anchor": rot ? "end" : "middle", class: "tick",
      transform: rot ? `rotate(-40 ${x + bw * 0.35} ${h - M.b + 14})` : "" }, labels[i]);
  });
  node(s, "line", { x1: M.l, x2: W - M.r, y1: y(0), y2: y(0), class: "zero" });
  if (secondary) {
    const ys = (v) => M.t + ih - (v / 100) * ih;
    const pts = secondary.map((v, i) => v === null ? null : [M.l + i * bw + bw / 2, ys(v)]).filter(Boolean);
    node(s, "polyline", { points: pts.map((p) => p.join(",")).join(" "), fill: "none", stroke: BLUE, "stroke-width": 1.6 });
    pts.forEach((p, j) => node(node(s, "circle", { cx: p[0], cy: p[1], r: 3, fill: BLUE }), "title", {}, `${secLabel}: ${secondary[j]?.toFixed(1)}%`));
    node(s, "text", { x: W - M.r, y: M.t + 2, "text-anchor": "end", class: "tick", fill: BLUE }, `● ${secLabel} (0–100%)`);
  }
}

export function histogram(el, edges, counts) {
  const s = svg(el);
  if (!counts.length) return;
  const ih = H - M.t - M.b, iw = W - M.l - M.r, mx = Math.max(...counts);
  const lo = edges[0], hi = edges[edges.length - 1];
  const x = (v) => M.l + ((v - lo) / (hi - lo || 1)) * iw;
  const y = (v) => M.t + ih - (v / (mx || 1)) * ih;
  yAxis(s, 0, mx, y, H, (v) => v.toFixed(0));
  counts.forEach((c, i) => {
    const a = edges[i], b = edges[i + 1], mid = (a + b) / 2;
    const r = node(s, "rect", { x: x(a) + 0.5, y: y(c), width: Math.max(x(b) - x(a) - 1, 1), height: M.t + ih - y(c), fill: mid >= 0 ? GREEN : RED, opacity: 0.85 });
    node(r, "title", {}, `${a.toFixed(2)}% → ${b.toFixed(2)}%: ${c} trades`);
  });
  ticks(lo, hi, 6).forEach((v) => node(s, "text", { x: x(v), y: H - M.b + 14, "text-anchor": "middle", class: "tick" }, v.toFixed(1) + "%"));
  if (lo < 0 && hi > 0) node(s, "line", { x1: x(0), x2: x(0), y1: M.t, y2: M.t + ih, class: "zero" });
  node(s, "text", { x: W / 2, y: H - 6, "text-anchor": "middle", class: "axis" }, "Trade return");
}

export function scatter(el, xs, ys, { xLabel = "", yLabel = "", colorBy = null, diag = false } = {}) {
  const s = svg(el);
  if (!xs.length) return;
  const ih = H - M.t - M.b, iw = W - M.l - M.r;
  let xlo = Math.min(...xs), xhi = Math.max(...xs), ylo = Math.min(...ys), yhi = Math.max(...ys);
  if (xlo === xhi) { xlo -= 1; xhi += 1; } if (ylo === yhi) { ylo -= 1; yhi += 1; }
  const x = (v) => M.l + ((v - xlo) / (xhi - xlo)) * iw, y = (v) => M.t + ih - ((v - ylo) / (yhi - ylo)) * ih;
  yAxis(s, ylo, yhi, y, H);
  ticks(xlo, xhi, 5).forEach((v) => node(s, "text", { x: x(v), y: H - M.b + 14, "text-anchor": "middle", class: "tick" }, nice(v)));
  if (ylo < 0 && yhi > 0) node(s, "line", { x1: M.l, x2: W - M.r, y1: y(0), y2: y(0), class: "zero" });
  if (xlo < 0 && xhi > 0) node(s, "line", { x1: x(0), x2: x(0), y1: M.t, y2: M.t + ih, class: "zero" });
  if (diag) {
    const a = Math.max(xlo, ylo), b = Math.min(xhi, yhi);
    if (b > a) node(s, "line", { x1: x(a), y1: y(a), x2: x(b), y2: y(b), stroke: GREY, "stroke-dasharray": "4 3" });
  }
  xs.forEach((v, i) => {
    const c = (colorBy ? colorBy[i] : ys[i]) > 0 ? GREEN : RED;
    node(node(s, "circle", { cx: x(v), cy: y(ys[i]), r: 3.2, fill: c, opacity: 0.7 }), "title", {}, `${xLabel} ${v.toFixed(2)} · ${yLabel} ${ys[i].toFixed(2)}`);
  });
  node(s, "text", { x: W / 2, y: H - 6, "text-anchor": "middle", class: "axis" }, xLabel);
  node(s, "text", { x: 12, y: H / 2, "text-anchor": "middle", class: "axis", transform: `rotate(-90 12 ${H / 2})` }, yLabel);
}

export function lines(el, series, { xLabel = "", yFmt = nice, zero = false } = {}) {
  const s = svg(el);
  const all = series.flatMap((sr) => sr.values.filter((v) => v !== null && Number.isFinite(v)));
  if (!all.length) return;
  const n = Math.max(...series.map((sr) => sr.values.length));
  const ih = H - M.t - M.b, iw = W - M.l - M.r;
  let lo = Math.min(...all), hi = Math.max(...all);
  if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  const x = (i) => M.l + (i / Math.max(n - 1, 1)) * iw, y = (v) => M.t + ih - ((v - lo) / (hi - lo || 1)) * ih;
  yAxis(s, lo, hi, y, H, yFmt);
  series.forEach((sr) => {
    let d = "", pen = false;
    sr.values.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
    });
    node(s, "path", { d, fill: "none", stroke: sr.color || BLUE, "stroke-width": sr.width || 1.6, "stroke-dasharray": sr.dashed ? "5 4" : "" });
  });
  series.forEach((sr, i) => node(s, "text", { x: M.l + 8 + i * 140, y: M.t + 4, class: "tick", fill: sr.color || BLUE }, `● ${sr.name}`));
  node(s, "text", { x: W / 2, y: H - 6, "text-anchor": "middle", class: "axis" }, xLabel);
}

export function heatColor(v, maxAbs) {
  if (v === null || v === undefined) return "transparent";
  const a = Math.min(Math.abs(v) / (maxAbs || 1), 1) * 0.75 + 0.08;
  return v >= 0 ? `rgba(8,153,129,${a})` : `rgba(242,54,69,${a})`;
}
