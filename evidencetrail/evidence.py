"""Evidence records: immutable, content-addressed observations.

Every fact an agent consumes is wrapped in an Evidence object whose id is the
SHA-256 of its canonical JSON payload. Agents reference evidence by id in the
reasoning trail, so any conclusion can be traced back to the exact bytes that
produced it.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any


def canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_id(payload: dict) -> str:
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Evidence:
    kind: str                 # e.g. "market.24h", "news.headline", "candles.1h"
    source: str               # human-readable source name
    url: str                  # where it came from (re-fetchable)
    fetched_at: str           # ISO-8601 UTC
    payload: dict = field(repr=False)

    @property
    def id(self) -> str:
        return content_id(self.payload)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "source": self.source,
            "url": self.url,
            "fetched_at": self.fetched_at,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        return cls(kind=d["kind"], source=d["source"], url=d["url"],
                   fetched_at=d["fetched_at"], payload=d["payload"])

    @classmethod
    def make(cls, kind: str, source: str, url: str, fetched_at: str, payload: dict) -> "Evidence":
        return cls(kind=kind, source=source, url=url, fetched_at=fetched_at, payload=payload)
