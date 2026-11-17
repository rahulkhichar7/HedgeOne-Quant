/* =====================================================================
   Bar Replay (TradingView-style)
   - pick a start bar, then play / step / scrub forward like a live market
   - "Bar" steps whole candles; "Intrabar" builds the current candle from
     finer stored data (open → high/low → close, volume accumulating)
   - strategies + indicators are drawn ONLY up to the cursor; the backend's
     look-ahead check decides when a strategy must be recomputed per bar
   - practice trading: Buy / Sell / Close at the current price
   ===================================================================== */
import { fmtNum, fmtTime } from "./chart.js";
import { $, esc, toast } from "./ui.js";

const SPEEDS = [0.5, 1, 2, 3, 5, 10, 20, 50, 100];
const OPEN_FILL_REASONS = new Set(["Signal", "Reversal"]);

export function tsToStr(t) {           // chart seconds (IST wall-clock as UTC) -> "YYYY-MM-DD HH:MM:SS"
  return new Date(t * 1000).toISOString().slice(0, 19).replace("T", " ");
}

export class Replay {
  /**
   * @param chart ChartStack
   * @param api   api module
   * @param hooks { request(), drawStrategy(part), drawIndicators(list), clearLayers(), onExit(), feePct() }
   */
  constructor(chart, api, hooks) {
    this.chart = chart; this.api = api; this.h = hooks;
    this.active = false; this.selecting = false; this.playing = false;
    this.data = null; this.n = 0; this.subPos = 0; this.mode = "bar"; this.speed = 5;
    this.pauseOnTrade = true; this.trades = []; this.exact = { strategy: false, indicators: [] };
    this.manual = []; this.pos = null; this._seq = 0; this._inflight = false; this._pending = false;
    this._load();
    this._buildUI();
    chart.main.chart.subscribeClick((p) => this._onClick(p));
    chart.main.chart.subscribeCrosshairMove((p) => this._onMove(p));
    document.addEventListener("keydown", (e) => this._onKey(e));
  }

  /* ------------------------------------------------------------ prefs */
  _load() {
    try {
      const p = JSON.parse(localStorage.getItem("h1-replay") || "{}");
      if (p.speed) this.speed = p.speed;
      if (p.mode) this.mode = p.mode;
      if (p.pauseOnTrade !== undefined) this.pauseOnTrade = p.pauseOnTrade;
    } catch (e) { /* ignore */ }
  }
  _save() {
    try { localStorage.setItem("h1-replay", JSON.stringify({ speed: this.speed, mode: this.mode, pauseOnTrade: this.pauseOnTrade })); } catch (e) { /* ignore */ }
  }

