"""Actual CLI/FFmpeg tests, enabled by EBALLS_BIN after a Rust build."""
import json
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

BINARY = os.environ.get("EBALLS_BIN")


def png(path):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    pixels = (b"\0" + bytes([20, 80, 150]) * 64) * 64
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


@unittest.skipUnless(BINARY, "set EBALLS_BIN to run compiled renderer tests")
class RenderCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "input.json"
        self.avatar = self.root / "face.png"
        png(self.avatar)
        self.value = {"schema_version": 1, "title": "Synthetic smoke test", "subtitle": "not real counts",
                      "footer": "test fixture", "unit": "e's", "unit_singular": "e",
                      "rows": [{"label": "Sunday", "count": 20}, {"label": "Monday", "count": 1},
                               {"label": "Tuesday", "count": 0}], "source": {"fixture": True}}

    def run_cli(self, *extra, env=None):
        self.data.write_text(json.dumps(self.value), encoding="utf-8")
        return subprocess.run([str(Path(BINARY).resolve()), "--data", str(self.data), "--avatar", str(self.avatar),
                               "--out", str(self.root / "out"), "--width", "320", "--fps", "15",
                               "--duration", "0.4", *extra], capture_output=True, text=True, env=env, timeout=40)

    def test_both_media_decode_and_receipts_survive(self):
        proc = self.run_cli()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = self.root / "out"
        self.assertEqual((out / "data.json").read_bytes(), self.data.read_bytes())
        manifest = json.loads((out / "manifest.json").read_text())
        self.assertEqual(manifest["rows"], [["Sunday", 20], ["Monday", 1], ["Tuesday", 0]])
        self.assertTrue((out / "avatar.png").exists())
        for suffix, width in [("mp4", 320), ("gif", 480)]:
            file = out / f"e-balls.{suffix}"
            meta = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-show_format",
                                                      "-of", "json", str(file)]))
            self.assertEqual(meta["streams"][0]["width"], width)
            self.assertEqual(meta["streams"][0]["height"], width)
            self.assertAlmostEqual(float(meta["format"]["duration"]), 0.4, delta=0.1)
            subprocess.run(["ffmpeg", "-v", "error", "-xerror", "-i", str(file), "-f", "null", "-"], check=True)
            frame = subprocess.check_output([
                "ffmpeg", "-v", "error", "-i", str(file), "-frames:v", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
            ])
            self.assertEqual(len(frame), width * width * 3)
            # Lossy H.264/YUV and GIF palettes need a small color tolerance.
            for actual, expected in zip(frame[:3], [245, 241, 232]):
                self.assertLessEqual(abs(actual - expected), 4)
            # Restrict ink checks to the title, excluding the blue portrait.
            # At 320px YUV420 averages thin glyphs with cream; GIF keeps RGB.
            title = frame[:width * (width // 5) * 3]
            pixels = zip(title[0::3], title[1::3], title[2::3])
            tolerance = 40 if suffix == "mp4" else 12
            self.assertGreater(sum(all(abs(c - e) <= tolerance for c, e in zip(p, [21, 107, 118]))
                                   for p in pixels), 10, suffix)


    def test_all_zeroes_still_render(self):
        for row in self.value["rows"]:
            row["count"] = 0
        proc = self.run_cli("--format", "mp4")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_no_portrait_fallback(self):
        self.avatar.write_bytes(b"not an image")
        proc = self.run_cli()
        self.assertNotEqual(proc.returncode, 0)
        self.assertFalse((self.root / "out").exists())

    def test_rejects_invalid_counts_before_creating_output(self):
        for bad in [-1, 1.5, True, 2**64]:
            with self.subTest(count=bad):
                self.value["rows"][0]["count"] = bad
                self.assertNotEqual(self.run_cli().returncode, 0)
                self.assertFalse((self.root / "out").exists())

    def test_existing_output_is_untouched(self):
        out = self.root / "out"
        out.mkdir()
        sentinel = out / "keep.txt"
        sentinel.write_text("keep")
        self.assertNotEqual(self.run_cli().returncode, 0)
        self.assertEqual(sentinel.read_text(), "keep")

    def test_ffmpeg_failure_leaves_no_completed_or_staging_output(self):
        empty_path = self.root / "empty-path"
        empty_path.mkdir()
        env = dict(os.environ, PATH=str(empty_path))
        self.assertNotEqual(self.run_cli(env=env).returncode, 0)
        self.assertFalse((self.root / "out").exists())
        self.assertFalse(list(self.root.glob(".e-balls-*")))


if __name__ == "__main__":
    unittest.main()
