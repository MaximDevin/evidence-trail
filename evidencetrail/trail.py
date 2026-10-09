"""Append-only, hash-chained reasoning trail.

Each entry records: which agent ran, which evidence ids it consumed, which
explicit rules fired, and what it concluded. Entries are chained with
SHA-256(prev_hash || canonical(entry_body)), so the trail is tamper-evident
and re-verifiable offline with `evidencetrail verify`.

That is what makes the reasoning *repeatable*: given the same evidence ids and
the same versioned rule set, re-running the agents reproduces the same
conclusions, and `verify` proves the recorded trail was never edited.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from .evidence import canonical

GENESIS = "0" * 64


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Trail:
    """Hash-chained JSONL log of reasoning steps."""

    def __init__(self, path: str):
        self.path = path
        self.entries: list[dict] = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                self.entries = [json.loads(line) for line in fh if line.strip()]
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # -- construction -----------------------------------------------------
    @staticmethod
    def _hash(prev_hash: str, body: dict) -> str:
        return hashlib.sha256((prev_hash + canonical(body)).encode("utf-8")).hexdigest()

    @property
    def head(self) -> str:
        return self.entries[-1]["hash"] if self.entries else GENESIS

    def record(self, agent: str, ruleset: str, evidence_ids: Iterable[str],
               rules: Iterable[dict], conclusion: dict, inputs: Optional[dict] = None) -> dict:
        body = {
            "seq": len(self.entries) + 1,
            "ts": utcnow(),
            "agent": agent,
            "ruleset": ruleset,
            "evidence_ids": list(evidence_ids),
            "rules": list(rules),
            "inputs": inputs or {},
            "conclusion": conclusion,
        }
        # freeze the body: callers may keep mutating their `conclusion` dict
        # (e.g. to attach the trail hash) after recording, which must not
        # invalidate the chain
        body = json.loads(json.dumps(body, ensure_ascii=False))
        entry = {"prev_hash": self.head, "body": body}
        entry["hash"] = self._hash(entry["prev_hash"], body)
        self.entries.append(entry)
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    # -- verification -----------------------------------------------------
    def verify(self) -> tuple[bool, str]:
        prev = GENESIS
        for i, entry in enumerate(self.entries, start=1):
            if entry.get("prev_hash") != prev:
                return False, f"entry {i}: prev_hash mismatch"
            body = entry.get("body") or {}
            if body.get("seq") != i:
                return False, f"entry {i}: sequence mismatch"
            if self._hash(prev, body) != entry.get("hash"):
                return False, f"entry {i}: hash mismatch (trail was modified)"
            prev = entry["hash"]
        return True, f"ok: {len(self.entries)} entries verified, head={prev[:16]}..."

    # -- replay -----------------------------------------------------------
    def conclusions(self, agent: Optional[str] = None) -> list[dict]:
        out = []
        for e in self.entries:
            if agent is None or e["body"]["agent"] == agent:
                out.append(e["body"]["conclusion"])
        return out


def load_evidence(path: str) -> dict[str, dict]:
    """Load the evidence bundle written by the collector, keyed by evidence id."""
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        bundle = json.load(fh)
    return {item["id"]: item for item in bundle}


def save_evidence(path: str, items: list[dict]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)


def rule(id_: str, name: str, detail: Any) -> dict:
    """Helper: a rule hit as it appears in the trail."""
    return {"id": id_, "name": name, "detail": detail}