  /* ------------------------------------------------------------ UI */
  _buildUI() {
    const host = this.chart.main.el;
    this.shade = document.createElement("div");
    this.shade.className = "rp-shade hidden";
    host.appendChild(this.shade);

    this.banner = document.createElement("div");
    this.banner.className = "rp-banner hidden";
    this.banner.innerHTML = `
      <b>Bar replay</b><span>Click a candle to start from there</span>
      <span class="muted">or</span><input type="datetime-local" id="rpDate">
      <button class="btn sm" id="rpGoDate">Go</button>
      <button class="btn sm" id="rpRandom" title="Random bar">🎲 Random</button>
      <button class="btn ghost sm" id="rpCancel">Cancel</button>`;
    host.appendChild(this.banner);

    this.bar = document.createElement("div");
    this.bar.className = "rp-bar hidden";
    this.bar.innerHTML = `
      <div class="rp-row">
        <button class="rp-b" id="rpPick" title="Pick a new start bar">⤺</button>
        <button class="rp-b" id="rpBack" title="Step back (←)">⏴</button>
        <button class="rp-b rp-play" id="rpPlay" title="Play / pause (Space)">▶</button>
        <button class="rp-b" id="rpFwd" title="Step forward (→, Shift+→ = 10)">⏵</button>
        <select id="rpSpeed" title="Speed (steps per second)">${SPEEDS.map((s) => `<option value="${s}" ${s === this.speed ? "selected" : ""}>${s}×/s</option>`).join("")}</select>
        <div class="seg mini" id="rpMode">
          <button data-m="bar">Bar</button><button data-m="intrabar" id="rpIntra">Intrabar</button>
        </div>
        <label class="toggle" title="Pause automatically when the strategy opens or closes a trade"><input type="checkbox" id="rpPause"><span>Pause on trade</span></label>
        <input type="range" id="rpSlider" min="1" max="2" value="1" title="Scrub">
        <span class="rp-time" id="rpTime"></span>
        <span class="rp-badge" id="rpBadge"></span>
        <button class="rp-b rp-x" id="rpExit" title="Exit replay (Esc)">✕</button>
      </div>
      <div class="rp-row rp-row2">
        <span class="rp-lbl">Practice</span>
        <button class="btn sm rp-buy" id="rpBuy" title="Buy at current price (B)">Buy</button>
        <button class="btn sm rp-sell" id="rpSell" title="Sell / short at current price (S)">Sell</button>
        <button class="btn sm" id="rpFlat" title="Close position (C)">Close</button>
        <span id="rpPos" class="rp-stat"></span>
        <span class="spacer"></span>
        <span id="rpStrat" class="rp-stat"></span>
      </div>`;
    host.appendChild(this.bar);

    const q = (id) => this.bar.querySelector("#" + id) || this.banner.querySelector("#" + id);
    this.el = { play: q("rpPlay"), speed: q("rpSpeed"), slider: q("rpSlider"), time: q("rpTime"), badge: q("rpBadge"),
      pos: q("rpPos"), strat: q("rpStrat"), pause: q("rpPause"), intra: q("rpIntra"), date: q("rpDate") };
    q("rpPick").onclick = () => this.pick();
    q("rpBack").onclick = () => { this.pausePlay(); this.back(); };
    q("rpFwd").onclick = () => { this.pausePlay(); this.forward(1); };
    this.el.play.onclick = () => this.toggle();
    this.el.speed.onchange = (e) => { this.speed = +e.target.value; this._save(); };
    this.el.pause.checked = this.pauseOnTrade;
    this.el.pause.onchange = (e) => { this.pauseOnTrade = e.target.checked; this._save(); };
    this.bar.querySelectorAll("#rpMode button").forEach((b) => b.onclick = () => this.setMode(b.dataset.m));
    this.el.slider.oninput = (e) => { this.pausePlay(); this.jump(+e.target.value); };
    q("rpExit").onclick = () => this.exit();
    q("rpBuy").onclick = () => this.trade(1);
    q("rpSell").onclick = () => this.trade(-1);
    q("rpFlat").onclick = () => this.flat();
    q("rpCancel").onclick = () => { this.selecting = false; this.banner.classList.add("hidden"); this.shade.classList.add("hidden"); if (!this.active) this.h.onExit(); };
    q("rpRandom").onclick = () => { const N = this.chart.times.length; this._startAt(Math.floor(N * 0.2 + Math.random() * N * 0.7)); };
    q("rpGoDate").onclick = () => {
      const v = this.el.date.value; if (!v) return;
      const t = Date.parse(v + ":00Z") / 1000;
      const i = this.chart.times.findIndex((x) => x >= t);
      this._startAt(i < 0 ? this.chart.times.length - 1 : i);
    };
  }

  _modeButtons() {
    this.bar.querySelectorAll("#rpMode button").forEach((b) => b.classList.toggle("active", b.dataset.m === this.mode));
    const sub = this.data && this.data.sub;
    this.el.intra.disabled = !sub;
    this.el.intra.title = sub ? `Build each candle from ${sub.interval} data` : "Needs finer stored data than the chart interval";
    this.el.intra.textContent = sub ? `Intrabar · ${sub.interval}` : "Intrabar";
  }

  /* ------------------------------------------------------------ enter / exit */
  /** Step 1: let the user pick the start bar on the full chart. */
  pick() {
    if (!this.chart.times.length) { toast("Load some candles first", "error"); return; }
    this.pausePlay();
    if (this.active) { this.chart.clearLimit(); }
    this.selecting = true;
    this.chart.setTrades([], null);
    this.banner.classList.remove("hidden");
    this.bar.classList.add("hidden");
    document.body.classList.add("replaying");
  }

  async _startAt(idx) {
    this.selecting = false;
    this.banner.classList.add("hidden"); this.shade.classList.add("hidden");
    await this.load(this.chart.times[Math.max(1, idx)]);
  }

