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

/* ---------------------------------------------------------------------
   Research-report charts (optimizer / universe)
   --------------------------------------------------------------------- */

/** colour for a value on a red → neutral → green scale. center = the "neutral" value (0, 1, 50 …) */
export function divColor(v, lo, hi, center = 0, alpha = 0.85) {
  if (v === null || v === undefined || !Number.isFinite(v)) return "transparent";
  let t;
  if (lo < center && hi > center) t = v >= center ? 0.5 + 0.5 * (v - center) / (hi - center || 1) : 0.5 - 0.5 * (center - v) / (center - lo || 1);
  else t = (v - lo) / (hi - lo || 1);
  t = Math.max(0, Math.min(1, t));
  // red (242,54,69) -> amber (255,193,7) -> green (8,153,129)
  const mix = (a, b, k) => Math.round(a + (b - a) * k);
  const [r, g, b] = t < 0.5
    ? [mix(242, 255, t * 2), mix(54, 193, t * 2), mix(69, 7, t * 2)]
    : [mix(255, 8, (t - 0.5) * 2), mix(193, 153, (t - 0.5) * 2), mix(7, 129, (t - 0.5) * 2)];
  return `rgba(${r},${g},${b},${alpha})`;
}

/** heat map: z[y][x]; labels shown if the grid is small enough. */
export function heatGrid(el, xLabels, yLabels, z, { fmt = (v) => v.toFixed(2), xTitle = "", yTitle = "", center = 0, highlight = null, onCell = null } = {}) {
  const nx = xLabels.length, ny = yLabels.length;
  const ml = 64, mb = 46, mt = 8, mr = 12;
  const cell = Math.max(10, Math.min(52, Math.floor((W - ml - mr) / Math.max(nx, 1))));
  const iw = cell * nx, ih = Math.max(9, Math.min(20, cell * 0.6)) * ny;
  const ch = ih / Math.max(ny, 1);
  const h = mt + ih + mb;
  el.innerHTML = "";
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("viewBox", `0 0 ${Math.max(W, ml + iw + mr)} ${h}`);
  s.setAttribute("class", "svgc");
  el.appendChild(s);
  const vals = z.flat().filter((v) => v !== null && Number.isFinite(v));
  const lo = vals.length ? Math.min(...vals) : 0, hi = vals.length ? Math.max(...vals) : 1;
  const showText = cell >= 30 && ch >= 13;
  for (let yi = 0; yi < ny; yi++) {
    for (let xi = 0; xi < nx; xi++) {
      const v = z[yi][xi];
      const x = ml + xi * cell, y = mt + (ny - 1 - yi) * ch;
      const r = node(s, "rect", { x: x + 0.5, y: y + 0.5, width: cell - 1, height: ch - 1, rx: 2,
        fill: v === null || !Number.isFinite(v) ? "var(--bg)" : divColor(v, lo, hi, center) });
      node(r, "title", {}, `${xTitle} ${xLabels[xi]} · ${yTitle} ${yLabels[yi]} → ${v === null || !Number.isFinite(v) ? "n/a" : fmt(v)}`);
      if (onCell) { r.style.cursor = "pointer"; r.addEventListener("click", () => onCell(xi, yi)); }
      if (showText && v !== null && Number.isFinite(v)) node(s, "text", { x: x + cell / 2, y: y + ch / 2 + 3.5, "text-anchor": "middle", class: "cellv" }, fmt(v));
      if (highlight && highlight[0] === xi && highlight[1] === yi) node(s, "rect", { x: x + 1, y: y + 1, width: cell - 2, height: ch - 2, fill: "none", stroke: "var(--strong)", "stroke-width": 2, rx: 2, "pointer-events": "none" });
    }
  }
  const every = Math.ceil(nx / 16);
  xLabels.forEach((l, i) => { if (i % every === 0) node(s, "text", { x: ml + i * cell + cell / 2, y: mt + ih + 14, "text-anchor": "middle", class: "tick" }, l); });
  const everyY = Math.ceil(ny / 14);
  yLabels.forEach((l, i) => { if (i % everyY === 0) node(s, "text", { x: ml - 6, y: mt + (ny - 1 - i) * ch + ch / 2 + 3, "text-anchor": "end", class: "tick" }, l); });
  node(s, "text", { x: ml + iw / 2, y: h - 8, "text-anchor": "middle", class: "axis" }, xTitle);
  node(s, "text", { x: 12, y: mt + ih / 2, "text-anchor": "middle", class: "axis", transform: `rotate(-90 12 ${mt + ih / 2})` }, yTitle);
  return { lo, hi };
}

