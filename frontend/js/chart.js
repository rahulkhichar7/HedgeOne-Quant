/* =====================================================================
   ChartStack — TradingView Lightweight Charts wrapper
   - main candlestick pane + any number of synced sub-panes
   - trade zones: dim green/red background for every trade + entry→exit box
   - markers for fills, optional raw-signal dots, crosshair-synced legend
   Used by both the terminal (index.html) and the report page.
   ===================================================================== */
const LWC = window.LightweightCharts;

export const PALETTE = ["#2962ff", "#ff9800", "#e040fb", "#00bcd4", "#ffd600", "#ff4081",
  "#8d6e63", "#66bb6a", "#7e57c2", "#26c6da", "#ef5350", "#9ccc65"];

const THEMES = {
  dark: {
    bg: "#131722", text: "#b2b5be", grid: "rgba(42,46,57,0.6)", border: "#2a2e39",
    up: "#089981", down: "#f23645", volUp: "rgba(8,153,129,0.22)", volDown: "rgba(242,54,69,0.22)",
    win: [8, 153, 129], loss: [242, 54, 69], label: "#d1d4dc", crosshair: "#758696",
  },
  light: {
    bg: "#ffffff", text: "#3a3e4a", grid: "rgba(220,224,232,0.7)", border: "#e0e3eb",
    up: "#089981", down: "#f23645", volUp: "rgba(8,153,129,0.3)", volDown: "rgba(242,54,69,0.3)",
    win: [8, 153, 129], loss: [242, 54, 69], label: "#131722", crosshair: "#9598a1",
  },
};

