"""Literal strings through raw Git collection, independent recount and real media."""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from count_letters import collect, write_json
from verify_counts import verify

START, END = dt.date(2026, 10, 4), dt.date(2026, 10, 11)
MESSAGES = [
    b"Fix: fix: FIX: eE qQ aa aaaaaa a.* a+b [] $(touch escaped) --out\n\nbody\r\ntrailers\n",
    "café CAFÉ é É e\u0301 🦀🦀 🦀 café newline\n\nend".encode(),
    b"\xfffix: invalid utf8 still has FIX: bytes\n",
    b"fi",
    b"x:",  # Neither message may complete the other's partial match.
]
PATTERNS = ["e", "Q", "fix:", "Fix:", "aa", "a.*", "a+b", "[]", "--out",
            "$(touch escaped)", " ", "\n\n", "\r\n", "é", "É", "café", "🦀", "🦀 café",
            "x" * 1024]


class LiteralFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q", "-b", "main")
        tree = self.git("mktree", input=b"").decode().strip()
        parent = ""
        for index, body in enumerate(MESSAGES):
            epoch = 1791072000 + index * 86400
            headers = (f"tree {tree}\n{parent}author Author{index} <person{index}@example.test> {epoch} +0000\n"
                       f"committer Counter <counter@example.test> {epoch} +0000\n\n")
            sha = self.git("hash-object", "-t", "commit", "-w", "--stdin", input=headers.encode() + body).decode().strip()
            parent = f"parent {sha}\n"
        self.pin = sha
        self.git("update-ref", "refs/heads/main", sha)

    def git(self, *args, input=None):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], input=input)

    def expected(self, text, sensitive):
        needle = text.encode()
        if not sensitive:
            needle = needle.lower()
        return [(body if sensitive else body.lower()).count(needle) for body in MESSAGES] + [0, 0]

    def reference(self, text="e", sensitive=False):
        return collect(self.repo, self.pin, START, END, "fixture/project", "project",
                       text=text, case_sensitive=sensitive)


class ReferenceStringTests(LiteralFixture):
    def test_every_literal_reconciles_with_independent_git_recount(self):
        for text in PATTERNS:
            for sensitive in (False, True):
                with self.subTest(text=text, sensitive=sensitive):
                    data = self.reference(text, sensitive)
                    self.assertEqual([r["count"] for r in data["rows"]], self.expected(text, sensitive))
                    self.assertEqual(data["source"]["matcher"]["text"], text)
                    self.assertNotIn("\n", data["title"])
                    self.assertLessEqual(len(data["title"]), 240)
                    self.assertLessEqual(len(data["unit"]), 24)
                    path = self.root / "data.json"
                    write_json(path, data)
                    self.assertTrue(verify(self.repo, path)["verified"])

    def test_old_letter_snapshots_remain_verifiable(self):
        data = self.reference()
        del data["source"]["matcher"]
        path = self.root / "legacy.json"
        write_json(path, data)
        self.assertTrue(verify(self.repo, path)["verified"])

    def test_empty_text_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "nonempty"):
            self.reference("")

    def test_semantics_cannot_be_changed_silently(self):
        good = self.reference("Fix:", True)
        edits = [("text", ""), ("text", 0), ("case", "unicode-insensitive"),
                 ("overlapping", True), ("overlapping", 0), ("kind", "regex"), ("extra", "ignored?")]
        for key, value in edits:
            with self.subTest(key=key, value=value):
                bad = copy.deepcopy(good)
                bad["source"]["matcher"][key] = value
                path = self.root / "bad.json"
                write_json(path, bad)
                with self.assertRaises(ValueError):
                    verify(self.repo, path)
        for altered in ["fix:", "whatever"]:
            bad = copy.deepcopy(good)
            bad["source"]["matcher"]["text"] = altered
            path = self.root / "tampered.json"
            write_json(path, bad)
            with self.assertRaisesRegex(ValueError, "mismatch|receipts"):
                verify(self.repo, path)


@unittest.skipUnless(os.environ.get("EBALLS_COLLECT_BIN"), "set EBALLS_COLLECT_BIN for compiled integration")
class RustStringTests(LiteralFixture):
    def collector(self, *args):
        out = self.root / "rust.json"
        out.unlink(missing_ok=True)
        process = subprocess.run([str(Path(os.environ["EBALLS_COLLECT_BIN"]).resolve()),
            "--repo", str(self.repo), "--ref", self.pin, "--repository", "fixture/project",
            "--project", "project", "--since", "7d", "--end", END.isoformat(), "--out", str(out), *args],
            capture_output=True, text=True, timeout=20)
        return process, out

    def test_rust_literals_match_reference_and_recount(self):
        for text in PATTERNS:
            for sensitive in (False, True):
                with self.subTest(text=text, sensitive=sensitive):
                    args = [f"--text={text}"] + (["--case-sensitive"] if sensitive else [])
                    result, path = self.collector(*args)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    actual = json.loads(path.read_text())
                    expected = self.reference(text, sensitive)
                    self.assertEqual(actual, expected)
                    self.assertEqual([r["count"] for r in actual["rows"]], self.expected(text, sensitive))
                    self.assertTrue(verify(self.repo, path)["verified"])

    def test_old_alias_and_default_mean_the_same_thing(self):
        result, path = self.collector()
        self.assertEqual(result.returncode, 0, result.stderr)
        default = json.loads(path.read_text())
        result, path = self.collector("--letter=e")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(path.read_text()), default)
        result, path = self.collector("--letter=fix:")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(path.read_text()), self.reference("fix:"))

    def test_empty_and_conflicting_options_fail_without_snapshot(self):
        for args in [("--text=",), ("--text=a", "--letter=b")]:
            with self.subTest(args=args):
                result, path = self.collector(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(path.exists())

    @unittest.skipUnless(os.environ.get("EBALLS_BIN"), "set EBALLS_BIN for actual media")
    def test_literal_snapshot_renders_replays_and_freezes_full_matcher(self):
        renderer = str(Path(os.environ["EBALLS_BIN"]).resolve())
        avatar = ROOT / "examples/perl-lsp-2026-10-04-teal/avatar.png"
        for index, text in enumerate(["fix:", "\n\n", "🦀 café", "x" * 1024]):
            result, path = self.collector(f"--text={text}")
            self.assertEqual(result.returncode, 0, result.stderr)
            snapshot = path.read_bytes()
            outputs = []
            for replay in range(2):
                out = self.root / f"clip-{index}-{replay}"
                result = subprocess.run([renderer, "--data", str(path), "--avatar", str(avatar),
                    "--out", str(out), "--format", "both", "--duration", "0.2", "--width", "320"],
                    env={**os.environ, "GITHUB_OUTPUT": str(self.root / f"outputs-{index}-{replay}")},
                    capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((out / "data.json").read_bytes(), snapshot)
                manifest = json.loads((out / "manifest.json").read_text())
                self.assertEqual(manifest["matcher"]["text"], text)
                self.assertEqual(manifest["matcher"], json.loads(snapshot)["source"]["matcher"])
                outputs.append(out)
                for suffix in ["gif", "mp4"]:
                    subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(out / f"e-balls.{suffix}"),
                                    "-f", "null", "-"], check=True, capture_output=True, timeout=20)
            for suffix in ["gif", "mp4"]:
                self.assertEqual((outputs[0] / f"e-balls.{suffix}").read_bytes(), (outputs[1] / f"e-balls.{suffix}").read_bytes())


if __name__ == "__main__":
    unittest.main()
