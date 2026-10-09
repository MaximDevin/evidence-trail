"""Agent: NewsChecker.

Verifies a headline against collected evidence and explains its crypto impact
as an explicit cause -> effect chain. Rules and thresholds live in lexicon.py
and every fired rule is written to the trail.
"""
from __future__ import annotations

import re
from typing import Iterable

from .lexicon import ASSETS, NEGATIVE_CUES, POSITIVE_CUES
from .trail import Trail, rule

AGENT = "NewsChecker"
RULESET = "news-checker/v1"


def _has(low: str, cue: str) -> bool:
    """Word-boundary match: 'ban' must not fire inside 'banks',
    'invest' not inside 'investigators'."""
    return re.search(r"(?<![a-z0-9])" + re.escape(cue) + r"(?![a-z0-9])", low) is not None


def _classify(text: str) -> tuple[set[str], int, list[dict], list[dict]]:
    low = text.lower()
    assets = {sym for mention, sym in ASSETS.items() if _has(low, mention)}
    pos_hits, neg_hits, fired = [], [], []
    for cue, w in POSITIVE_CUES.items():
        if _has(low, cue):
            pos_hits.append(cue)
            fired.append(rule(f"pos:{cue}", "positive cue", {"cue": cue, "weight": w}))
    for cue, w in NEGATIVE_CUES.items():
        if _has(low, cue):
            neg_hits.append(cue)
            fired.append(rule(f"neg:{cue}", "negative cue", {"cue": cue, "weight": w}))
    score = sum(POSITIVE_CUES[c] for c in pos_hits) + sum(NEGATIVE_CUES[c] for c in neg_hits)
    return assets, score, fired, pos_hits + neg_hits


def run(trail: Trail, evidence: Iterable[dict], max_items: int = 12) -> list[dict]:
    """Classify every news headline; return conclusions."""
    out = []
    headlines = [e for e in evidence if e["kind"] == "news.headline"][:max_items]
    for ev in headlines:
        title = ev["payload"].get("title", "")
        assets, score, fired, cues = _classify(title)

        if score > 0:
            direction, impact = "positive", "supportive"
        elif score < 0:
            direction, impact = "negative", "adverse"
        else:
            direction, impact = "neutral", "no clear market impact"

        if assets and cues:
            confidence = min(0.9, 0.55 + 0.1 * abs(score))
        elif cues:
            confidence = 0.5
        else:
            confidence = 0.3

        cause = f"headline cites {', '.join(sorted(cues))}" if cues else "no event cues matched"
        effect = (f"rule weight {score:+d} for {', '.join(sorted(assets)) or 'market'} "
                  f"-> {impact}")
        conclusion = {
            "headline": title[:140],
            "headline_id": ev["id"],
            "assets": sorted(assets),
            "direction": direction,
            "score": score,
            "impact": impact,
            "cause": cause,
            "effect": effect,
            "confidence": round(confidence, 2),
        }
        fired.append(rule("nc.direction", "direction mapping",
                          {"score": score, "direction": direction}))
        entry = trail.record(agent=AGENT, ruleset=RULESET, evidence_ids=[ev["id"]],
                             rules=fired, conclusion=conclusion,
                             inputs={"cues": cues})
        conclusion["trail_entry"] = entry["hash"]
        out.append(conclusion)
    return out


def aggregate(news_conclusions: list[dict]) -> dict:
    """Net bias across headlines (used by DipBuyer as a gate)."""
    if not news_conclusions:
        return {"bias": "neutral", "net_score": 0, "confidence": 0.0}
    net = sum(c["score"] for c in news_conclusions)
    bias = "positive" if net > 0 else "negative" if net < 0 else "neutral"
    conf = min(0.95, 0.4 + 0.05 * abs(net))
    return {"bias": bias, "net_score": net, "confidence": round(conf, 2),
            "headlines": len(news_conclusions)}


def bias_from_evidence(evidence: Iterable[dict], max_items: int = 20) -> dict:
    """Classify stored headlines without writing a trail entry (for replays)."""
    heads = [e for e in evidence if e["kind"] == "news.headline"][:max_items]
    conclusions = []
    for ev in heads:
        assets, score, _fired, _cues = _classify(ev["payload"].get("title", ""))
        conclusions.append({"score": score, "assets": sorted(assets)})
    return aggregate(conclusions)
