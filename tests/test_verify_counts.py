"""Verifier regressions against real Git objects, independent of the collector."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_counts import verify


class VerifyCountsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.run_git("init", "--quiet")
        tree = self.run_git("mktree", input=b"").decode().strip()
        self.parent = self.commit(tree, b"e\n", 1791072000)
        self.head = self.commit(tree, b"eE\n", 1791072060, self.parent)
        self.run_git("update-ref", "HEAD", self.head)
        self.snapshot = self.repo / "data.json"
        self.value = {
            "schema_version": 1,
            "rows": [{"date": "2026-10-04", "count": 3, "commits": 2},
                     {"date": "2026-10-05", "count": 0, "commits": 0}],
            "source": {
                "commit": self.head,
                "start_inclusive": "2026-10-04T00:00:00Z",
                "end_exclusive": "2026-10-06T00:00:00Z",
                "letter": "e", "total_count": 3, "total_commits": 2,
                "commits": [self.receipt(self.parent, b"e\n", 1791072000),
                            self.receipt(self.head, b"eE\n", 1791072060)],
            },
        }

    def run_git(self, *args, input=None):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], input=input)

    def commit(self, tree, message, epoch, parent=None):
        parents = f"parent {parent}\n" if parent else ""
        raw = (f"tree {tree}\n{parents}author Fixture <fixture@example.invalid> {epoch} +0000\n"
               f"committer Fixture <fixture@example.invalid> {epoch} +0000\n\n").encode() + message
        return self.run_git("hash-object", "-t", "commit", "-w", "--stdin", input=raw).decode().strip()

    def receipt(self, sha, message, epoch):
        stamp = dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
        return {"sha": sha, "committed_at": stamp.isoformat().replace("+00:00", "Z"),
                "day": stamp.date().isoformat(), "count": message.count(b"e") + message.count(b"E"),
                "message_sha256": hashlib.sha256(message).hexdigest()}

    def check(self):
        self.snapshot.write_text(json.dumps(self.value), encoding="utf-8")
        return verify(self.repo, self.snapshot)

    def test_valid_snapshot(self):
        result = self.check()
        self.assertTrue(result["verified"])
        self.assertEqual(result["data_sha256"], hashlib.sha256(self.snapshot.read_bytes()).hexdigest())

    def test_report_retains_zero_days(self):
        self.assertEqual(self.check()["daily_counts"], {"2026-10-04": 3, "2026-10-05": 0})

    def test_hash_binds_the_bytes_that_were_actually_verified(self):
        original = json.dumps(self.value).encode()
        self.snapshot.write_bytes(original)
        check_output = subprocess.check_output
        changed = False

        def run_and_change_file(*args, **kwargs):
            nonlocal changed
            if not changed:
                self.snapshot.write_bytes(original + b" ")
                changed = True
            return check_output(*args, **kwargs)

        with mock.patch("subprocess.check_output", side_effect=run_and_change_file):
            result = verify(self.repo, self.snapshot)
        self.assertEqual(result["data_sha256"], hashlib.sha256(original).hexdigest())

    def test_rejects_shallow_history_even_when_partial_snapshot_reconciles(self):
        (self.repo / ".git" / "shallow").write_text(self.head + "\n")
        self.value["rows"][0].update(count=2, commits=1)
        self.value["source"].update(total_count=2, total_commits=1)
        self.value["source"]["commits"] = self.value["source"]["commits"][1:]
        with self.assertRaisesRegex(ValueError, "shallow"):
            self.check()

    def test_rejects_a_moving_ref_instead_of_a_pin(self):
        self.value["source"]["commit"] = "HEAD"
        with self.assertRaisesRegex(ValueError, "SHA"):
            self.check()

    def test_rejects_multiletter_metric(self):
        self.value["source"]["letter"] = "ee"
        with self.assertRaisesRegex(ValueError, "letter"):
            self.check()

    def test_rejects_tampered_committed_at(self):
        self.value["source"]["commits"][0]["committed_at"] = "2026-10-04T12:34:56Z"
        with self.assertRaisesRegex(ValueError, "receipts"):
            self.check()

    def test_rejects_boolean_counts(self):
        self.value["source"]["commits"][0]["count"] = True
        with self.assertRaises(ValueError):
            self.check()

    def test_rejects_non_midnight_window(self):
        self.value["source"]["start_inclusive"] = "2026-10-04T00:00:01Z"
        self.value["source"]["end_exclusive"] = "2026-10-06T00:00:01Z"
        self.value["rows"][0].update(count=2, commits=1)
        self.value["source"].update(total_count=2, total_commits=1)
        self.value["source"]["commits"] = self.value["source"]["commits"][1:]
        with self.assertRaisesRegex(ValueError, "UTC"):
            self.check()


if __name__ == "__main__":
    unittest.main()