  /** (Re)load replay data from the backend and put the cursor at time `t` (inclusive). */
  async load(t, { quiet = false } = {}) {
    const req = this.h.request();
    const seq = ++this._seq;
    let d;
    try {
      this.h.busy && this.h.busy(true, "Preparing replay…");
      d = await this.api.replayPrepare({ ...req, intrabar: true });
    } catch (e) { toast("Replay: " + e.message, "error", false, 8000); return; }
    finally { this.h.busy && this.h.busy(false); }
    if (seq !== this._seq) return;
    this.data = d;
    this.active = true;
    document.body.classList.add("replaying");
    this.bar.classList.remove("hidden");
    const N = d.candles.t.length;
    let i = d.candles.t.findIndex((x) => x > t);
    this.n = Math.max(1, i < 0 ? N : i);       // bars [0, n) visible
    this.subPos = 0;
    this._index();
    // exact mode for anything that failed the look-ahead check
    const c = d.causal || {};
    this.exact.strategy = !!(c.strategy && !c.strategy.ok);
    this.exact.indicators = Object.entries(c.indicators || {}).filter(([, v]) => !v.ok).map(([k]) => k);
    this.trades = d.strategy && !this.exact.strategy ? d.strategy.trades : [];
    this.execution = d.strategy ? d.strategy.execution : "next_open";
    this.pit = null;
    this._exactInit();
    if (this.mode === "intrabar" && !d.sub) this.mode = "bar";
    this._modeButtons();
    // draw: limit FIRST so nothing beyond the cursor is ever rendered
    this.chart.limit = { n: this.n, forming: null };
    this.h.clearLayers();
    this.chart.setCandles(d.candles);
    if (d.strategy) this.h.drawStrategy(this.exact.strategy ? this._exactPayload() : d.strategy);
    this.h.drawIndicators(d.indicators.map((r) => this.exact.indicators.includes(r.key) ? this._exactInd(r.key) : r));
    this.el.slider.max = N; this.el.slider.min = 1;
    this._badge();
    this.render(true);
    this.h.onLoaded && this.h.onLoaded(this);
    if (!quiet) {
      const flagged = [this.exact.strategy && d.strategy.name, ...this.exact.indicators].filter(Boolean);
      if (flagged.length) toast(`⚠ <b>Look-ahead detected</b> in ${esc(flagged.join(", "))}${c.strategy && !c.strategy.ok ? ": " + esc(c.strategy.detail) : ""}.
        Replaying in <b>exact mode</b>: it goes live at the replay start and every bar is decided from past bars only.`, "error", true, 14000);
    }
  }

  /** Reload after the strategy / indicators / interval changed — keeps the cursor time. */
  async refresh() {
    if (!this.active) return;
    const t = this.cursorTime();
    this.pausePlay();
    await this.load(t, { quiet: false });
  }

  exit() {
    this.pausePlay();
    this.active = false; this.selecting = false; this.data = null;
    this.manual = []; this.pos = null;
    this.bar.classList.add("hidden"); this.banner.classList.add("hidden"); this.shade.classList.add("hidden");
    document.body.classList.remove("replaying");
    this.chart.limit = null;
    this.h.onExit();
  }

  /* ------------------------------------------------------------ cursor */
  _index() {
    const s = this.data.sub;
    this.subStart = null;
    if (!s) return;
    const N = this.data.candles.t.length;
    this.subStart = new Array(N).fill(-1); this.subCount = new Array(N).fill(0);
    s.p.forEach((p, k) => { if (this.subStart[p] < 0) this.subStart[p] = k; this.subCount[p]++; });
  }

  total() { return this.data ? this.data.candles.t.length : 0; }
  cursorIdx() { return this.subPos > 0 ? this.n : this.n - 1; }
  cursorTime() { return this.data ? this.data.candles.t[Math.min(this.cursorIdx(), this.total() - 1)] : null; }
  /** end timestamp string to use for "backtest up to now" */
  cursorEnd() { return tsToStr(this.data.candles.t[this.n - 1]); }

  _forming() {
    if (this.subPos <= 0 || !this.subStart) return null;
    const s = this.data.sub, k0 = this.subStart[this.n];
    if (k0 < 0) return null;
    let h = -Infinity, l = Infinity, v = 0;
    for (let k = k0; k < k0 + this.subPos; k++) { h = Math.max(h, s.h[k]); l = Math.min(l, s.l[k]); v += s.v[k] || 0; }
    return { o: s.o[k0], h, l, c: s.c[k0 + this.subPos - 1], v };
  }

