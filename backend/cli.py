"""
Command-line helper (run from the backend/ folder):

  python cli.py symbols
  python cli.py download "RELIANCE INDUSTRIES LTD" 5m 2024-01-01 [2025-01-01]
  python cli.py update   "RELIANCE INDUSTRIES LTD" 5m
  python cli.py import   "TATA CONSULTANCY SERVICES" 1m C:/old_data/TCS.csv
  python cli.py stored
  python cli.py strategies
  python cli.py backtest "RELIANCE INDUSTRIES LTD" 15m "EMA Crossover" --params fast=9 slow=21 --start 2025-01-01
  python cli.py deep     "RELIANCE INDUSTRIES LTD" 15m "EMA Crossover"          # saves a report
  python cli.py upstox-search "tata motors"   # find the exact Upstox name / key of a stock or index
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.data import store  # noqa: E402
from app.data.sources import SOURCES  # noqa: E402


def _kv(pairs):
    out = {}
    for p in pairs or []:
        k, _, v = p.partition("=")
        out[k] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="HedgeOne CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("symbols")
    sub.add_parser("stored")
    sub.add_parser("strategies")
    us = sub.add_parser("upstox-search"); us.add_argument("query")
    d = sub.add_parser("download"); d.add_argument("symbol"); d.add_argument("interval"); d.add_argument("start"); d.add_argument("end", nargs="?")
    u = sub.add_parser("update"); u.add_argument("symbol"); u.add_argument("interval")
    i = sub.add_parser("import"); i.add_argument("symbol"); i.add_argument("interval"); i.add_argument("path"); i.add_argument("--monthfirst", action="store_true")
    for name in ("backtest", "deep"):
        b = sub.add_parser(name); b.add_argument("symbol"); b.add_argument("interval"); b.add_argument("strategy")
        b.add_argument("--params", nargs="*"); b.add_argument("--settings", nargs="*")
        b.add_argument("--start"); b.add_argument("--end")
    a = ap.parse_args()

    if a.cmd == "symbols":
        for n, info in store.catalog().items():
            print(f"{n:32s} {info['source']:8s} {info['symbol']:28s} stored: {', '.join(store.stored_intervals(n)) or '-'}")
    elif a.cmd == "stored":
        for r in store.inventory():
            print(f"{r['symbol']:32s} {r['interval']:5s} {r['rows']:>9,d}  {r['first']} → {r['last']}")
    elif a.cmd == "download":
        end = datetime.fromisoformat(a.end) if a.end else datetime.now()
        print(store.download(a.symbol, a.interval, datetime.fromisoformat(a.start), end, progress=print))
    elif a.cmd == "update":
        print(store.update(a.symbol, a.interval, progress=print))
    elif a.cmd == "import":
        print(store.import_csv(a.symbol, a.interval, a.path, dayfirst=not a.monthfirst))
    elif a.cmd == "upstox-search":
        for r in SOURCES["upstox"].search(a.query):
            print(f"{r['symbol']:40s} {r['instrument_key']:28s} {r['name']}")
    else:
        import strategies
        errs = strategies.load_all()
        if errs:
            print("Strategy load errors:", json.dumps(errs, indent=2))
        from app.engine import STRATEGIES
        if a.cmd == "strategies":
            for s in STRATEGIES.values():
                print(f"[{s.category:14s}] {s.name:34s} {', '.join(f'{k}={p.default}' for k, p in s.params.items())}")
            return
        from app.engine.runner import run
        res = run(a.symbol, a.interval, a.start, a.end, a.strategy, _kv(a.params), _kv(a.settings),
                  "deep" if a.cmd == "deep" else "backtest")
        for g in res["metrics"]:
            print(f"\n{g['title']}")
            for it in g["items"]:
                v = it["value"]
                v = f"{v:,.2f}" if isinstance(v, float) else v
                print(f"  {it['label']:28s} {v}")
        if a.cmd == "deep":
            print(f"\nReport saved: http://127.0.0.1:8000/report.html?id={res['report_id']}")
            for ins in res["analysis"]["insights"]:
                print(f"  [{ins['level']:4s}] {ins['title']}: {ins['text']}")


if __name__ == "__main__":
    main()
