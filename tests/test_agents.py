import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evidencetrail import debate, news_checker, token_hunter  # noqa: E402
from evidencetrail.dip_buyer import evaluate  # noqa: E402
from evidencetrail.evidence import content_id  # noqa: E402
from evidencetrail.trail import Trail  # noqa: E402


def ev(kind, payload, url="https://example.test/x"):
    return {"id": content_id(payload), "kind": kind, "source": "test",
            "url": url, "fetched_at": "2026-10-09T00:00:00Z", "payload": payload}


def ticker(sym, price, chg, vol=100_000_000, high=None, low=None):
    return ev("market.24h", {"symbol": sym, "last_price": price,
                             "change_pct_24h": chg, "quote_volume_24h": vol,
                             "high_24h": high or price * 1.01,
                             "low_24h": low or price * 0.99})


class NewsCheckerTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.trail = Trail(os.path.join(self.dir, "t.jsonl"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_exploit_headline_is_negative(self):
        res = news_checker.run(self.trail, [
            ev("news.headline", {"title": "DeFi protocol suffers $40M exploit on Ethereum",
                                 "feed": "x", "link": "https://a", "index": 0})])
        self.assertEqual(res[0]["direction"], "negative")
        self.assertIn("ETH", res[0]["assets"])
        self.assertLess(res[0]["confidence"], 0.9)

    def test_adoption_headline_is_positive(self):
        res = news_checker.run(self.trail, [
            ev("news.headline", {"title": "Bitcoin ETF approval brings institutional adoption",
                                 "feed": "x", "link": "https://b", "index": 1})])
        self.assertEqual(res[0]["direction"], "positive")

    def test_aggregate_neutral_when_empty(self):
        self.assertEqual(news_checker.aggregate([])["bias"], "neutral")


class TokenHunterTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.trail = Trail(os.path.join(self.dir, "t.jsonl"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_liquid_and_stable_selected(self):
        res = token_hunter.run(self.trail, [ticker("BTCUSDT", 80000, 1.2)])
        self.assertEqual(res["selected_symbols"], ["BTCUSDT"])

    def test_thin_liquidity_rejected(self):
        res = token_hunter.run(self.trail, [ticker("SHITUSDT", 1.0, 2.0, vol=1_000_000)])
        self.assertEqual(res["rejected_symbols"], ["SHITUSDT"])
        self.assertTrue(any("liquidity" in r for r in res["rejected"][0]["reasons"]))

    def test_pump_rejected(self):
        res = token_hunter.run(self.trail, [ticker("PUMPUSDT", 1.0, 88.0)])
        self.assertEqual(res["rejected_symbols"], ["PUMPUSDT"])


class DipBuyerTests(unittest.TestCase):
    def rows(self, closes):
        return [[0, c, c, c, c, 0] for c in closes]

    def test_no_entry_without_drawdown(self):
        closes = [100.0] * 40
        dec, fired, inputs = evaluate(
            {"symbol": "BTCUSDT", "last_price": 100.0, "change_pct_24h": 0,
             "quote_volume_24h": 1e9, "high_24h": 101, "low_24h": 99},
            self.rows(closes), {"verdict": "neutral"}, {"bias": "neutral"}, 10_000)
        self.assertEqual(inputs["drawdown_pct"], 0.0)
        self.assertLess(dec["confidence"], 0.6)

    def test_decision_is_atomic_with_stop_and_target(self):
        closes = [100.0] * 30 + [95.0]           # 5% drawdown
        dec, fired, inputs = evaluate(
            {"symbol": "BTCUSDT", "last_price": 95.0, "change_pct_24h": -2.0,
             "quote_volume_24h": 1e9, "high_24h": 96, "low_24h": 94},
            self.rows(closes), {"verdict": "risk-on"}, {"bias": "positive"}, 10_000)
        self.assertAlmostEqual(inputs["drawdown_pct"], 5.0, places=2)
        self.assertLess(dec["stop"], dec["entry"])
        self.assertGreater(dec["target"], dec["entry"])
        self.assertGreater(dec["size_units"], 0)
        ids = {f["id"] for f in fired}
        self.assertIn("dip.sizing", ids)
        self.assertIn("dip.band", ids)

    def test_risk_off_lowers_confidence_but_gates_still_decide(self):
        closes = [100.0] * 30 + [95.0]
        dec, fired, inputs = evaluate(
            {"symbol": "BTCUSDT", "last_price": 95.0, "change_pct_24h": -2.0,
             "quote_volume_24h": 1e9, "high_24h": 96, "low_24h": 94},
            self.rows(closes), {"verdict": "risk-off"}, {"bias": "positive"}, 10_000)
        self.assertEqual(inputs["debate"]["verdict"], "risk-off")
        self.assertTrue(inputs["gates"]["in_band"])


class DebateTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.trail = Trail(os.path.join(self.dir, "t.jsonl"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_same_evidence_ids_for_both_sides(self):
        items = [ticker("BTCUSDT", 80000, 2.5),
                 ev("news.headline", {"title": "Ethereum ETF approval expected",
                                      "feed": "x", "link": "https://c", "index": 0})]
        news = news_checker.run(self.trail, items)
        res = debate.run(self.trail, items, news)
        self.assertEqual(res["bull"]["shared_evidence_count"],
                         res["bear"]["shared_evidence_count"])
        self.assertIn(res["verdict"]["verdict"], {"risk-on", "risk-off", "neutral"})
        ok, msg = self.trail.verify()
        self.assertTrue(ok, msg)


if __name__ == "__main__":
    unittest.main()