  _stepOne() {
    const N = this.total();
    if (this.n >= N) return false;
    if (this.mode === "intrabar" && this.subStart && this.subCount[this.n] > 1) {
      this.subPos++;
      if (this.subPos >= this.subCount[this.n]) { this.n++; this.subPos = 0; }
    } else { this.n++; this.subPos = 0; }
    return true;
  }

  forward(k = 1) {
    let moved = false;
    for (let i = 0; i < k; i++) moved = this._stepOne() || moved;
    if (moved) this.render();
    if (this.n >= this.total()) { this.pausePlay(); toast("Replay reached the end of the data", "ok"); }
  }

  back() {
    if (this.subPos > 0) this.subPos = 0; else this.n = Math.max(1, this.n - 1);
    this.render(true);
  }

  jump(n) { this.n = Math.max(1, Math.min(n, this.total())); this.subPos = 0; this.render(true); }

  setMode(m) {
    if (m === "intrabar" && !(this.data && this.data.sub)) return;
    this.mode = m; this.subPos = 0; this._save(); this._modeButtons(); this.render(true);
  }

  /* ------------------------------------------------------------ playback */
  toggle() { this.playing ? this.pausePlay() : this.play(); }
  play() {
    if (!this.active || this.n >= this.total()) return;
    this.playing = true; this.el.play.textContent = "⏸";
    let last = performance.now(), acc = 0;
    const tick = (now) => {
      if (!this.playing) return;
      acc += ((now - last) / 1000) * this.speed; last = now;
      let steps = 0;
      const before = this._tradeSig();
      while (acc >= 1 && steps < 250) { if (!this._stepOne()) break; acc -= 1; steps++; }
      if (steps) {
        this.render();
        if (this.pauseOnTrade && this._tradeSig() !== before) { this.pausePlay(); return; }
      }
      if (this.n >= this.total()) { this.pausePlay(); toast("Replay reached the end of the data", "ok"); return; }
      this._raf = requestAnimationFrame(tick);
    };
    this._raf = requestAnimationFrame(tick);
  }
  pausePlay() { this.playing = false; if (this._raf) cancelAnimationFrame(this._raf); this.el && (this.el.play.textContent = "▶"); }

  _tradeSig() { const v = this.visibleTrades(); return v.length + ":" + v.filter((t) => !t.live).length; }

  /* ------------------------------------------------------------ what is known at the cursor */
  visibleTrades() {
    const c = this.data.candles, L = this.n - 1, forming = this.subPos > 0;
    const f = forming ? this._forming() : null;
    const cur = forming ? this.n : L, price = f ? f.c : c.c[L];
    const out = [];
    for (const t of this.trades) {
      const openFill = this.execution === "next_open";
      const entryKnown = t.entry_idx <= L || (forming && openFill && t.entry_idx === this.n);
      if (!entryKnown) continue;
      const exitKnown = t.status === "Closed" && (t.exit_idx <= L ||
        (forming && openFill && t.exit_idx === this.n && OPEN_FILL_REASONS.has(t.exit_reason)));
      if (exitKnown) { out.push(t); continue; }
      out.push(this._liveCopy(t, cur, price));
    }
    return out;
  }

  _liveCopy(t, cur, price) {
    const dir = t.direction === "Long" ? 1 : -1;
    const ret = (price / t.entry_price - 1) * 100 * dir;
    const ex = this._excursion(t.entry_idx, cur, t.entry_price, dir);
    return { ...t, live: true, status: "Open", exit_idx: Math.max(cur, t.entry_idx), exit_price: price, exit_t: this.data.candles.t[cur],
      return_pct: ret, pnl: t.size ? t.size * (price - t.entry_price) * dir : ret, exit_reason: "Open", bars: cur - t.entry_idx, ...ex };
  }

