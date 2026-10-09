import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evidencetrail.trail import Trail, GENESIS  # noqa: E402


class TrailTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "trail.jsonl")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_hash_chain_verifies(self):
        t = Trail(self.path)
        t.record("A", "v1", ["e1"], [{"id": "r1", "name": "n", "detail": 1}],
                 {"verdict": "x"})
        t.record("B", "v1", ["e1", "e2"], [{"id": "r2", "name": "n", "detail": 2}],
                 {"verdict": "y"})
        ok, msg = t.verify()
        self.assertTrue(ok, msg)

    def test_tampering_detected(self):
        t = Trail(self.path)
        t.record("A", "v1", ["e1"], [], {"verdict": "x"})
        t.record("B", "v1", ["e2"], [], {"verdict": "y"})
        # rewrite history
        with open(self.path) as fh:
            lines = fh.readlines()
        entry = json.loads(lines[0])
        entry["body"]["conclusion"]["verdict"] = "tampered"
        lines[0] = json.dumps(entry) + "\n"
        with open(self.path, "w") as fh:
            fh.writelines(lines)
        ok, msg = Trail(self.path).verify()
        self.assertFalse(ok)
        self.assertIn("hash mismatch", msg)

    def test_reload_appends_not_duplicates(self):
        t = Trail(self.path)
        t.record("A", "v1", [], [], {"v": 1})
        t2 = Trail(self.path)
        self.assertEqual(len(t2.entries), 1)
        self.assertEqual(t2.head, t.head)
        t2.record("B", "v1", [], [], {"v": 2})
        self.assertEqual(len(Trail(self.path).entries), 2)

    def test_genesis_prev_hash(self):
        t = Trail(self.path)
        e = t.record("A", "v1", [], [], {})
        self.assertEqual(e["prev_hash"], GENESIS)


if __name__ == "__main__":
    unittest.main()
