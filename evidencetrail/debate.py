"""Agents: Bull / Bear debate + Judge.

Two opposing agents argue *from the same evidence set*; a third judge weighs
the fired rules and produces the verdict. All three write to the trail, and
the judge's entry records that both sides consumed identical evidence ids -
cause and effect stays visible.
"""
from __future__ import annotations

from statistics import median
from typing import Iterable

from .lexicon import DEBATE_RULES
from .trail import Trail, rule

BULL = "BullAgent"
BEAR = "BearAgent"
JUDGE = "DebateJudge"
RULESET = "debate/v1"


def _market(evidence: Iterable[dict]) -> list[dict]:
    return [e for e in evidence if e["kind"] == "market.24h"]


def bull_run(trail: Trail, evidence: list[dict], news: list[dict]) -> dict:
    mkt = _market(evidence)
    ids = [e["id"] for e in mkt] + [n["headline_id"] for n in news]
    fired, args = [], []
    changes = [e["payload"]["change_pct_24h"] for e in mkt]
    volumes = [e["payload"]["quote_volume_24h"] for e in mkt]
    med_vol = median(volumes) if volumes else 0

    for e in mkt:
        p = e["payload"]
        if p["change_pct_24h"] > 0:
            fired.append(rule("bull.price_positive", DEBATE_RULES["bull.price_positive"]["desc"],
                              {"symbol": p["symbol"], "change_pct": p["change_pct_24h"]}))
            args.append(f"{p['symbol']} 24h {p['change_pct_24h']:+.2f}% (momentum up)")
        if med_vol and p["quote_volume_24h"] >= med_vol:
            fired.append(rule("bull.volume_above_median", DEBATE_RULES["bull.volume_above_median"]["desc"],
                              {"symbol": p["symbol"], "volume": p["quote_volume_24h"], "median": med_vol}))
            args.append(f"{p['symbol']} volume {p['quote_volume_24h'] / 1e6:.0f}M >= median")

    for n in news:
        if n["direction"] == "positive":
            fired.append(rule("bull.positive_news", DEBATE_RULES["bull.positive_news"]["desc"],
                              {"headline": n["headline"][:80], "score": n["score"]}))
            args.append(f"positive headline: {n['headline'][:80]}")

    weight = sum(DEBATE_RULES[r["id"]]["weight"] for r in fired if r["id"] in DEBATE_RULES)
    conclusion = {"side": "bull", "weight": weight, "arguments": args,
                  "argument_count": len(args),
                  "shared_evidence_count": len(ids)}
    entry = trail.record(BULL, RULESET, ids, fired, conclusion,
                         inputs={"watchlist_changes": changes})
    conclusion["trail_entry"] = entry["hash"]
    return conclusion


def bear_run(trail: Trail, evidence: list[dict], news: list[dict]) -> dict:
    mkt = _market(evidence)
    ids = [e["id"] for e in mkt] + [n["headline_id"] for n in news]
    fired, args = [], []

    for e in mkt:
        p = e["payload"]
        if p["change_pct_24h"] < 0:
            fired.append(rule("bear.price_negative", DEBATE_RULES["bear.price_negative"]["desc"],
                              {"symbol": p["symbol"], "change_pct": p["change_pct_24h"]}))
            args.append(f"{p['symbol']} 24h {p['change_pct_24h']:+.2f}% (momentum down)")
        if p["low_24h"] and p["last_price"] <= p["low_24h"] * 1.015:
            fired.append(rule("bear.near_24h_low", DEBATE_RULES["bear.near_24h_low"]["desc"],
                              {"symbol": p["symbol"], "last": p["last_price"], "low": p["low_24h"]}))
            args.append(f"{p['symbol']} sits at 24h low ({p['last_price']:.2f})")
        if abs(p["change_pct_24h"]) > 8.0:
            fired.append(rule("bear.volatility_extreme", DEBATE_RULES["bear.volatility_extreme"]["desc"],
                              {"symbol": p["symbol"], "change_pct": p["change_pct_24h"]}))
            args.append(f"{p['symbol']} |24h| {abs(p['change_pct_24h']):.1f}% = unstable")

    for n in news:
        if n["direction"] == "negative":
            fired.append(rule("bear.negative_news", DEBATE_RULES["bear.negative_news"]["desc"],
                              {"headline": n["headline"][:80], "score": n["score"]}))
            args.append(f"negative headline: {n['headline'][:80]}")

    weight = sum(DEBATE_RULES[r["id"]]["weight"] for r in fired if r["id"] in DEBATE_RULES)
    conclusion = {"side": "bear", "weight": weight, "arguments": args,
                  "argument_count": len(args),
                  "shared_evidence_count": len(ids)}
    entry = trail.record(BEAR, RULESET, ids, fired, conclusion)
    conclusion["trail_entry"] = entry["hash"]
    return conclusion


def judge_run(trail: Trail, bull: dict, bear: dict, shared_ids: list[str]) -> dict:
    b, r = bull["weight"], bear["weight"]
    if b > r:
        verdict, conf = "risk-on", min(0.9, 0.5 + 0.05 * (b - r))
    elif r > b:
        verdict, conf = "risk-off", min(0.9, 0.5 + 0.05 * (r - b))
    else:
        verdict, conf = "neutral", 0.5
    fired = [
        rule("judge.score", "sum of published debate weights",
             {"bull": b, "bear": r}),
        rule("judge.shared_evidence", "both sides argued from identical evidence",
             {"shared_ids": len(shared_ids), "bull_ids": bull["shared_evidence_count"],
              "bear_ids": bear["shared_evidence_count"]}),
    ]
    conclusion = {"verdict": verdict, "bull_weight": b, "bear_weight": r,
                  "confidence": round(conf, 2),
                  "rationale": (f"bull rules={bull['argument_count']} (w={b}) vs "
                                f"bear rules={bear['argument_count']} (w={r}) over the same "
                                f"{len(shared_ids)} evidence items")}
    entry = trail.record(JUDGE, RULESET, shared_ids, fired, conclusion)
    conclusion["trail_entry"] = entry["hash"]
    return conclusion


def run(trail: Trail, evidence: list[dict], news: list[dict]) -> dict:
    market_ids = [e["id"] for e in _market(evidence)]
    news_ids = [n["headline_id"] for n in news]
    shared = market_ids + news_ids
    bull = bull_run(trail, evidence, news)
    bear = bear_run(trail, evidence, news)
    verdict = judge_run(trail, bull, bear, shared)
    return {"bull": bull, "bear": bear, "verdict": verdict, "shared_evidence": shared}