  _excursion(from, to, entry, dir) {
    const c = this.data.candles, f = this.subPos > 0 ? this._forming() : null;
    let hi = -Infinity, lo = Infinity;
    for (let i = from; i <= to; i++) {
      const known = i < this.n;
      const h = known ? c.h[i] : f ? f.h : null, l = known ? c.l[i] : f ? f.l : null;
      if (h === null) continue;
      hi = Math.max(hi, h); lo = Math.min(lo, l);
    }
    if (!Number.isFinite(hi)) return { mae_pct: 0, mfe_pct: 0 };
    return dir > 0 ? { mfe_pct: (hi / entry - 1) * 100, mae_pct: (lo / entry - 1) * 100 }
      : { mfe_pct: (1 - lo / entry) * 100, mae_pct: (1 - hi / entry) * 100 };
  }

  /* ------------------------------------------------------------ practice trading */
  _price() { const f = this._forming(); return f ? f.c : this.data.candles.c[this.n - 1]; }
  trade(dir) {
    if (!this.active) return;
    if (this.pos && this.pos.dir === dir) { toast("Already in that position", "info", false, 1500); return; }
    if (this.pos) this.flat();
    const price = this._price(), fee = (this.h.feePct() || 0) / 100;
    const cash = this.h.capital();
    this.pos = { dir, entry_price: price, entry_idx: this.cursorIdx(), qty: cash / price, fee: cash * fee };
    this.render(true);
  }
  flat() {
    if (!this.pos) return;
    const p = this.pos, price = this._price(), fee = (this.h.feePct() || 0) / 100;
    const gross = p.qty * (price - p.entry_price) * p.dir;
    const fees = p.fee + p.qty * price * fee;
    const idx = this.cursorIdx();
    this.manual.push({ manual: true, id: this.manual.length, direction: p.dir > 0 ? "Long" : "Short", status: "Closed",
      entry_idx: p.entry_idx, exit_idx: idx, entry_t: this.data.candles.t[p.entry_idx], exit_t: this.data.candles.t[idx],
      entry_price: p.entry_price, exit_price: price, size: p.qty, pnl: gross - fees, fees,
      return_pct: (price / p.entry_price - 1) * 100 * p.dir, bars: idx - p.entry_idx, exit_reason: "Manual",
      ...this._excursion(p.entry_idx, idx, p.entry_price, p.dir) });
    this.pos = null;
    this.render(true);
  }
  _manualTrades() {
    const list = [...this.manual];
    if (this.pos) {
      const p = this.pos, price = this._price(), cur = this.cursorIdx();
      list.push({ manual: true, live: true, id: list.length, direction: p.dir > 0 ? "Long" : "Short", status: "Open",
        entry_idx: p.entry_idx, exit_idx: Math.max(cur, p.entry_idx), entry_t: this.data.candles.t[p.entry_idx], exit_t: this.data.candles.t[cur],
        entry_price: p.entry_price, exit_price: price, size: p.qty, pnl: p.qty * (price - p.entry_price) * p.dir - p.fee, fees: p.fee,
        return_pct: (price / p.entry_price - 1) * 100 * p.dir, bars: cur - p.entry_idx, exit_reason: "Open",
        ...this._excursion(p.entry_idx, cur, p.entry_price, p.dir) });
    }
    return list;
  }

  /* ------------------------------------------------------------ render */
  render(force = false) {
    if (!this.active) return;
    const forming = this._forming();
    this.chart.setLimit(this.n, forming);
    const strat = this.visibleTrades();
    const manual = this._manualTrades();
    const all = [...strat, ...manual].sort((a, b) => a.entry_idx - b.entry_idx);
    this.chart.setTrades(all, this._signals());
    this.chart.scrollToCursor(force);
    // trades table: on every new/closed trade, otherwise at most twice a second
    const sig = all.length + ":" + all.filter((t) => !t.live).length, now = performance.now();
    if (this.h.onTrades && (force || sig !== this._lastSig || now - (this._lastTbl || 0) > 500)) {
      this._lastSig = sig; this._lastTbl = now; this.h.onTrades(all);
    }
    this._status(strat, manual);
    if (this.exact.strategy || this.exact.indicators.length) this._exactFetch();
  }

