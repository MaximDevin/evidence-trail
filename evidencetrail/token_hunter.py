"""Agent: TokenHunter (Meme / Token Hunter direction).

Screens watchlist candidates against published, fully numeric rules and
explains every accept/reject. No black box: the trail carries the per-rule
outcome for every candidate.
"""
from __future__ import annotations

from typing import Iterable

from .lexicon import HUNTER_RULES
from .trail import Trail, rule

AGENT = "TokenHunter"
RULESET = "token-hunter/v1"


def _screen(payload: dict) -> tuple[bool, list[dict], list[str]]:
    fired, reasons = [], []
    vol = payload["quote_volume_24h"]
    chg = payload["change_pct_24h"]
    px = payload["last_price"]

    ok_liq = vol >= HUNTER_RULES["liquidity"]["min"]
    fired.append(rule("liquidity", HUNTER_RULES["liquidity"]["desc"],
                      {"value": vol, "pass": ok_liq}))
    if ok_liq:
        reasons.append(f"liquidity ok ({vol / 1e6:.0f}M 24h volume)")
    else:
        reasons.append(f"fails liquidity ({vol / 1e6:.1f}M < 50M)")

    ok_stab = abs(chg) <= HUNTER_RULES["stability"]["max"]
    fired.append(rule("stability", HUNTER_RULES["stability"]["desc"],
                      {"value": chg, "pass": ok_stab}))
    if not ok_stab:
        reasons.append(f"fails stability (|24h| {abs(chg):.1f}% > 25%)")
    else:
        reasons.append(f"stability ok (24h {chg:+.2f}%)")

    ok_trend = chg >= HUNTER_RULES["trend"]["min"]
    fired.append(rule("trend", HUNTER_RULES["trend"]["desc"],
                      {"value": chg, "pass": ok_trend}))
    if not ok_trend:
        reasons.append(f"fails trend (24h {chg:+.2f}% < -3%)")
    else:
        reasons.append("trend ok (not in free fall)")

    ok_data = px > 0 and payload["high_24h"] >= payload["low_24h"] > 0
    fired.append(rule("data_quality", HUNTER_RULES["data_quality"]["desc"],
                      {"price": px, "pass": ok_data}))
    if not ok_data:
        reasons.append("fails data quality (implausible OHLC)")

    return ok_liq and ok_stab and ok_trend and ok_data, fired, reasons


def run(trail: Trail, evidence: Iterable[dict]) -> dict:
    tickers = [e for e in evidence if e["kind"] == "market.24h"]
    selected, rejected = [], []
    for ev in tickers:
        p = ev["payload"]
        ok, fired, reasons = _screen(p)
        verdict = "selected" if ok else "rejected"
        conclusion = {"symbol": p["symbol"], "verdict": verdict,
                      "last_price": p["last_price"], "reasons": reasons,
                      "rules_passed": sum(1 for r in fired if r["detail"].get("pass")),
                      "rules_total": len(fired)}
        entry = trail.record(AGENT, RULESET, [ev["id"], ], fired, conclusion,
                             inputs={"symbol": p["symbol"]})
        conclusion["trail_entry"] = entry["hash"]
        (selected if ok else rejected).append(conclusion)
    return {"selected": selected, "rejected": rejected,
            "selected_symbols": [s["symbol"] for s in selected],
            "rejected_symbols": [r["symbol"] for r in rejected]}
