"""
Deep backtest analysis: "where does the strategy make / lose money?"

  * breakdowns by time of day, hour, weekday, week of month, month, year,
    holding period, direction and exit reason
  * monthly / yearly return tables, drawdown periods, trade distributions
  * MAE / MFE study, rolling win-rate, streaks
  * plain-English insights that point at the weak spots
  * report persistence (data/reports/<id>.json)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime

import numpy as np
import pandas as pd

from .. import config
from ..data.sources import interval_seconds, parse_interval
from .backtest import _fmt_td

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ======================================================================
# Bucket statistics
# ======================================================================
def bucket_stats(g: pd.DataFrame, init_cash: float) -> dict:
    pnl, ret = g.pnl.to_numpy(), g.return_pct.to_numpy()
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    return {
        "trades": int(len(g)),
        "win_rate": float((pnl > 0).mean() * 100) if len(pnl) else None,
        "pnl": float(pnl.sum()),
        "pnl_pct": float(pnl.sum() / init_cash * 100),
        "avg_return": float(ret.mean()) if len(ret) else None,
        "profit_factor": float(wins.sum() / abs(losses.sum())) if len(losses) and losses.sum() != 0 else None,
        "avg_win": float(ret[ret > 0].mean()) if (ret > 0).any() else None,
        "avg_loss": float(ret[ret <= 0].mean()) if (ret <= 0).any() else None,
    }


def breakdown(tr: pd.DataFrame, key: pd.Series, order: list | None, init_cash: float) -> list[dict]:
    rows = []
    groups = tr.groupby(key, sort=order is None)
    keys = order if order is not None else list(groups.groups)
    for k in keys:
        if k in groups.groups:
            rows.append({"label": str(k), **bucket_stats(groups.get_group(k), init_cash)})
    return rows


def _hold_bucket(td: pd.Timedelta) -> str:
    m = td.total_seconds() / 60
    for lim, lab in [(15, "< 15m"), (60, "15m–1h"), (240, "1–4h"), (1440, "4h–1d"),
                     (4320, "1–3d"), (10080, "3–7d"), (43200, "1–4w")]:
        if m < lim:
            return lab
    return "> 4w"


HOLD_ORDER = ["< 15m", "15m–1h", "1–4h", "4h–1d", "1–3d", "3–7d", "1–4w", "> 4w"]


def breakdowns(tr: pd.DataFrame, interval: str, init_cash: float) -> list[dict]:
    if not len(tr):
        return []
    t = pd.DatetimeIndex(tr.entry_time)
    intraday = parse_interval(interval)[1] in ("s", "m", "h")
    out = []

    def add(title, key, order=None, note=""):
        rows = breakdown(tr, pd.Series(key, index=tr.index), order, init_cash)
        if len(rows) > 1 or title in ("Direction", "Exit reason"):
            out.append({"title": title, "note": note, "rows": rows})

    if intraday:
        iv_min = interval_seconds(interval) // 60
        if iv_min < 15:                      # fine bars -> 15-minute buckets
            tod = t.hour * 60 + (t.minute // 15) * 15
            note = "15-minute buckets"
        else:                                # one bucket per bar time (09:15, 09:30 ...)
            tod = t.hour * 60 + t.minute
            note = f"one bucket per {interval} bar"
        labels = [f"{m // 60:02d}:{m % 60:02d}" for m in tod]
        add("Time of day (entry)", labels, sorted(set(labels)), note)
        add("Hour (entry)", [f"{h:02d}:00" for h in t.hour], sorted({f"{h:02d}:00" for h in t.hour}))
    add("Day of week", list(t.day_name()), [d for d in DAYS if d in set(t.day_name())])
    add("Week of month", [f"Week {(d - 1) // 7 + 1}" for d in t.day], [f"Week {i}" for i in range(1, 6)])
    add("Month", [MONTHS[m - 1] for m in t.month], MONTHS)
    add("Year", [str(y) for y in t.year], sorted({str(y) for y in t.year}))
    holds = [_hold_bucket(x) for x in (pd.DatetimeIndex(tr.exit_time) - t)]
    add("Holding period", holds, [h for h in HOLD_ORDER if h in set(holds)])
    add("Direction", list(tr.direction), ["Long", "Short"])
    add("Exit reason", list(tr.exit_reason), None)
    return out


# ======================================================================
# Return tables / drawdowns / distributions
# ======================================================================
def monthly_table(equity: pd.Series) -> dict:
    m = equity.resample("ME").last()
    prev = m.shift(1)
    prev.iloc[0] = equity.iloc[0]
    rets = (m / prev - 1) * 100
    years = sorted(set(rets.index.year))
    rows = []
    for y in years:
        r = rets[rets.index.year == y]
        cells = [None] * 12
        for ts, v in r.items():
            cells[ts.month - 1] = None if pd.isna(v) else round(float(v), 2)
        ye = equity[equity.index.year == y]
        start = equity[equity.index.year < y].iloc[-1] if (equity.index.year < y).any() else equity.iloc[0]
        rows.append({"year": int(y), "months": cells, "total": round(float((ye.iloc[-1] / start - 1) * 100), 2)})
    return {"months": MONTHS, "rows": rows}


def drawdown_periods(equity: pd.Series, top: int = 5) -> list[dict]:
    peak = equity.cummax()
    dd = equity / peak - 1
    out, in_dd, start = [], False, None
    for ts, v in dd.items():
        if v < 0 and not in_dd:
            in_dd, start = True, ts
        elif v >= 0 and in_dd:
            seg = dd.loc[start:ts]
            out.append((start, seg.idxmin(), ts, float(seg.min())))
            in_dd = False
    if in_dd:
        seg = dd.loc[start:]
        out.append((start, seg.idxmin(), None, float(seg.min())))
    out.sort(key=lambda x: x[3])
    res = []
    for s, v, e, depth in out[:top]:
        end = e if e is not None else equity.index[-1]
        res.append({"start": str(s), "valley": str(v), "end": str(e) if e is not None else "not recovered",
                    "depth_pct": round(depth * 100, 2), "duration": _fmt_td(end - s),
                    "recovered": e is not None})
    return res


def histogram(values: np.ndarray, bins: int = 30) -> dict:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return {"edges": [], "counts": []}
    counts, edges = np.histogram(values, bins=min(bins, max(5, len(values) // 2)))
    return {"edges": np.round(edges, 3).tolist(), "counts": counts.tolist()}


def rolling_trades(tr: pd.DataFrame, n: int = 20) -> dict:
    if len(tr) < 2:
        return {"n": n, "win_rate": [], "expectancy": [], "cum_pnl": []}
    w = (tr.pnl > 0).astype(float)
    return {"n": n,
            "win_rate": np.round(w.rolling(n, min_periods=max(3, n // 4)).mean().to_numpy() * 100, 2).tolist(),
            "expectancy": np.round(tr.return_pct.rolling(n, min_periods=max(3, n // 4)).mean().to_numpy(), 3).tolist(),
            "cum_pnl": np.round(tr.pnl.cumsum().to_numpy(), 2).tolist()}


# ======================================================================
# Insights — the "where is it failing?" section
# ======================================================================
def insights(tr: pd.DataFrame, bds: list[dict], metric_groups: list[dict], init_cash: float) -> list[dict]:
    m = {i["key"]: i["value"] for g in metric_groups for i in g["items"]}
    out: list[dict] = []
    add = lambda level, title, text: out.append({"level": level, "title": title, "text": text})  # noqa: E731
    closed = tr[tr.status == "Closed"] if len(tr) else tr
    n = len(closed)

    if n == 0:
        add("bad", "No trades", "The strategy never completed a trade in this range. Check the conditions or widen the date range.")
        return out
    if n < 30:
        add("warn", "Small sample", f"Only {n} closed trades — results are not statistically reliable (aim for 30+, ideally 100+).")

    tot, bh = m.get("total_return"), m.get("buy_hold")
    if tot is not None and bh is not None and np.isfinite(tot) and np.isfinite(bh):
        if tot < bh:
            add("warn", "Lags buy & hold", f"Strategy returned {tot:.2f}% vs {bh:.2f}% for simply holding. "
                                          f"Time in market was {m.get('exposure', 0):.0f}%.")
        else:
            add("good", "Beats buy & hold", f"{tot:.2f}% vs {bh:.2f}% buy & hold.")

    # weakest / strongest buckets
    for b in bds:
        if b["title"] in ("Direction", "Exit reason", "Year"):
            continue
        rows = [r for r in b["rows"] if r["trades"] >= max(5, n // 25)]
        if len(rows) < 2:
            continue
        worst = min(rows, key=lambda r: r["pnl"])
        best = max(rows, key=lambda r: r["pnl"])
        if worst["pnl"] < 0:
            add("bad", f"Weak {b['title'].lower()}: {worst['label']}",
                f"{worst['trades']} trades, win rate {worst['win_rate']:.0f}%, P&L {worst['pnl_pct']:.2f}% of capital. "
                f"Consider filtering out this {b['title'].split(' (')[0].lower()}.")
        if best["pnl"] > 0 and best is not worst:
            add("good", f"Strong {b['title'].lower()}: {best['label']}",
                f"{best['trades']} trades, win rate {best['win_rate']:.0f}%, P&L +{best['pnl_pct']:.2f}% of capital.")

    # profit concentration
    gp = closed.pnl[closed.pnl > 0].sort_values(ascending=False)
    if len(gp) >= 5:
        k = max(1, int(np.ceil(len(closed) * 0.1)))
        share = gp.iloc[:k].sum() / gp.sum() * 100
        lvl = "warn" if share > 60 else "info"
        add(lvl, "Profit concentration", f"The top {k} trades (10%) produce {share:.0f}% of all gross profit."
            + (" The edge depends on a few outliers — don't cut winners early." if share > 60 else ""))

    # gave back profits
    losers = closed[closed.pnl <= 0]
    winners = closed[closed.pnl > 0]
    if len(losers) >= 5 and len(winners):
        thr = max(winners.return_pct.median() * 0.5, 0.3)
        gave = losers[losers.mfe_pct >= thr]
        if len(gave) / len(losers) > 0.25:
            add("bad", "Winners turning into losers",
                f"{len(gave)} of {len(losers)} losing trades ({len(gave) / len(losers) * 100:.0f}%) were up at least "
                f"{thr:.2f}% before closing red. A trailing stop or partial take-profit could save these.")

    # stop-loss suggestion from winners' MAE
    if len(winners) >= 10:
        mae90 = abs(np.percentile(winners.mae_pct, 10))
        lose_mae = abs(losers.mae_pct).median() if len(losers) else np.nan
        add("info", "Stop-loss hint",
            f"90% of winning trades never went more than {mae90:.2f}% against you. A stop around "
            f"{mae90 * 1.1:.2f}% would keep most winners" + (f" (median loser drew down {lose_mae:.2f}%)." if np.isfinite(lose_mae) else "."))

    # hold time asymmetry
    if len(winners) >= 5 and len(losers) >= 5:
        hw = (winners.exit_time - winners.entry_time).mean()
        hl = (losers.exit_time - losers.entry_time).mean()
        if hl > hw * 1.5:
            add("bad", "Losers held too long", f"Losing trades last {hl / hw:.1f}× longer than winners on average. "
                                               "Classic 'cut winners, let losers run' — tighten exits on losing trades.")

    # streaks
    if m.get("streak_l", 0) >= 6:
        add("warn", "Long losing streak", f"Up to {m['streak_l']} losses in a row — size positions so that this is survivable.")

    # costs
    fs = m.get("fees_share")
    if fs is not None and np.isfinite(fs) and fs > 30:
        add("bad", "Costs eat the edge", f"Fees consume {fs:.0f}% of gross profit. Trade less often or on a higher timeframe.")

    # sides
    longs, shorts = closed[closed.direction == "Long"], closed[closed.direction == "Short"]
    if len(longs) >= 5 and len(shorts) >= 5:
        lp, sp = longs.pnl.sum(), shorts.pnl.sum()
        if (lp > 0) != (sp > 0):
            bad_side = "short" if sp < 0 else "long"
            add("bad", f"The {bad_side} side loses", f"Long P&L {lp:,.0f}, short P&L {sp:,.0f}. Try running {('long' if bad_side == 'short' else 'short')}-only.")

    sharpe = m.get("sharpe")
    if sharpe is not None and np.isfinite(sharpe) and sharpe > 3 and n < 100:
        add("warn", "Too good to be true?", f"Sharpe {sharpe:.2f} on {n} trades is unusually high — check for overfitting "
                                            "by testing other symbols and an out-of-sample period.")
    order = {"bad": 0, "warn": 1, "info": 2, "good": 3}
    out.sort(key=lambda x: order[x["level"]])
    return out


# ======================================================================
# Full deep analysis
# ======================================================================
def deep(sim: dict, df: pd.DataFrame, metric_groups: list[dict], init_cash: float) -> dict:
    tr = sim["trades"]
    closed = tr[tr.status == "Closed"].reset_index(drop=True) if len(tr) else tr
    equity = sim["pf"].value()
    bds = breakdowns(closed, df.attrs.get("interval", "1d"), init_cash)
    yearly = []
    for y in sorted(set(equity.index.year)):
        e = equity[equity.index.year == y]
        c = df.close[df.close.index.year == y]
        prev_e = equity[equity.index.year < y].iloc[-1] if (equity.index.year < y).any() else equity.iloc[0]
        prev_c = df.close[df.close.index.year < y].iloc[-1] if (df.close.index.year < y).any() else df.close.iloc[0]
        yearly.append({"year": int(y), "strategy": round(float((e.iloc[-1] / prev_e - 1) * 100), 2),
                       "buy_hold": round(float((c.iloc[-1] / prev_c - 1) * 100), 2)})
    return {
        "breakdowns": bds,
        "monthly": monthly_table(equity),
        "yearly": yearly,
        "drawdowns": drawdown_periods(equity),
        "distribution": histogram(closed.return_pct.to_numpy() if len(closed) else np.array([])),
        "scatter": {
            "mae": np.round(closed.mae_pct.to_numpy(), 3).tolist() if len(closed) else [],
            "mfe": np.round(closed.mfe_pct.to_numpy(), 3).tolist() if len(closed) else [],
            "ret": np.round(closed.return_pct.to_numpy(), 3).tolist() if len(closed) else [],
            "bars": closed.bars.astype(int).tolist() if len(closed) else [],
        },
        "rolling": rolling_trades(closed),
        "insights": insights(tr, bds, metric_groups, init_cash),
    }


# ======================================================================
# Report persistence
# ======================================================================
def save_report(payload: dict) -> str:
    rid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    payload["id"] = rid
    (config.REPORTS_DIR / f"{rid}.json").write_text(json.dumps(payload, default=str), encoding="utf-8")
    return rid


def load_report(rid: str) -> dict:
    p = config.REPORTS_DIR / f"{rid}.json"
    if not p.exists() or "/" in rid or "\\" in rid:
        raise FileNotFoundError(rid)
    return json.loads(p.read_text(encoding="utf-8"))


def list_reports() -> list[dict]:
    out = []
    for p in sorted(config.REPORTS_DIR.glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            meta = d.get("meta", {})
            kp = {i["key"]: i["value"] for g in d.get("metrics", []) for i in g["items"]}
            out.append({"id": d.get("id", p.stem), **meta, "total_return": kp.get("total_return"),
                        "sharpe": kp.get("sharpe"), "trades": kp.get("trades")})
        except Exception:  # noqa: BLE001
            continue
    return out


def delete_report(rid: str):
    p = config.REPORTS_DIR / f"{rid}.json"
    if p.exists() and "/" not in rid and "\\" not in rid:
        p.unlink()