  _status(strat, manual) {
    const c = this.data.candles, i = this.cursorIdx();
    this.el.slider.value = this.n;
    this.el.time.innerHTML = `${fmtTime(c.t[i])}${this.subPos ? ` <span class="muted">forming ${this.subPos}/${this.subCount[this.n]}</span>` : ""}
      <span class="muted">· bar ${this.n.toLocaleString()} / ${this.total().toLocaleString()}</span>`;
    if (this.data.strategy) {
      const closed = strat.filter((t) => !t.live), open = strat.find((t) => t.live);
      const wins = closed.filter((t) => t.pnl > 0).length, pnl = closed.reduce((a, t) => a + t.pnl, 0);
      this.el.strat.innerHTML = `<b>${esc(this.data.strategy.name)}</b> · ${closed.length} trades · win ${closed.length ? Math.round((wins / closed.length) * 100) : 0}%
        · P&L <b class="${pnl >= 0 ? "pos" : "neg"}">${fmtNum(pnl)}</b>` +
        (open ? ` · open ${open.direction} <b class="${open.return_pct >= 0 ? "pos" : "neg"}">${open.return_pct >= 0 ? "+" : ""}${open.return_pct.toFixed(2)}%</b>` : "");
    } else this.el.strat.innerHTML = `<span class="muted">Apply a strategy to replay its trades</span>`;
    const done = manual.filter((t) => !t.live), live = manual.find((t) => t.live);
    const rp = done.reduce((a, t) => a + t.pnl, 0), w = done.filter((t) => t.pnl > 0).length;
    this.el.pos.innerHTML = (live ? `<b class="${live.direction === "Long" ? "pos" : "neg"}">${live.direction}</b> @ ${fmtNum(live.entry_price)} ·
        <b class="${live.pnl >= 0 ? "pos" : "neg"}">${fmtNum(live.pnl)} (${live.return_pct >= 0 ? "+" : ""}${live.return_pct.toFixed(2)}%)</b>` : `<span class="muted">Flat</span>`) +
      ` · realised <b class="${rp >= 0 ? "pos" : "neg"}">${fmtNum(rp)}</b> · ${done.length} trades${done.length ? `, ${Math.round((w / done.length) * 100)}% win` : ""}`;
  }

  _badge() {
    const c = this.data.causal || {};
    const exact = this.exact.strategy || this.exact.indicators.length;
    const items = [];
    if (c.strategy) items.push(`${this.data.strategy.name}: ${c.strategy.ok ? "✓ " + c.strategy.detail : "⚠ look-ahead: " + c.strategy.detail}`);
    Object.entries(c.indicators || {}).forEach(([k, v]) => { if (!v.ok) items.push(`indicator ${k}: ⚠ ${v.detail}`); });
    this.el.badge.className = "rp-badge " + (exact ? "warn" : "ok");
    this.el.badge.textContent = exact ? "⚠ exact mode" : "✓ past data only";
    this.el.badge.title = (items.join("\n") || "Indicators verified: no look-ahead") + (exact
      ? "\n\nExact mode: the flagged code went 'live' at the replay start; every bar after that is decided using only the bars before it."
      : "\n\nEvery value on screen is computed from bars up to the cursor only.");
  }

  /* ------------------------------------------------------------ exact (point-in-time) mode
     For code that failed the look-ahead check. The strategy "goes live" at the replay start:
     for every new bar the backend runs it on bars [0, i] and we FREEZE its decision and
     plotted values for bar i — what you would really have seen at that moment. */
  _signals() {
    if (!this.data || !this.data.strategy) return null;
    return this.exact.strategy ? (this.pitSignals || null) : this.data.strategy.chart.signals;
  }

  _exactInit() {
    const N = this.total(), blank = () => new Array(N).fill(null);
    this.pitSignals = null;
    this.pitVals = {}; this.pitInd = {};
    const st = this.data.strategy;
    if (st && this.exact.strategy) {
      Object.keys(st.chart.overlays).forEach((k) => { this.pitVals[k] = blank(); });
      Object.values(st.chart.panes).forEach((d) => Object.keys(d).forEach((k) => { this.pitVals[k] = blank(); }));
      this.pitSeries = { equity: blank(), benchmark: blank(), drawdown: blank() };
    }
    this.data.indicators.filter((r) => this.exact.indicators.includes(r.key)).forEach((r) => {
      this.pitInd[r.key] = Object.fromEntries(Object.keys(r.series).map((k) => [k, blank()]));
    });
  }

