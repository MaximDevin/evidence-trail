"""Walk-forward practice-trading over captured candles.

The live pipeline records one decision per run (today's market state). This
module replays the captured 1h candle history through the *same* published
decision function (`dip_buyer.evaluate`) so the ledger shows the practice
trades the agent would have taken, with the same gates, sizing and stops.

Nothing here touches the network or real orders - it is a paper simulation
whose every decision is written to the hash-chained trail.
"""
from __future__ import annotations

from typing import Iterable

from . import dip_buyer
from .lexicon import DIP_PARAMS
from .trail import Trail, rule

AGENT = "DipBuyer.walk-forward"
RULESET = "buy-the-dip/v1 (walk-forward)"


def _trading_view(rows: list, i: int, symbol: str, static_volume: float) -> dict:
    """Build the ticker-shaped payload a decision sees at candle i."""
    window = rows[max(0, i - 24):i + 1]
    closes = [float(r[4]) for r in window]
    highs = [float(r[2]) for r in rows[max(0, i - 24):i + 1]]
    lows = [float(r[3]) for r in rows[max(0, i - 24):i + 1]]
    last = closes[-1]
    base = closes[0] if closes else last
    change = 100.0 * (last - base) / base if base else 0.0
    return {"symbol": symbol, "last_price": last, "change_pct_24h": round(change, 4),
            "quote_volume_24h": static_volume, "high_24h": max(highs), "low_24h": min(lows)}


def _momentum_verdict(view: dict) -> dict:
    """Same published debate rules, evaluated on the trailing 24 candles."""
    bull = 0
    bear = 0
    if view["change_pct_24h"] > 0:
        bull += 2
    else:
        bear += 2
    if view["low_24h"] and view["last_price"] <= view["low_24h"] * 1.015:
        bear += 2
    if abs(view["change_pct_24h"]) > 8.0:
        bear += 1
    if view["quote_volume_24h"] > 0:
        bull += 1  # volume present in all our sources (see TokenHunter median rule)
    verdict = "risk-on" if bull > bear else "risk-off" if bear > bull else "neutral"
    return {"verdict": verdict, "bull_weight": bull, "bear_weight": bear,
            "confidence": round(min(0.9, 0.5 + 0.05 * abs(bull - bear)), 2),
            "rationale": f"trailing-24candle rules: bull={bull} bear={bear}"}


def run(trail: Trail, evidence: Iterable[dict], news_bias: dict, ledger,
        symbols: list[str], max_trades_per_symbol: int = 4) -> dict:
    candles = {e["payload"]["symbol"]: e for e in evidence if e["kind"] == "candles.1h"}
    volumes = {e["payload"]["symbol"]: e["payload"]["quote_volume_24h"]
               for e in evidence if e["kind"] == "market.24h"}

    summary: dict[str, dict] = {}
    for sym in symbols:
        if sym not in candles:
            continue
        rows = candles[sym]["payload"]["rows"]
        opened = 0
        decided = 0
        accepted = 0
        open_pos = None
        for i in range(DIP_PARAMS["lookback"], len(rows)):
            view = _trading_view(rows, i, sym, volumes.get(sym, 0.0))
            if open_pos is not None:
                hi, lo, close = float(rows[i][2]), float(rows[i][3]), float(rows[i][4])
                if lo <= open_pos.stop:
                    ledger.mark(sym, open_pos.stop)
                    open_pos = None
                elif hi >= open_pos.target:
                    ledger.mark(sym, open_pos.target)
                    open_pos = None
                continue
            if opened >= max_trades_per_symbol:
                break
            decided += 1
            verdict = _momentum_verdict(view)
            decision, fired, inputs = dip_buyer.evaluate(
                view, rows[:i + 1], verdict, news_bias, ledger.equity)
            if not all(inputs["gates"].values()):
                # gate-level no-entry: counted, not a candidate trade
                decided -= 1
                continue
            ok, detail = ledger.try_open({**decision, "trail_entry": "pending"})
            fired.append(rule("wf.episode", "walk-forward candle index",
                              {"index": i, "price": view["last_price"]}))
            conclusion = {"symbol": sym, "episode": i, "verdict": verdict["verdict"],
                          "drawdown_pct": inputs["drawdown_pct"],
                          "confidence": decision["confidence"],
                          "outcome": "accepted" if ok else "rejected",
                          "detail": detail}
            entry = trail.record(AGENT, RULESET,
                                 [candles[sym]["id"]],
                                 fired, conclusion, inputs=inputs)
            if ok:
                opened += 1
                accepted += 1
                for pos in reversed(ledger.positions):
                    if pos.trail_entry == "pending":
                        pos.trail_entry = entry["hash"]
                        open_pos = pos
                        break
                ledger.save()
        # flatten anything still open so accounting stays simple
        if open_pos is not None:
            ledger.mark(sym, float(rows[-1][4]))
            open_pos = None
        summary[sym] = {"decided": decided, "accepted": accepted, "opened": opened}
    return summary