const pad = (n) => String(n).padStart(2, "0");
const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function fmtTime(t) {           // t = seconds; we store IST wall-clock as UTC
  const d = new Date(t * 1000);
  return `${pad(d.getUTCDate())} ${MON[d.getUTCMonth()]} '${String(d.getUTCFullYear()).slice(2)} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}
export function fmtNum(v, d = 2) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1e7) return (v / 1e7).toFixed(2) + " Cr";
  if (a >= 1e5) return (v / 1e5).toFixed(2) + " L";
  return v.toLocaleString("en-IN", { maximumFractionDigits: d, minimumFractionDigits: a < 10 ? d : Math.min(d, 2) });
}

/* ---------------------------------------------------------------------
   Trade zones primitive (drawn behind candles)
   --------------------------------------------------------------------- */
class TradeZones {
  constructor(theme) {
    this.trades = []; this.hover = -1; this.focus = -1; this.theme = theme; this.visible = true;
    const self = this;
    this._renderer = { draw: (target) => self._draw(target) };
    this._view = { zOrder: () => "bottom", renderer: () => self._renderer };
  }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
  detached() { this.chart = null; }
  updateAllViews() {}
  paneViews() { return [this._view]; }
  set(trades) { this.trades = trades || []; this.hover = this.focus = -1; this.requestUpdate && this.requestUpdate(); }
  setHover(i) { if (i !== this.hover) { this.hover = i; this.requestUpdate && this.requestUpdate(); } }
  setFocus(i) { this.focus = i; this.requestUpdate && this.requestUpdate(); }

  _draw(target) {
    if (!this.chart || !this.visible || !this.trades.length) return;
    const ts = this.chart.timeScale();
    const spacing = ts.options().barSpacing;
    const vr = ts.getVisibleLogicalRange();
    if (!vr) return;
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context, hr = scope.horizontalPixelRatio, vpr = scope.verticalPixelRatio;
      const H = scope.bitmapSize.height;
      const half = Math.max(spacing / 2, 1);
      ctx.save();
      ctx.font = `${Math.round(11 * vpr)}px -apple-system, Segoe UI, Roboto, sans-serif`;
      ctx.textBaseline = "bottom";
      this.trades.forEach((t, i) => {
        if (t.exit_idx < vr.from - 2 || t.entry_idx > vr.to + 2) return;
        const x1 = ts.logicalToCoordinate(t.entry_idx), x2 = ts.logicalToCoordinate(t.exit_idx);
        if (x1 === null || x2 === null) return;
        const win = t.pnl > 0, rgb = win ? this.theme.win : this.theme.loss;
        const strong = i === this.hover || i === this.focus;
        const L = Math.round((x1 - half) * hr), R = Math.round((x2 + (t.live ? 0 : half)) * hr);
        // 1) full-height dim band
        ctx.fillStyle = `rgba(${rgb},${strong ? 0.13 : 0.06})`;
        ctx.fillRect(L, 0, Math.max(R - L, 1), H);
        // 2) box between entry and exit price
        const y1 = this.series.priceToCoordinate(t.entry_price), y2 = this.series.priceToCoordinate(t.exit_price);
        if (y1 === null || y2 === null) return;
        const T = Math.round(Math.min(y1, y2) * vpr), B = Math.round(Math.max(y1, y2) * vpr);
        ctx.fillStyle = `rgba(${rgb},${strong ? 0.32 : 0.18})`;
        ctx.fillRect(L, T, Math.max(R - L, 1), Math.max(B - T, 1));
        if (t.manual) {                      // practice trades: blue outline
          ctx.strokeStyle = "rgba(41,98,255,0.95)"; ctx.lineWidth = Math.max(1, Math.round(1.5 * hr));
          ctx.strokeRect(L, T, Math.max(R - L, 1), Math.max(B - T, 1));
        }
        if (t.live) {                        // still-open trade: pulsing right edge
          ctx.fillStyle = `rgba(${rgb},0.9)`;
          ctx.fillRect(R - Math.round(2 * hr), T, Math.round(2 * hr), Math.max(B - T, 1));
        }
        // entry price line (dashed) + exit edge
        ctx.strokeStyle = `rgba(${rgb},0.9)`;
        ctx.lineWidth = Math.max(1, Math.round(hr));
        ctx.setLineDash([4 * hr, 3 * hr]);
        ctx.beginPath(); ctx.moveTo(L, Math.round(y1 * vpr)); ctx.lineTo(R, Math.round(y1 * vpr)); ctx.stroke();
        ctx.setLineDash([]);
        // 3) label
        if ((R - L) / hr > 44 || strong) {
          const txt = `${t.manual ? "You " : ""}${t.live ? "open " : ""}${t.return_pct >= 0 ? "+" : ""}${t.return_pct.toFixed(2)}%`;
          ctx.fillStyle = `rgba(${rgb},1)`;
          ctx.fillText(txt, L + 3 * hr, T - 2 * vpr);
        }
      });
      ctx.restore();
    });
  }
}

/* ---------------------------------------------------------------------
   ChartStack
   --------------------------------------------------------------------- */
export class ChartStack {
  constructor(container, { theme = "dark", onTradeHover = null, legend = true } = {}) {
    this.root = container;
    this.root.classList.add("chart-stack");
    this.th = THEMES[theme];
    this.themeName = theme;
    this.panes = [];                 // [{id, el, chart, series:[], group}]
    this.groups = {};                // group -> [{pane, series}]
    this.times = [];
    this.timeIndex = new Map();
    this.trades = [];
    this.onTradeHover = onTradeHover;
    this._syncing = false;
    this.showSignals = false;
    this.limit = null;               // replay window: {n: complete bars shown, forming: {o,h,l,c,v} | null}
    this.main = this._makePane("main", "Price", true);
    this.candles = this.main.chart.addCandlestickSeries({
      upColor: this.th.up, downColor: this.th.down, borderUpColor: this.th.up, borderDownColor: this.th.down,
      wickUpColor: this.th.up, wickDownColor: this.th.down, priceLineVisible: true,
    });
    this.volume = this.main.chart.addHistogramSeries({
      priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false,
    });
    this.main.chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.86, bottom: 0 } });
    this.zones = new TradeZones(this.th);
    this.candles.attachPrimitive(this.zones);
    this.main.series.push(this.candles);
    if (legend) this._legend();
    this.main.chart.subscribeCrosshairMove((p) => this._onCrosshair(p, this.main));
  }

  /* ---------- panes ---------- */
  _chartOptions(isMain) {
    const th = this.th;
    return {
      autoSize: true,
      layout: { background: { type: "solid", color: th.bg }, textColor: th.text, fontSize: 11,
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif" },
      grid: { vertLines: { color: th.grid }, horzLines: { color: th.grid } },
      rightPriceScale: { borderColor: th.border, minimumWidth: 72, scaleMargins: isMain ? { top: 0.08, bottom: 0.2 } : { top: 0.12, bottom: 0.08 } },
      timeScale: { borderColor: th.border, timeVisible: true, secondsVisible: false, rightOffset: 8,
        visible: isMain, minBarSpacing: 0.2 },
      crosshair: { mode: LWC.CrosshairMode.Normal,
        vertLine: { color: th.crosshair, labelBackgroundColor: "#363a45" },
        horzLine: { color: th.crosshair, labelBackgroundColor: "#363a45" } },
      localization: { timeFormatter: (t) => fmtTime(t) },
      handleScale: { axisPressedMouseMove: { time: true, price: true } },
    };
  }

  _makePane(id, title, isMain = false, height = 150) {
    const el = document.createElement("div");
    el.className = "pane" + (isMain ? " pane-main" : "");
    if (!isMain) el.style.height = height + "px";
    const head = document.createElement("div");
    head.className = "pane-head";
    head.innerHTML = `<span class="pane-title">${title}</span><span class="pane-values"></span>`;
    el.appendChild(head);
    if (!isMain) {
      const x = document.createElement("button");
      x.className = "pane-close"; x.title = "Close pane"; x.textContent = "×";
      x.onclick = () => this.removePane(id);
      head.appendChild(x);
      const grip = document.createElement("div");
      grip.className = "pane-grip"; el.appendChild(grip);
      this._resizable(el, grip);
    }
    this.root.appendChild(el);
    const chart = LWC.createChart(el, this._chartOptions(isMain));
    const pane = { id, el, chart, series: [], title, head };
    this.panes.push(pane);
    // sync logical range
    chart.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (isMain && r) {
        const compact = (r.to - r.from) > 600;
        if (compact !== this._compact) { this._compact = compact; if (this.trades && this.trades.length) this._markers(); }
      }
      if (this._syncing || !r) return;
      this._syncing = true;
      this.panes.forEach((p) => p !== pane && p.chart.timeScale().setVisibleLogicalRange(r));
      this._syncing = false;
    });
    if (!isMain) {
      chart.subscribeCrosshairMove((p) => this._onCrosshair(p, pane));
      const r = this.main && this.main.chart.timeScale().getVisibleLogicalRange();
      if (r) chart.timeScale().setVisibleLogicalRange(r);
      // only the bottom pane shows the time axis
      this.panes.forEach((p) => p.chart.applyOptions({ timeScale: { visible: false } }));
      chart.applyOptions({ timeScale: { visible: true } });
    }
    return pane;
  }

  _resizable(el, grip) {
    grip.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const y0 = e.clientY, h0 = el.offsetHeight;
      const move = (ev) => { el.style.height = Math.max(60, h0 + (ev.clientY - y0)) + "px"; };
      const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
      document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
    });
  }

  pane(id, title, height) {
    return this.panes.find((p) => p.id === id) || this._makePane(id, title, false, height);
  }

  removePane(id) {
    const i = this.panes.findIndex((p) => p.id === id);
    if (i <= 0) return;
    const p = this.panes[i];
    p.chart.remove(); p.el.remove();
    this.panes.splice(i, 1);
    for (const g of Object.keys(this.groups)) this.groups[g] = this.groups[g].filter((x) => x.pane !== p);
    const last = this.panes[this.panes.length - 1];
    last.chart.applyOptions({ timeScale: { visible: true } });
    this.onPaneClosed && this.onPaneClosed(id);
  }

  /* ---------- data ---------- */
  // Every series stores its FULL value array (s._values). What is drawn is always
  // limited to the replay window when one is set, so future bars are never rendered.
  _count() { return this.limit ? Math.min(this.limit.n, this.times.length) : this.times.length; }
  lastIndex() { return this.limit && this.limit.forming ? this._count() : this._count() - 1; }

  _candlePt(i) {
    const c = this.ohlc, f = this.limit && this.limit.forming && i === this._count() ? this.limit.forming : null;
    return f ? { time: c.t[i], open: f.o, high: f.h, low: f.l, close: f.c }
      : { time: c.t[i], open: c.o[i], high: c.h[i], low: c.l[i], close: c.c[i] };
  }
  _volPt(i) {
    const c = this.ohlc, f = this.limit && this.limit.forming && i === this._count() ? this.limit.forming : null;
    const o = f ? f.o : c.o[i], cl = f ? f.c : c.c[i], v = f ? f.v : c.v[i];
    return { time: c.t[i], value: v || 0, color: cl >= o ? this.th.volUp : this.th.volDown };
  }
  _pt(s, i) {
    const t = this.times[i];
    if (this.limit && i >= this._count()) return { time: t };        // forming bar: value not known yet
    const v = s._values[i];
    if (v === null || v === undefined) return { time: t };
    if (s._kind === "hist") return { time: t, value: v, color: v >= 0 ? this.th.volUp : this.th.volDown };
    return { time: t, value: v };
  }
  _pts(s) {
    const n = this._count() + (this.limit && this.limit.forming && this._count() < this.times.length ? 1 : 0);
    const out = new Array(n);
    for (let i = 0; i < n; i++) out[i] = this._pt(s, i);
    return out;
  }
  _allSeries() { return Object.values(this.groups).flat().map((g) => g.series); }

  _renderAll() {
    if (!this.ohlc) return;
    const n = this._count() + (this.limit && this.limit.forming && this._count() < this.times.length ? 1 : 0);
    const bars = new Array(n), vols = new Array(n);
    for (let i = 0; i < n; i++) { bars[i] = this._candlePt(i); vols[i] = this._volPt(i); }
    this.candles.setData(bars);
    this.volume.setData(vols);
    this._allSeries().forEach((s) => s.setData(this._pts(s)));
  }

  setCandles(c) {
    const keep = this.times.length && c.t.length && this.times[0] === c.t[0] && this.times.length === c.t.length;
    this.times = c.t;
    this.timeIndex = new Map(c.t.map((t, i) => [t, i]));
    this.ohlc = c;
    const n = this._count() + (this.limit && this.limit.forming ? 1 : 0);
    const bars = new Array(n), vols = new Array(n);
    for (let i = 0; i < n; i++) { bars[i] = this._candlePt(i); vols[i] = this._volPt(i); }
    this.candles.setData(bars);
    this.volume.setData(vols);
    const p = c.c.find((x) => x !== null) || 1;
    const prec = p < 1 ? 5 : p < 10 ? 4 : 2;
    this.candles.applyOptions({ priceFormat: { type: "price", precision: prec, minMove: 1 / 10 ** prec } });
    if (!keep && !this.limit) {
      this.main.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 300), to: n + 5 });
    }
    this._updateLegend(this.lastIndex());
  }

  /** Replay: show only the first `n` complete bars (+ an optional forming bar at index n). */
  setLimit(n, forming = null) {
    n = Math.max(1, Math.min(n, this.times.length));
    if (n >= this.times.length) forming = null;
    const prev = this.limit;
    this.limit = { n, forming };
    const incremental = prev && n >= prev.n && n - prev.n <= 25 && this.ohlc;
    if (!incremental) { this._renderAll(); }
    else {
      const series = this._allSeries();
      for (let i = prev.n; i < n; i++) {           // newly completed bars (also replaces old forming bar)
        this.candles.update(this._candlePt(i)); this.volume.update(this._volPt(i));
        series.forEach((s) => s.update(this._pt(s, i)));
      }
      if (forming) {
        this.candles.update(this._candlePt(n)); this.volume.update(this._volPt(n));
        series.forEach((s) => s.update(this._pt(s, n)));
      } else if (prev.forming && prev.n === n) {
        this._renderAll();                           // forming bar removed (stepped back) -> rebuild
      }
    }
    this._markers();
    this._updateLegend(this.lastIndex());
  }

  clearLimit() {
    this.limit = null;
    this._renderAll();
    this._markers();
    this._updateLegend(this.times.length - 1);
  }

  _register(group, paneObj, s, name, values, color, kind) {
    s._name = name; s._values = values; s._color = color; s._kind = kind;
    s.setData(this._pts(s));
    if (paneObj === this.main) this.main.series.push(s); else paneObj.series.push(s);
    (this.groups[group] = this.groups[group] || []).push({ pane: paneObj, series: s });
    return s;
  }

  addLine(group, paneObj, name, values, opts = {}) {
    const s = paneObj.chart.addLineSeries({
      color: opts.color || PALETTE[0], lineWidth: opts.width || 1.5, priceLineVisible: false,
      lastValueVisible: opts.lastValue !== false, title: "", crosshairMarkerRadius: 3,
      lineStyle: opts.dashed ? LWC.LineStyle.Dashed : LWC.LineStyle.Solid,
      ...(opts.priceScaleId ? { priceScaleId: opts.priceScaleId } : {}),
    });
    return this._register(group, paneObj, s, name, values, opts.color || PALETTE[0], "line");
  }

  addHistogram(group, paneObj, name, values, opts = {}) {
    const s = paneObj.chart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
    return this._register(group, paneObj, s, name, values, opts.color || "#787b86", "hist");
  }

  addBaseline(group, paneObj, name, values) {
    const s = paneObj.chart.addBaselineSeries({
      baseValue: { type: "price", price: 0 }, priceLineVisible: false, lastValueVisible: true,
      topLineColor: "rgba(0,0,0,0)", topFillColor1: "rgba(0,0,0,0)", topFillColor2: "rgba(0,0,0,0)",
      bottomLineColor: this.th.down, bottomFillColor1: "rgba(242,54,69,0.05)", bottomFillColor2: "rgba(242,54,69,0.35)",
      lineWidth: 1,
    });
    return this._register(group, paneObj, s, name, values, this.th.down, "baseline");
  }

  /** replace the values of an existing series (by group + name) without recreating it */
  updateValues(group, name, values) {
    const g = (this.groups[group] || []).find((x) => x.series._name === name);
    if (!g) return false;
    g.series._values = values;
    g.series.setData(this._pts(g.series));
    return true;
  }

  addLevels(paneObj, levels) {
    const target = paneObj.series[0];
    if (!target) return;
    (levels || []).forEach((lv) => target.createPriceLine({
      price: lv, color: "rgba(120,123,134,0.7)", lineWidth: 1, lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: "",
    }));
  }

  clearGroup(group) {
    (this.groups[group] || []).forEach(({ pane, series }) => {
      try { pane.chart.removeSeries(series); } catch (e) { /* already gone */ }
      pane.series = pane.series.filter((s) => s !== series);
      if (pane === this.main) this.main.series = this.main.series.filter((s) => s !== series);
    });
    delete this.groups[group];
    // drop empty sub-panes
    [...this.panes].forEach((p) => { if (p !== this.main && p.series.length === 0) this.removePane(p.id); });
  }

  /* ---------- strategy output ---------- */
  setTrades(trades, signals) {
    this.trades = trades || [];
    this.zones.set(this.trades);
    this._signals = signals;
    this._markers();
  }

  setShowSignals(on) { this.showSignals = on; this._markers(); }
  setZonesVisible(on) { this.zones.visible = on; this.zones.requestUpdate && this.zones.requestUpdate(); }

  _markers() {
    const th = this.th, m = [], many = this._compact || this.trades.length > 350;
    for (const t of this.trades) {
      const long = t.direction === "Long", win = t.pnl > 0;
      m.push({ time: this.times[t.entry_idx], position: long ? "belowBar" : "aboveBar",
        shape: long ? "arrowUp" : "arrowDown", color: t.manual ? "#2962ff" : long ? th.up : th.down,
        text: many ? "" : (t.manual ? (long ? "You buy" : "You sell") : (long ? "Buy" : "Short")) });
      if (t.status === "Closed" && !t.live)
        m.push({ time: this.times[t.exit_idx], position: long ? "aboveBar" : "belowBar", shape: "circle", size: 0.6,
          color: win ? th.up : th.down, text: many ? "" : `${t.return_pct >= 0 ? "+" : ""}${t.return_pct.toFixed(1)}%` });
    }
    if (this.showSignals && this._signals) {
      const lim = this._count();
      const add = (arr, pos, color, txt) => arr.forEach((i) => i < lim && this.times[i] &&
        m.push({ time: this.times[i], position: pos, shape: "square", size: 0.4, color, text: txt }));
      add(this._signals.long_entry, "belowBar", "#b388ff", "");
      add(this._signals.long_exit, "aboveBar", "#ffb74d", "");
      add(this._signals.short_entry, "aboveBar", "#b388ff", "");
      add(this._signals.short_exit, "belowBar", "#ffb74d", "");
    }
    m.sort((a, b) => a.time - b.time);
    this.candles.setMarkers(m.filter((x) => x.time !== undefined));
  }

  focusTrade(i) {
    const t = this.trades[i];
    if (!t) return;
    const span = Math.max(t.exit_idx - t.entry_idx, 10);
    this.main.chart.timeScale().setVisibleLogicalRange({ from: t.entry_idx - span * 1.5, to: t.exit_idx + span * 1.5 });
    this.zones.setFocus(i);
  }

  /* ---------- legend / crosshair ---------- */
  _legend() {
    this.legendEl = document.createElement("div");
    this.legendEl.className = "legend";
    this.main.el.appendChild(this.legendEl);
  }

  _idxAt(p) {
    if (!p || p.time === undefined) return null;
    const i = this.timeIndex.get(p.time);
    return i === undefined ? null : i;
  }

  _onCrosshair(p, src) {
    const i = this._idxAt(p);
    // sync crosshair to other panes
    this.panes.forEach((pane) => {
      if (pane === src) return;
      const s = pane.series[0];
      if (!s) return;
      if (i === null) { pane.chart.clearCrosshairPosition(); return; }
      const v = this.limit && i >= this._count() ? null : pane === this.main ? this.ohlc.c[i] : (s._values ? s._values[i] : null);
      try { pane.chart.setCrosshairPosition(v ?? 0, this.times[i], s); }
      catch (e) { pane.chart.clearCrosshairPosition(); }        // no point at that time in this pane
    });
    this._updateLegend(i === null ? this.lastIndex() : i);
    // hovered trade
    let hit = -1;
    if (i !== null && this.trades.length) {
      for (let k = this.trades.length - 1; k >= 0; k--) {
        const t = this.trades[k];
        if (i >= t.entry_idx && i <= t.exit_idx) { hit = k; break; }
      }
    }
    this.zones.setHover(hit);
    this.onTradeHover && this.onTradeHover(hit >= 0 ? this.trades[hit] : null, p);
  }

  _updateLegend(i) {
    if (!this.ohlc || i < 0 || i >= this.times.length) return;
    if (this.limit && i > this.lastIndex()) i = this.lastIndex();
    const known = (k) => !this.limit || k < this._count();
    const f = this.limit && this.limit.forming && i === this._count() ? this.limit.forming : null;
    const c = f ? { o: { [i]: f.o }, h: { [i]: f.h }, l: { [i]: f.l }, c: { [i]: f.c }, v: { [i]: f.v } } : this.ohlc;
    const ch = c.c[i] - c.o[i], cls = ch >= 0 ? "up" : "down";
    const pct = c.o[i] ? (ch / c.o[i]) * 100 : 0;
    const val = (s) => (known(i) ? s._values[i] : null);
    if (this.legendEl) {
      let html = `<div class="lg-row"><span class="lg-sym">${this.symbolLabel || ""}</span>` +
        `<span>O <b class="${cls}">${fmtNum(c.o[i])}</b></span><span>H <b class="${cls}">${fmtNum(c.h[i])}</b></span>` +
        `<span>L <b class="${cls}">${fmtNum(c.l[i])}</b></span><span>C <b class="${cls}">${fmtNum(c.c[i])}</b></span>` +
        `<span class="${cls}">${ch >= 0 ? "+" : ""}${fmtNum(ch)} (${pct.toFixed(2)}%)</span>` +
        `<span class="muted">Vol ${fmtNum(c.v[i], 0)}</span></div>`;
      const lines = this.main.series.filter((s) => s._name);
      if (lines.length) html += `<div class="lg-row">` + lines.map((s) =>
        `<span><i style="background:${s._color}"></i>${s._name} <b>${fmtNum(val(s))}</b></span>`).join("") + `</div>`;
      this.legendEl.innerHTML = html;
    }
    this.panes.forEach((pane) => {
      if (pane === this.main) return;
      const el = pane.head.querySelector(".pane-values");
      el.innerHTML = pane.series.filter((s) => s._name).map((s) =>
        `<span><i style="background:${s._color}"></i>${s._name} <b>${fmtNum(val(s))}</b></span>`).join("");
    });
  }

  fit() { this.main.chart.timeScale().fitContent(); }

  /** keep the newest replay bar in view near the right edge */
  scrollToCursor(force = false) {
    const ts = this.main.chart.timeScale(), r = ts.getVisibleLogicalRange(), last = this.lastIndex();
    if (!r) return;
    const width = r.to - r.from;
    if (force || last > r.to - 3 || last < r.from) ts.setVisibleLogicalRange({ from: last - width * 0.8, to: last + width * 0.2 });
  }
}
