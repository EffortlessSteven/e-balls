import datetime as dt
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("count_letters", ROOT / "scripts/count_letters.py")
assert spec and spec.loader
counter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(counter)
START, END = dt.date(2026, 10, 4), dt.date(2026, 10, 11)


class CounterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.run_git("init", "-q")
        self.tree = self.run_git("mktree", input=b"").decode().strip()

    def run_git(self, *args, input=None):
        return counter.git(self.repo, *args, input=input)

    def commit(self, message, when="2026-10-05T12:00:00+00:00", parents=(), author_time=1):
        stamp = int(dt.datetime.fromisoformat(when).timestamp())
        headers = f"tree {self.tree}\n" + "".join(f"parent {p}\n" for p in parents)
        headers += f"author E Header <e@invalid> {author_time} +0000\n"
        headers += f"committer E Header <e@invalid> {stamp} +0000\n\n"
        sha = self.run_git("hash-object", "-t", "commit", "-w", "--stdin",
                           input=headers.encode() + message).decode().strip()
        self.run_git("update-ref", "refs/heads/main", sha)
        return sha

    def collect(self, ref="main", **kwargs):
        return counter.collect(self.repo, ref, kwargs.pop("start", START), kwargs.pop("end", END),
                               "example/project", "perl-lsp", **kwargs)

    def test_full_message_case_and_unicode(self):
        self.commit("fix: e\n\nEE e\né è Ê\n\nCo-authored-by: Eve\n".encode())
        data = self.collect()
        self.assertEqual(data["source"]["total_count"], 7)
        self.assertEqual(data["rows"][1]["count"], 7)
        self.assertEqual(data["source"]["total_commits"], 1)

    def test_zero_days_are_chronological(self):
        self.commit(b"xyz\n")
        data = self.collect()
        self.assertEqual(len(data["rows"]), 7)
        self.assertEqual([r["date"] for r in data["rows"]],
                         [(START + dt.timedelta(days=i)).isoformat() for i in range(7)])
        self.assertEqual([r["count"] for r in data["rows"]], [0] * 7)
        self.assertEqual(data["rows"][1]["commits"], 1)

    def test_committer_not_author_and_utc(self):
        self.commit(b"e", "2026-10-04T22:00:00-07:00", author_time=999999999)
        rows = self.collect()["rows"]
        self.assertEqual(rows[0]["count"], 0)
        self.assertEqual(rows[1]["count"], 1)

    def test_half_open_window(self):
        a = self.commit(b"e", "2026-10-03T23:59:59+00:00")
        b = self.commit(b"ee", "2026-10-04T00:00:00+00:00", (a,))
        c = self.commit(b"eee", "2026-10-10T23:59:59+00:00", (b,))
        self.commit(b"eeee", "2026-10-11T00:00:00+00:00", (c,))
        data = self.collect()
        self.assertEqual(data["source"]["total_count"], 5)
        self.assertEqual(data["source"]["total_commits"], 2)

    def test_nonmonotonic_ancestors_are_not_pruned(self):
        a = self.commit(b"eee", "2026-10-05T12:00:00+00:00")
        b = self.commit(b"eeee", "2026-01-01T12:00:00+00:00", (a,))
        self.commit(b"e", "2026-10-06T12:00:00+00:00", (b,))
        self.assertEqual(self.collect()["source"]["total_count"], 4)

    def test_merge_includes_each_shared_ancestor_once(self):
        root = self.commit(b"e")
        a = self.commit(b"ee", parents=(root,))
        b = self.commit(b"eee", parents=(root,))
        self.commit(b"eeee", parents=(a, b))
        data = self.collect()
        self.assertEqual(data["source"]["total_count"], 10)
        self.assertEqual(data["source"]["total_commits"], 4)
        self.assertEqual(len({c["sha"] for c in data["source"]["commits"]}), 4)

    def test_unreachable_work_does_not_count(self):
        pin = self.commit(b"e")
        self.commit(b"eeeeeeee")
        self.assertEqual(self.collect(pin)["source"]["total_count"], 1)

    def test_raw_delimiters_are_message_content(self):
        self.commit(b"e\ne\x1ee\x1fe\n\nEe")
        self.assertEqual(self.collect()["source"]["total_count"], 6)

    def test_replay_pinned_revision_is_identical(self):
        pin = self.commit(b"eE")
        before = self.collect(pin)
        self.commit(b"eeeeeeee", parents=(pin,))
        self.assertEqual(before, self.collect(pin))

    def test_replacements_are_ignored(self):
        pin = self.commit(b"e")
        replacement = self.commit(b"eeee")
        self.run_git("replace", pin, replacement)
        self.assertEqual(self.collect(pin)["source"]["total_count"], 1)

    def test_other_ascii_letter(self):
        self.commit(b"Aa ee a")
        self.assertEqual(self.collect(letter="A")["source"]["total_count"], 3)

    def test_invalid_letter_and_window(self):
        self.commit(b"e")
        for letter in ["", "ee", "é", "1"]:
            with self.subTest(letter=letter), self.assertRaises(ValueError):
                self.collect(letter=letter)
        for end in [START, START - dt.timedelta(days=1), START + dt.timedelta(days=367)]:
            with self.subTest(end=end), self.assertRaises(ValueError):
                self.collect(end=end)

    def test_empty_window_is_not_missing_history(self):
        self.commit(b"e", "2026-01-01T00:00:00+00:00")
        self.assertEqual(self.collect()["source"]["total_commits"], 0)

    def test_shallow_clone_is_rejected(self):
        self.commit(b"e")
        (self.repo / ".git/shallow").write_text(self.run_git("rev-parse", "main").decode())
        with self.assertRaisesRegex(ValueError, "shallow"):
            self.collect()

    def test_cli_and_output(self):
        self.commit(b"eE")
        output = Path(self.tmp.name) / "output" / "data.json"
        proc = subprocess.run([
            "python3", str(ROOT / "scripts/count_letters.py"), "--repo", str(self.repo),
            "--ref", "main", "--repository", "example/project", "--start", START.isoformat(),
            "--end", END.isoformat(), "--out", str(output),
        ], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(output.read_text())["source"]["total_count"], 2)


if __name__ == "__main__":
    unittest.main()