  _exactPayload() {
    const c = this.data.strategy.chart;
    const pick = (d) => Object.fromEntries(Object.keys(d).map((k) => [k, this.pitVals[k]]));
    return { ...this.data.strategy, chart: { ...c, overlays: pick(c.overlays),
      panes: Object.fromEntries(Object.entries(c.panes).map(([p, d]) => [p, pick(d)])) }, series: this.pitSeries };
  }
  _exactInd(key) {
    const r = this.data.indicators.find((x) => x.key === key);
    return { ...r, series: this.pitInd[key] };
  }

  async _exactFetch() {
    if (this._inflight) { this._pending = true; return; }
    const cursor = this.n - 1;
    if (this.pit && cursor < this.pit.start) { this.pit = null; this._exactInit(); }   // went back before the live start
    this._inflight = true;
    const req = this.h.request(), seq = this._seq;
    this.el.badge.textContent = "⚠ exact · computing…";
    let again = false;
    try {
      const inds = req.indicators.filter((x) => this.exact.indicators.includes(x.key));
      const r = await this.api.replayStep({ ...req, cursor, pit: this.pit,
        strategy: this.exact.strategy ? req.strategy : null, indicators: inds });
      if (seq !== this._seq || !this.active) return;
      const N = this.total();
      const apply = (arrs, base, points, last) => {
        if (base) Object.entries(base).forEach(([k, v]) => { if (arrs[k]) v.forEach((x, i) => { arrs[k][i] = x; }); });
        Object.entries(points || {}).forEach(([k, pts]) => { if (arrs[k]) pts.forEach(([i, v]) => { arrs[k][i] = v; }); });
        Object.values(arrs).forEach((a) => { for (let i = last + 1; i < N; i++) a[i] = null; });
      };
      if (r.strategy) {
        const b = r.strategy.base;
        apply(this.pitVals, b ? { ...b.overlays, ...Object.assign({}, ...Object.values(b.panes || {})) } : null, r.strategy.points, r.pit.last);
        const ser = r.strategy.series;
        ["equity", "benchmark", "drawdown"].forEach((k) => {
          const a = this.pitSeries[k]; a.fill(null);
          ser[k].forEach((v, i) => { if (i >= r.pit.start) a[i] = v; });
        });
        this.trades = r.strategy.trades;
        this.pitSignals = r.strategy.signals;
        this.h.drawStrategy(this._exactPayload(), true);
      }
      r.indicators.forEach((it) => {
        const arrs = this.pitInd[it.key]; if (!arrs) return;
        apply(arrs, it.base ? it.base.series : null, it.points, r.pit.last);
        this.h.drawIndicators([this._exactInd(it.key)], true);
      });
      this.pit = r.pit;
      again = !r.done || this.pit.last < this.n - 1;
      this.chart.setLimit(this.n, this._forming());
      const strat = this.visibleTrades(), manual = this._manualTrades();
      this.chart.setTrades([...strat, ...manual].sort((a, b) => a.entry_idx - b.entry_idx), this._signals());
      this._status(strat, manual);
    } catch (e) { console.warn(e); toast("Exact replay: " + e.message, "error"); }
    finally {
      this._inflight = false;
      this._badge();
      if (this._pending || again) { this._pending = false; this._exactFetch(); }
    }
  }

  /* ------------------------------------------------------------ input */
  _onClick(p) {
    if (!this.selecting || !p || p.time === undefined) return;
    const i = this.chart.timeIndex.get(p.time);
    if (i !== undefined) this._startAt(i);
  }
  _onMove(p) {
    if (!this.selecting) return;
    if (!p || !p.point) { this.shade.classList.add("hidden"); return; }
    this.shade.style.left = p.point.x + "px";
    this.shade.classList.remove("hidden");
  }
  _onKey(e) {
    if (!this.active && !this.selecting) return;
    if (e.target.closest("input, select, textarea")) return;
    const k = e.key;
    if (k === "Escape") { e.preventDefault(); this.selecting && !this.active ? this.banner.querySelector("#rpCancel").click() : this.exit(); }
    if (!this.active) return;
    if (k === " ") { e.preventDefault(); this.toggle(); }
    else if (k === "ArrowRight") { e.preventDefault(); this.pausePlay(); this.forward(e.shiftKey ? 10 : 1); }
    else if (k === "ArrowLeft") { e.preventDefault(); this.pausePlay(); this.back(); }
    else if (k === "b" || k === "B") this.trade(1);
    else if (k === "s" || k === "S") this.trade(-1);
    else if (k === "c" || k === "C") this.flat();
  }
}