/** lines over categorical x values (e.g. a parameter's tested values) */
export function catLines(el, labels, series, { xLabel = "", yFmt = nice, zero = false, mark = null } = {}) {
  const s = svg(el);
  const all = series.flatMap((sr) => sr.values.filter((v) => v !== null && Number.isFinite(v)));
  if (!all.length) return;
  const ih = H - M.t - M.b, iw = W - M.l - M.r, n = labels.length;
  let lo = Math.min(...all), hi = Math.max(...all);
  if (zero) { lo = Math.min(lo, 0); hi = Math.max(hi, 0); }
  const x = (i) => M.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw), y = (v) => M.t + ih - ((v - lo) / (hi - lo || 1)) * ih;
  yAxis(s, lo, hi, y, H, yFmt);
  if (lo < 0 && hi > 0) node(s, "line", { x1: M.l, x2: W - M.r, y1: y(0), y2: y(0), class: "zero" });
  if (mark !== null && mark >= 0) node(s, "line", { x1: x(mark), x2: x(mark), y1: M.t, y2: M.t + ih, stroke: "var(--accent)", "stroke-dasharray": "3 3" });
  series.forEach((sr) => {
    let d = "", pen = false;
    sr.values.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`; pen = true;
    });
    node(s, "path", { d, fill: "none", stroke: sr.color || BLUE, "stroke-width": sr.width || 1.8, "stroke-dasharray": sr.dashed ? "5 4" : "" });
    sr.values.forEach((v, i) => {
      if (v === null || !Number.isFinite(v)) return;
      node(node(s, "circle", { cx: x(i), cy: y(v), r: 2.6, fill: sr.color || BLUE }), "title", {}, `${labels[i]}: ${sr.name} ${yFmt(v)}`);
    });
  });
  const every = Math.ceil(n / 14);
  labels.forEach((l, i) => { if (i % every === 0) node(s, "text", { x: x(i), y: H - M.b + 14, "text-anchor": "middle", class: "tick" }, l); });
  series.forEach((sr, i) => node(s, "text", { x: W - M.r - (series.length - 1 - i) * 110, y: 10, "text-anchor": "end", class: "tick", fill: sr.color || BLUE }, `● ${sr.name}`));
  node(s, "text", { x: W / 2, y: H - 6, "text-anchor": "middle", class: "axis" }, xLabel);
}

/** horizontal bars, one row per item; rows: [{label, values:[a, b?], color}] */
export function hbars(el, rows, { names = [], fmt = (v) => v.toFixed(2), center = 0 } = {}) {
  el.innerHTML = "";
  if (!rows.length) return;
  const lw = 170, mr = 62, rowH = rows[0].values.length > 1 ? 30 : 24, mt = names.length ? 22 : 6, mb = 8;
  const h = mt + rows.length * rowH + mb;
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("viewBox", `0 0 ${W} ${h}`);
  s.setAttribute("class", "svgc");
  el.appendChild(s);
  const all = rows.flatMap((r) => r.values.filter((v) => v !== null && Number.isFinite(v)));
  const lo = Math.min(center, ...all), hi = Math.max(center, ...all);
  const iw = W - lw - mr;
  const x = (v) => lw + ((v - lo) / (hi - lo || 1)) * iw;
  node(s, "line", { x1: x(center), x2: x(center), y1: mt - 4, y2: h - mb, class: "zero" });
  rows.forEach((r, i) => {
    const y0 = mt + i * rowH;
    node(s, "text", { x: lw - 8, y: y0 + rowH / 2 + 3.5, "text-anchor": "end", class: "hbl" }, r.label.length > 24 ? r.label.slice(0, 23) + "…" : r.label);
    const k = r.values.length, bh = (rowH - 6) / k;
    r.values.forEach((v, j) => {
      if (v === null || !Number.isFinite(v)) return;
      const xa = x(Math.min(v, center)), xb = x(Math.max(v, center));
      const fill = j === 0 ? (r.color || (v >= center ? GREEN : RED)) : GREY;
      const rect = node(s, "rect", { x: xa, y: y0 + 3 + j * bh, width: Math.max(xb - xa, 1), height: bh - 1, fill, rx: 2, opacity: j === 0 ? 0.95 : 0.6 });
      node(rect, "title", {}, `${r.label}${names[j] ? " · " + names[j] : ""}: ${fmt(v)}`);
      // value label: right of the bar for positives; for negatives just right of the zero line (never over the row name)
      if (j === 0) node(s, "text", { x: v >= center ? xb + 4 : x(center) + 4, y: y0 + 3 + bh / 2 + 3.5, "text-anchor": "start", class: "hbv" }, fmt(v));
    });
  });
  names.forEach((nm, j) => node(s, "text", { x: lw + j * 120, y: 13, class: "hbv", fill: j === 0 ? "var(--text)" : GREY }, `${j === 0 ? "■" : "■"} ${nm}`));
}

/** scatter with labelled, coloured points: pts [{x, y, label, color, big}] */
export function labelScatter(el, pts, { xLabel = "", yLabel = "", xFmt = nice, yFmt = nice } = {}) {
  const s = svg(el, 300);
  const h = 300;
  pts = pts.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
  if (!pts.length) return;
  const ih = h - M.t - M.b, iw = W - M.l - M.r;
  let xlo = Math.min(...pts.map((p) => p.x)), xhi = Math.max(...pts.map((p) => p.x));
  let ylo = Math.min(...pts.map((p) => p.y)), yhi = Math.max(...pts.map((p) => p.y));
  const px = (xhi - xlo || 1) * 0.08, py = (yhi - ylo || 1) * 0.08;
  xlo -= px; xhi += px; ylo -= py; yhi += py;
  const x = (v) => M.l + ((v - xlo) / (xhi - xlo)) * iw, y = (v) => M.t + ih - ((v - ylo) / (yhi - ylo)) * ih;
  yAxis(s, ylo, yhi, y, h, yFmt);
  ticks(xlo, xhi, 5).forEach((v) => node(s, "text", { x: x(v), y: h - M.b + 14, "text-anchor": "middle", class: "tick" }, xFmt(v)));
  if (ylo < 0 && yhi > 0) node(s, "line", { x1: M.l, x2: W - M.r, y1: y(0), y2: y(0), class: "zero" });
  if (xlo < 0 && xhi > 0) node(s, "line", { x1: x(0), x2: x(0), y1: M.t, y2: M.t + ih, class: "zero" });
  pts.forEach((p) => {
    const c = node(s, "circle", { cx: x(p.x), cy: y(p.y), r: p.big ? 6 : 4.2, fill: p.color || BLUE, opacity: 0.85, stroke: p.big ? "var(--strong)" : "none", "stroke-width": 1.5 });
    node(c, "title", {}, `${p.label || ""} · ${xLabel} ${xFmt(p.x)} · ${yLabel} ${yFmt(p.y)}`);
    if (p.label && pts.length <= 40) node(s, "text", { x: x(p.x) + 7, y: y(p.y) + 3, class: "tick lbl" }, p.label.length > 18 ? p.label.slice(0, 17) + "…" : p.label);
  });
  node(s, "text", { x: W / 2, y: h - 6, "text-anchor": "middle", class: "axis" }, xLabel);
  node(s, "text", { x: 12, y: h / 2, "text-anchor": "middle", class: "axis", transform: `rotate(-90 12 ${h / 2})` }, yLabel);
}
