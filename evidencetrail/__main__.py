"""Command line interface.

    python -m evidencetrail collect     # fetch evidence -> data/evidence.json
    python -m evidencetrail run         # collect + all agents + paper ledger
    python -m evidencetrail simulate    # walk-forward paper trades over captured candles
    python -m evidencetrail verify      # re-verify the hash-chained trail
    python -m evidencetrail replay      # re-run agents on stored evidence,
                                        # compare with recorded conclusions
    python -m evidencetrail ledger      # print practice-ledger summary
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import backtest, debate, dip_buyer, news_checker, sources, token_hunter
from .ledger import Ledger
from .trail import Trail, load_evidence, save_evidence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
EVIDENCE_PATH = os.path.join(DATA, "evidence.json")
TRAIL_PATH = os.path.join(DATA, "trail.jsonl")
LEDGER_PATH = os.path.join(DATA, "ledger.json")

WATCHLIST = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "TRXUSDT"]
CG_IDS = ["bitcoin", "ethereum", "solana", "binancecoin", "tron"]
TRADE_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]


def cmd_collect(_args) -> int:
    items = [e.to_dict() for e in sources.collect(WATCHLIST, CG_IDS)]
    save_evidence(EVIDENCE_PATH, items)
    kinds: dict[str, int] = {}
    for it in items:
        kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
    print(f"collected {len(items)} evidence items -> {EVIDENCE_PATH}")
    for k, v in sorted(kinds.items()):
        print(f"  {k:18} {v}")
    return 0


def _pipeline(trail: Trail, items: list[dict], ledger: Ledger) -> dict:
    news = news_checker.run(trail, items)
    bias = news_checker.aggregate(news)
    debate_res = debate.run(trail, items, news)
    hunter = token_hunter.run(trail, items)
    dips = dip_buyer.run(trail, items, debate_res["verdict"], bias, ledger,
                         TRADE_SYMBOLS)
    # mark open positions against the latest observed prices
    for e in items:
        if e["kind"] == "market.24h":
            ledger.mark(e["payload"]["symbol"], e["payload"]["last_price"])
    return {"news": news, "bias": bias, "debate": debate_res, "hunter": hunter,
            "dips": dips}


def cmd_run(_args) -> int:
    items = [e.to_dict() for e in sources.collect(WATCHLIST, CG_IDS)]
    save_evidence(EVIDENCE_PATH, items)
    # a run is one self-contained reasoning episode: archive any previous trail
    if os.path.exists(TRAIL_PATH):
        n = len([1 for line in open(TRAIL_PATH) if line.strip()])
        if n:
            os.replace(TRAIL_PATH, TRAIL_PATH.replace(".jsonl", f".{n}.jsonl"))
    # snapshot the paper account as it was *before* this run, for exact replay
    ledger = Ledger.load(LEDGER_PATH)
    json.dump({
        "cash": ledger.cash,
        "limits": {k: getattr(ledger.limits, k) for k in vars(ledger.limits)},
        "day_start_equity": ledger.day_start_equity,
        "day": ledger.day,
        "rejects": ledger.rejects,
        "positions": [vars(p) for p in ledger.positions],
    }, open(os.path.join(DATA, "ledger.start.json"), "w"), indent=1)
    trail = Trail(TRAIL_PATH)
    result = _pipeline(trail, items, ledger)
    ok, msg = trail.verify()

    print("=" * 72)
    print("EvidenceTrail run report")
    print("=" * 72)
    print(f"evidence items : {len(items)}")
    print(f"trail entries  : {len(trail.entries)}  ({msg})")
    print()
    print(f"[NewsChecker] bias={result['bias']} over {len(result['news'])} headlines")
    for n in result["news"][:5]:
        print(f"  {n['direction']:8} conf={n['confidence']:.2f}  {n['headline'][:80]}")
    print()
    v = result["debate"]["verdict"]
    print(f"[Debate] verdict={v['verdict']} bull_w={v['bull_weight']} "
          f"bear_w={v['bear_weight']} conf={v['confidence']}")
    print(f"  bull: {result['debate']['bull']['arguments'][:3]}")
    print(f"  bear: {result['debate']['bear']['arguments'][:3]}")
    print()
    print(f"[TokenHunter] selected={result['hunter']['selected_symbols']} "
          f"rejected={result['hunter']['rejected_symbols']}")
    print()
    for d in result["dips"]:
        print(f"[DipBuyer] {d['symbol']}: {d['outcome'].upper()} - {d['detail']}")
    print()
    s = ledger.summary()
    print(f"[Ledger] equity={s['equity']} cash={s['cash']} exposure={s['exposure']} "
          f"daily_pnl={s['daily_pnl_pct']}% rejected={s['rejected_decisions']}")
    for p in s["open"]:
        print(f"  open {p['id']} {p['side']} {p['size_units']:g} {p['symbol']} "
              f"@ {p['entry']:g} stop={p['stop']:g} target={p['target']:g}")
    for p in s["closed"]:
        print(f"  closed {p['id']} {p['symbol']} exit={p['exit']:g} pnl={p['pnl']:.2f}")
    print()
    print(f"verify: {msg}")
    return 0 if ok else 1


def cmd_verify(_args) -> int:
    trail = Trail(TRAIL_PATH)
    ok, msg = trail.verify()
    print(("PASS" if ok else "FAIL") + ": " + msg)
    return 0 if ok else 1


def cmd_replay(_args) -> int:
    """Re-run every agent over the stored evidence bundle and diff the
    conclusions against the recorded trail: proof the reasoning repeats."""
    recorded = Trail(TRAIL_PATH)
    if not os.path.exists(EVIDENCE_PATH):
        print("no stored evidence; run `collect` first", file=sys.stderr)
        return 2
    items = list(load_evidence(EVIDENCE_PATH).values())
    replay_path = os.path.join(DATA, "trail.replay.jsonl")
    if os.path.exists(replay_path):
        os.remove(replay_path)
    tmp = Trail(replay_path)
    # replay must see the exact paper-account state the recorded run started from
    start = os.path.join(DATA, "ledger.start.json")
    replay_ledger_path = os.path.join(DATA, "ledger.replay.json")
    if os.path.exists(start):
        with open(start) as fh, open(replay_ledger_path, "w") as out:
            out.write(fh.read())
        ledger = Ledger.load(replay_ledger_path)
    else:
        ledger = Ledger.load(replay_ledger_path)
    res = _pipeline(tmp, items, ledger)
    ok_r, msg_r = tmp.verify()

    def sig(entries):
        return [(e["body"]["agent"], json.dumps(e["body"]["conclusion"], sort_keys=True))
                for e in entries]

    rec, rep = sig(recorded.entries), sig(tmp.entries)
    if len(rec) != len(rep):
        print(f"FAIL: entry count differs recorded={len(rec)} replay={len(rep)}")
        return 1
    diffs = [i for i, (a, b) in enumerate(zip(rec, rep)) if a[0] != b[0] or a[1] != b[1]]
    if diffs:
        print(f"FAIL: {len(diffs)} conclusions differ (first at index {diffs[0]})")
        for i in diffs[:3]:
            print("  recorded:", rec[i][1][:200])
            print("  replay  :", rep[i][1][:200])
        return 1
    print(f"PASS: {len(rec)} conclusions reproduced identically from stored "
          f"evidence ({msg_r})")
    return 0


def cmd_simulate(_args) -> int:
    """Walk-forward paper trades over the captured candle history."""
    if not os.path.exists(EVIDENCE_PATH):
        print("no stored evidence; run `collect` or `run` first", file=sys.stderr)
        return 2
    items = list(load_evidence(EVIDENCE_PATH).values())
    bias = news_checker.bias_from_evidence(items)
    bt_path = os.path.join(DATA, "trail.backtest.jsonl")
    if os.path.exists(bt_path):
        os.remove(bt_path)
    trail = Trail(bt_path)
    ledger = Ledger.load(LEDGER_PATH)
    summary = backtest.run(trail, items, bias, ledger, TRADE_SYMBOLS)
    ok, msg = trail.verify()

    print("=" * 72)
    print("Walk-forward practice trades (same rules, replayed over 1h candles)")
    print("=" * 72)
    print(f"news bias used as gate: {bias}")
    for sym, s in summary.items():
        print(f"  {sym:9} candidate episodes={s['decided']:3} "
              f"accepted={s['accepted']} opened={s['opened']}")
    print()
    led = ledger.summary()
    closed = led["closed"]
    wins = [p for p in closed if p["pnl"] > 0]
    print(f"ledger: equity={led['equity']} cash={led['cash']} "
          f"exposure={led['exposure']} rejected={led['rejected_decisions']}")
    print(f"closed practice trades={len(closed)}  wins={len(wins)}  "
          f"losses={len(closed) - len(wins)}  "
          f"realised_pnl={sum(p['pnl'] for p in closed):.2f}")
    for p in closed[:8]:
        print(f"  {p['id']} {p['symbol']} entry={p['entry']:g} exit={p['exit']:g} "
              f"pnl={p['pnl']:+.2f}  trail={p['trail_entry'][:12]}")
    for p in led["open"][:4]:
        print(f"  {p['id']} {p['symbol']} entry={p['entry']:g} stop={p['stop']:g} "
              f"target={p['target']:g} (open)")
    print()
    print(f"backtest trail: {len(trail.entries)} entries - {msg}")
    return 0 if ok else 1


def cmd_ledger(_args) -> int:
    print(json.dumps(Ledger.load(LEDGER_PATH).summary(), indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="evidencetrail")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("collect", cmd_collect), ("run", cmd_run), ("simulate", cmd_simulate),
                     ("verify", cmd_verify), ("replay", cmd_replay), ("ledger", cmd_ledger)]:
        sub.add_parser(name).set_defaults(fn=fn)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
