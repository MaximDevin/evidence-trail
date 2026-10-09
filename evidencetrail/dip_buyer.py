"""Agent: Buy-the-Dip (entry, sizing and exit decided as ONE decision).

Computes a drawdown from recent candles, gates on the debate verdict and the
NewsChecker bias, then asks the ledger to open a practice position. The ledger
may refuse - the refusal itself is recorded in the trail, so rejections are
part of the reasoning history too.

No keys, no orders: this writes a paper position only.
"""
from __future__ import annotations

from typing import Iterable

from .lexicon import DIP_PARAMS
from .trail import Trail, rule

AGENT = "DipBuyer"
RULESET = "buy-the-dip/v1"


def _closes(rows: list) -> list[float]:
    return [float(r[4]) for r in rows]


def evaluate(payload_ticker: dict, rows: list, verdict: dict, news_bias: dict,
             equity: float) -> tuple[dict, list[dict], dict]:
    """Pure function: returns (decision, fired_rules, inputs) without side effects."""
    p = DIP_PARAMS
    closes = _closes(rows)
    lookback = closes[-p["lookback"]:]
    local_high = max(lookback)
    entry = closes[-1]
    drawdown = 100.0 * (local_high - entry) / local_high

    fired = [
        rule("dip.local_high", f"local high over last {p['lookback']} candles",
             {"high": local_high, "last": entry, "drawdown_pct": round(drawdown, 3)}),
        rule("dip.band", "drawdown must sit inside [min,max]",
             {"value": round(drawdown, 3), "min": p["min_drawdown_pct"],
              "max": p["max_drawdown_pct"],
              "pass": p["min_drawdown_pct"] <= drawdown <= p["max_drawdown_pct"]}),
        rule("dip.debate_adjust", "debate verdict adjusts confidence (soft factor)",
             {"verdict": verdict.get("verdict"),
              "bull_weight": verdict.get("bull_weight"),
              "bear_weight": verdict.get("bear_weight"),
              "effect": ("+0.10" if verdict.get("verdict") == "risk-on"
                         else "-0.05" if verdict.get("verdict") == "risk-off" else "0")}),
        rule("dip.news_gate", "NewsChecker bias may not be negative (hard gate)",
             {"bias": news_bias.get("bias"), "net_score": news_bias.get("net_score"),
              "pass": news_bias.get("bias") != "negative"}),
    ]

    # Hard gates: price must sit in the drawdown band and the news must not be
    # adverse. The debate verdict is deliberately SOFT: a dip buyer by
    # definition buys into weakness, so bearish momentum lowers confidence
    # instead of vetoing the trade.
    in_band = p["min_drawdown_pct"] <= drawdown <= p["max_drawdown_pct"]
    news_ok = news_bias.get("bias") != "negative"
    gates_pass = in_band and news_ok
    fired.append(rule("dip.entry_gate", "drawdown band + no adverse news",
                      {"in_band": in_band, "news_ok": news_ok, "pass": gates_pass}))

    confidence = 0.45
    if in_band:
        confidence += min(0.25, 0.05 * (drawdown - p["min_drawdown_pct"]))
    confidence += 0.10 if verdict.get("verdict") == "risk-on" else 0.0
    confidence -= 0.05 if verdict.get("verdict") == "risk-off" else 0.0
    confidence = round(max(0.0, min(0.95, confidence)), 2)

    stop = entry * (1 - p["stop_pct"] / 100.0)
    target = entry * (1 + p["target_pct"] / 100.0)
    risk_budget = equity * p["risk_per_trade_pct"] / 100.0
    stop_distance = entry - stop
    units_by_risk = risk_budget / stop_distance if stop_distance > 0 else 0.0
    units_by_cap = (equity * p["max_notional_pct"] / 100.0) / entry if entry > 0 else 0.0
    units = max(0.0, min(units_by_risk, units_by_cap)) if gates_pass else 0.0
    if not gates_pass:
        confidence = 0.0

    fired.append(rule("dip.sizing", "size = min(risk budget, position cap)",
                      {"risk_budget": round(risk_budget, 2),
                       "units_by_risk": round(units_by_risk, 8),
                       "units_by_cap": round(units_by_cap, 8),
                       "chosen_units": round(units, 8)}))

    decision = {
        "symbol": payload_ticker["symbol"],
        "side": "long",
        "entry": entry,
        "size_units": round(units, 8),
        "stop": stop,
        "target": target,
        "confidence": confidence,
        "reason": (f"drawdown {drawdown:.2f}% from {p['lookback']}-candle high; "
                   f"debate={verdict.get('verdict')}; news_bias={news_bias.get('bias')}; "
                   f"stop {p['stop_pct']}% / target {p['target_pct']}% decided together"),
    }
    inputs = {"drawdown_pct": round(drawdown, 3), "local_high": local_high,
              "last": entry, "confidence": confidence,
              "debate": verdict,
              "gates": {"in_band": in_band, "news_ok": news_ok}}
    return decision, fired, inputs


def run(trail: Trail, evidence: Iterable[dict], verdict: dict, news_bias: dict,
        ledger, symbols: list[str]) -> list[dict]:
    candles = {e["payload"]["symbol"]: e for e in evidence
               if e["kind"] == "candles.1h"}
    tickers = {e["payload"]["symbol"]: e for e in evidence if e["kind"] == "market.24h"}
    results = []
    for sym in symbols:
        if sym not in candles or sym not in tickers:
            continue
        rows = candles[sym]["payload"]["rows"]
        decision, fired, inputs = evaluate(tickers[sym]["payload"], rows, verdict,
                                           news_bias, ledger.equity)
        accepted, detail = ledger.try_open({**decision, "trail_entry": "pending"})
        conclusion = {"symbol": sym, "decision": decision,
                      "outcome": "accepted" if accepted else "rejected",
                      "detail": detail, "equity_after": round(ledger.equity, 2)}
        entry = trail.record(AGENT, RULESET,
                             [candles[sym]["id"], tickers[sym]["id"]],
                             fired, conclusion, inputs=inputs)
        # back-fill the ledger row with the real trail hash
        if accepted:
            for pos in reversed(ledger.positions):
                if pos.trail_entry == "pending":
                    pos.trail_entry = entry["hash"]
                    break
            ledger.save()
        conclusion["trail_entry"] = entry["hash"]
        results.append(conclusion)
    return results
