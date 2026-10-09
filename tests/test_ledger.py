import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evidencetrail.ledger import Ledger, RiskLimits  # noqa: E402


def decision(**kw):
    base = dict(symbol="BTCUSDT", side="long", entry=100.0, size_units=1.0,
                stop=97.0, target=105.0, confidence=0.8, trail_entry="h", reason="t")
    base.update(kw)
    return base


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "ledger.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_accepts_within_limits(self):
        led = Ledger(path=self.path)
        ok, msg = led.try_open(decision())          # $100 notional of $10k equity
        self.assertTrue(ok, msg)
        self.assertEqual(len(led.open_positions), 1)
        self.assertAlmostEqual(led.cash, 10_000 - 100)

    def test_rejects_oversized_position(self):
        led = Ledger(path=self.path)
        ok, msg = led.try_open(decision(size_units=2000.0))  # $200k > 10% cap
        self.assertFalse(ok)
        self.assertIn("position_size", msg)
        self.assertEqual(len(led.open_positions), 0)

    def test_rejects_low_confidence(self):
        led = Ledger(path=self.path)
        ok, msg = led.try_open(decision(confidence=0.3))
        self.assertFalse(ok)
        self.assertIn("confidence", msg)

    def test_exposure_and_count_caps(self):
        led = Ledger(path=self.path, limits=RiskLimits(
            max_position_pct=10.0, max_exposure_pct=25.0, max_open_positions=2))
        self.assertTrue(led.try_open(decision(symbol="AAA"))[0])
        self.assertTrue(led.try_open(decision(symbol="BBB"))[0])
        # third would exceed max_open_positions (2) and exposure cap
        ok, msg = led.try_open(decision(symbol="CCC"))
        self.assertFalse(ok)
        self.assertTrue("open_positions" in msg or "total_exposure" in msg)

    def test_daily_loss_circuit_breaker(self):
        from evidencetrail.trail import utcnow
        led = Ledger(path=self.path)
        led.day = utcnow()[:10]                 # same session, no day roll
        led.day_start_equity = 10_000.0
        led.cash = 9_600.0                      # -4% day > 3% breaker
        ok, msg = led.try_open(decision())
        self.assertFalse(ok)
        self.assertIn("daily_loss_breaker", msg)

    def test_stop_and_target_close_position(self):
        led = Ledger(path=self.path)
        led.try_open(decision())
        led.mark("BTCUSDT", 96.0)               # below stop 97
        self.assertEqual(len(led.open_positions), 0)
        closed = [p for p in led.positions if p.status == "closed"]
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].exit, 97.0)
        self.assertAlmostEqual(closed[0].pnl, (97.0 - 100.0) * 1.0)

    def test_persistence_roundtrip(self):
        led = Ledger(path=self.path)
        led.try_open(decision())
        again = Ledger.load(self.path)
        self.assertEqual(len(again.open_positions), 1)
        self.assertEqual(again.positions[0].symbol, "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
