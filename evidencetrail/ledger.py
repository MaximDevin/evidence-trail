"""Paper-trading ledger with user-defined risk limits.

We hold no keys and never send orders: a "trade" here is a *practice* position
with entry, size, stop and target recorded as one atomic decision, plus the
trail entry id that justified it.

Enforced limits (all user-editable):
  * max_position_pct   - one position may never exceed this % of equity
  * max_exposure_pct   - sum of open position notionals <= this % of equity
  * max_open_positions - hard cap on concurrent positions
  * max_daily_loss_pct - circuit breaker: no new positions after this daily loss
  * min_confidence     - agents must clear this confidence to open a position
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Optional

from .trail import utcnow


@dataclass
class RiskLimits:
    max_position_pct: float = 10.0
    max_exposure_pct: float = 30.0
    max_open_positions: int = 3
    max_daily_loss_pct: float = 3.0
    min_confidence: float = 0.60


@dataclass
class Position:
    id: str
    symbol: str
    side: str            # "long" only: practice book, no leverage, no shorts
    entry: float
    size_units: float
    notional: float
    stop: float
    target: float
    opened_at: str
    trail_entry: str     # hash of the reasoning entry that justified it
    status: str = "open"
    exit: Optional[float] = None
    closed_at: Optional[str] = None
    pnl: float = 0.0


@dataclass
class Ledger:
    path: str
    cash: float = 10_000.0
    limits: RiskLimits = field(default_factory=RiskLimits)
    positions: list[Position] = field(default_factory=list)
    day_start_equity: float = 10_000.0
    day: str = ""
    rejects: list[dict] = field(default_factory=list)

    # -- persistence ------------------------------------------------------
    @classmethod
    def load(cls, path: str) -> "Ledger":
        if not os.path.exists(path):
            return cls(path=path, day=utcnow()[:10])
        with open(path, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        led = cls(path=path, cash=d["cash"], limits=RiskLimits(**d["limits"]),
                  day_start_equity=d["day_start_equity"], day=d["day"],
                  rejects=d.get("rejects", []))
        led.positions = [Position(**p) for p in d["positions"]]
        return led

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        d = asdict(self)
        d["limits"] = asdict(self.limits)
        d["positions"] = [asdict(p) for p in self.positions]
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)

    # -- views ------------------------------------------------------------
    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.status == "open"]

    @property
    def exposure(self) -> float:
        return sum(p.notional for p in self.open_positions)

    @property
    def equity(self) -> float:
        return self.cash + sum(p.notional for p in self.open_positions) + sum(
            p.pnl for p in self.positions if p.status == "closed")

    def _roll_day(self) -> None:
        today = utcnow()[:10]
        if today != self.day:
            self.day = today
            self.day_start_equity = self.equity

    @property
    def daily_pnl_pct(self) -> float:
        if not self.day_start_equity:
            return 0.0
        return 100.0 * (self.equity - self.day_start_equity) / self.day_start_equity

    # -- decision ---------------------------------------------------------
    def try_open(self, decision: dict) -> tuple[bool, str]:
        """decision: {symbol, side, entry, size_units, stop, target,
                       confidence, trail_entry, reason}"""
        self._roll_day()
        checks: list[tuple[str, bool, str]] = []
        entry = float(decision["entry"])
        units = float(decision["size_units"])
        notional = entry * units
        equity = self.equity

        checks.append(("confidence",
                       float(decision.get("confidence", 0)) >= self.limits.min_confidence,
                       f"confidence {decision.get('confidence')} >= {self.limits.min_confidence}"))
        checks.append(("position_size",
                       notional <= equity * self.limits.max_position_pct / 100.0,
                       f"notional {notional:.2f} <= {self.limits.max_position_pct}% of equity "
                       f"({equity * self.limits.max_position_pct / 100.0:.2f})"))
        checks.append(("total_exposure",
                       self.exposure + notional <= equity * self.limits.max_exposure_pct / 100.0,
                       f"exposure {self.exposure + notional:.2f} <= {self.limits.max_exposure_pct}% "
                       f"({equity * self.limits.max_exposure_pct / 100.0:.2f})"))
        checks.append(("open_positions",
                       len(self.open_positions) < self.limits.max_open_positions,
                       f"open {len(self.open_positions)} < {self.limits.max_open_positions}"))
        checks.append(("cash",
                       notional <= self.cash,
                       f"notional {notional:.2f} <= available cash {self.cash:.2f}"))
        checks.append(("daily_loss_breaker",
                       self.daily_pnl_pct > -self.limits.max_daily_loss_pct,
                       f"daily pnl {self.daily_pnl_pct:.2f}% > "
                       f"-{self.limits.max_daily_loss_pct}%"))

        failed = [c for c in checks if not c[1]]
        if failed:
            reason = "; ".join(f"{n}: {d}" for n, _, d in failed)
            self.rejects.append({"ts": utcnow(), "symbol": decision.get("symbol"),
                                 "failed": [n for n, _, _ in failed], "detail": reason})
            self.save()
            return False, f"REJECTED by risk limits -> {reason}"

        pos = Position(
            id=f"P{len(self.positions) + 1:04d}",
            symbol=decision["symbol"],
            side=decision.get("side", "long"),
            entry=entry,
            size_units=units,
            notional=notional,
            stop=float(decision["stop"]),
            target=float(decision["target"]),
            opened_at=utcnow(),
            trail_entry=decision["trail_entry"],
        )
        self.positions.append(pos)
        self.cash -= notional
        self.save()
        return True, f"ACCEPTED {pos.id} {pos.side} {units:g} {pos.symbol} @ {entry:g} " \
                     f"(notional {notional:.2f}, stop {pos.stop:g}, target {pos.target:g})"

    def mark(self, symbol: str, price: float) -> None:
        """Mark open positions to market; close on stop/target hit."""
        for p in self.open_positions:
            if p.symbol != symbol:
                continue
            hit_stop = price <= p.stop
            hit_target = price >= p.target
            if not (hit_stop or hit_target):
                continue
            exit_price = p.stop if hit_stop else p.target
            p.exit = exit_price
            p.closed_at = utcnow()
            p.status = "closed"
            p.pnl = (exit_price - p.entry) * p.size_units
            self.cash += p.size_units * exit_price
        self.save()

    def summary(self) -> dict:
        return {
            "equity": round(self.equity, 2),
            "cash": round(self.cash, 2),
            "exposure": round(self.exposure, 2),
            "daily_pnl_pct": round(self.daily_pnl_pct, 4),
            "open": [asdict(p) for p in self.open_positions],
            "closed": [asdict(p) for p in self.positions if p.status == "closed"],
            "risk_limits": asdict(self.limits),
            "rejected_decisions": len(self.rejects),
        }
