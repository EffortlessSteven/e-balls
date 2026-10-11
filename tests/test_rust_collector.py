"""Cross-check Rust collection against the existing independent Python collector/verifier."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "scripts" / "count_letters.py"
VERIFY = ROOT / "scripts" / "verify_counts.py"

def invoke(repo, *args, input=None):
    return subprocess.check_output(["git", "-C", str(repo), *args], input=input)

class RustCollectionTests(unittest.TestCase):
    def setUp(self):
        binary = os.environ.get("EBALLS_COLLECT_BIN")
        if not binary:
            self.skipTest("Set EBALLS_COLLECT_BIN to compiled Rust collector")
        self.binary = str((ROOT / binary).resolve()) if not Path(binary).is_absolute() else binary
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.repo = self.path / "source"
        self.repo.mkdir()
        invoke(self.repo, "init", "-q", "-b", "main")
        self.tree = invoke(self.repo, "mktree", input=b"").decode().strip()

    def commit(self, message, date, email="someone@example.test", name="Someone", parents=()):
        timestamp = int(dt.datetime.fromisoformat(date).timestamp())
        parents_text = "".join(f"parent {sha}\n" for sha in parents)
        raw = (
            f"tree {self.tree}\n{parents_text}"
            f"author {name} <{email}> {timestamp} +0000\n"
            f"committer Fixture <fixture@example.invalid> {timestamp} +0000\n\n"
        ).encode() + message
        sha = invoke(self.repo, "hash-object", "-t", "commit", "-w", "--stdin", input=raw).decode().strip()
        invoke(self.repo, "update-ref", "refs/heads/main", sha)
        return sha

    def rust(self, *more):
        destination = self.path / "rust.json"
        process = subprocess.run(
            [self.binary, "--repo", str(self.repo), "--ref", "main",
             "--repository", "fixture/project", "--project", "project",
             "--since", "7d", "--end", "2026-10-11",
             "--out", str(destination), *more],
            capture_output=True, text=True,
        )
        return process, destination

    def python(self):
        destination = self.path / "python.json"
        process = subprocess.run(
            ["python3", str(PYTHON), "--repo", str(self.repo), "--ref", "main",
             "--repository", "fixture/project", "--project", "project",
             "--since", "7d", "--end", "2026-10-11",
             "--out", str(destination)],
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(process.returncode, 0)
        return json.loads(destination.read_text())

    def test_rust_matches_python_and_independent_git_verifier(self):
        a = self.commit(b"eE\n\nbody ee\x00delimiter", "2026-10-04T04:00:00+00:00")
        b = self.commit(b"eeE\n\ntext", "2026-10-10T10:00:00+00:00",
                        email="else@example.test", name="Someone Else", parents=(a,))
        c = self.commit(b"e\n\ntrail e\n", "2026-10-06T16:00:00+00:00",
                        parents=(b,))
        self.commit(b"eE\n", "2026-10-07T08:00:00+00:00", parents=(b, c))
        process, path = self.rust()
        self.assertEqual(process.returncode, 0, process.stderr)
        observed = json.loads(path.read_text())
        expected = self.python()
        self.assertEqual(observed["rows"], expected["rows"])
        self.assertEqual(observed["source"]["total_count"], expected["source"]["total_count"])
        self.assertEqual(observed["source"]["total_commits"], expected["source"]["total_commits"])
        self.assertEqual(observed["source"]["commits"], expected["source"]["commits"])
        result = subprocess.run(["python3", str(VERIFY), "--repo", str(self.repo),
                                 "--data", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["verified"])

    def test_zero_days_and_pinned_history(self):
        initial = self.commit(b"e\n", "2026-10-04T00:00:00+00:00")
        process, path = self.rust()
        self.assertEqual(process.returncode, 0, process.stderr)
        observed = json.loads(path.read_text())
        self.assertEqual(len(observed["rows"]), 7)
        self.assertEqual([r["count"] for r in observed["rows"]], [1, 0, 0, 0, 0, 0, 0])
        self.commit(b"eeeee\n", "2026-10-10T00:00:00+00:00", parents=(initial,))
        pinned = self.path / "pinned.json"
        result = subprocess.run(
            [self.binary, "--repo", str(self.repo), "--ref", initial,
             "--repository", "fixture/project", "--since", "7d", "--end", "2026-10-11",
             "--out", str(pinned)], capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(pinned.read_text())["source"]["total_count"], 1)

    def test_shallow_rejected_and_bad_since(self):
        head = self.commit(b"ee", "2026-10-08T12:00:00+00:00")
        (self.repo / ".git" / "shallow").write_text(head + "\n")
        process, path = self.rust()
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("shallow", process.stderr)
        self.assertFalse(path.exists())
        (self.repo / ".git" / "shallow").unlink()
        for tail in (("--since", "2d"), ("--days", "4"), ("--start", "2026-10-04")):
            with self.subTest(tail=tail):
                process, path = self.rust(*tail)
                self.assertNotEqual(process.returncode, 0)
                self.assertFalse(path.exists())

if __name__ == "__main__":
    unittest.main()
