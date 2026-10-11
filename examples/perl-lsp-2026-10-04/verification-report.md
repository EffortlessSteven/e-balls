# Pinned perl-lsp e-balls: executed verification

Executed on 2026-10-11 in EffortlessSteven/e-balls. All recipe build/test commands
passed. The actual MP4 and GIF are included alongside this report.

## Source and scope

PR: https://github.com/EffortlessSteven/e-balls/pull/1

The API-retrieved PR head and clean initial checkout both matched
`bdaca6256357208d3a1a383b280165da007f5e6e` before editing. The retrieved description
and changes are in [evidence/pr-context.json](evidence/pr-context.json).

The tested source is that revision **plus formatting-only changes** in
`src/bin/e-balls.rs` and `src/render.rs`, produced by `cargo fmt --all`.
[evidence/tested-source.patch](evidence/tested-source.patch) and
[evidence/tested-inputs.json](evidence/tested-inputs.json) identify the exact patch
and all 29 tracked source/test/config/dependency/asset files. No rendering behavior,
framework, dependency, license or attribution was changed. Existing font assets
were used for rendering; no font files or compiler binaries are in this bundle.

## Build and tests

All commands ran from the e-balls repository root. Toolchain: Rust/Cargo 1.88.0,
Python 3.12.15, Git 2.49.0, FreeType development package 2.13.2, pkg-config 1.8.0,
FFmpeg/ffprobe 7.0.2. Exact versions and installation transcripts are in evidence.

| Command | Exit | Observed outcome | Transcript |
| --- | --- | --- | --- |
| `cargo fmt --all` | 0 | Formatted two files | [log](evidence/cargo-fmt.log) |
| `cargo fmt --all -- --check` | 0 | Passed | [log](evidence/fmt-check.log) |
| `cargo clippy --release --locked --all-targets -- -D warnings` | 0 | Passed, warnings denied | [log](evidence/clippy-1.log) |
| `cargo test --locked --all-targets` | 0 | 7 test executions passed, 0 ignored | [log](evidence/rust-tests.log) |
| `cargo build --release --locked --bins` | 0 | Both binaries built | [log](evidence/release-build.log) |
| `EBALLS_BIN=$PWD/target/release/e-balls python3 -m unittest discover -s tests -v` | 0 | 33 passed, 0 skipped, including all 6 CLI/media tests | [log](evidence/python-tests.log) |

The renderer module's two Rust tests execute in both the library and original
binary targets; the 7 executions represent 5 distinct test functions.
There were no failed recipe build/test commands and no blocked checks.

## Real pinned counts

Read-only full commit ancestry clone: `EffortlessMetrics/perl-lsp-swarm`.
Pin: `31b87ee79b8fb55b6433bed7c1f1e4478443d61e`.
UTC committer window: **2026-10-04 inclusive to 2026-10-11 exclusive**.

The clone is not shallow. The pin has 12,422 reachable commits; 129 fall within
this window. Counted ASCII e/E in full raw messages, including bodies and
trailers, with merged ancestry and each SHA once. Independent raw-object
verification agreed with all daily totals and per-commit message hashes.

| UTC day | Commits | e/E count |
| --- | ---: | ---: |
| 2026-10-04 | 39 | 5,773 |
| 2026-10-05 | 40 | 5,691 |
| 2026-10-06 | 25 | 3,809 |
| 2026-10-07 | 15 | 3,292 |
| 2026-10-08 | 5 | 109 |
| 2026-10-09 | 1 | 4 |
| 2026-10-10 | 4 | 734 |
| **Total** | **129** | **19,412** |

See [data.json](data.json) for the 129 receipts and
[count-verification.json](count-verification.json) for the independent result.
All authors are included; the repeated portrait is presentation, not authorship.

## Actual media verification

| File | Codec | Dimensions | Frames | Duration | Rate |
| --- | --- | --- | ---: | ---: | --- |
| [e-balls.mp4](e-balls.mp4) | H.264 / yuv420p | 1080 × 1080 | 960 | 16.000 s | 60 fps |
| [e-balls.gif](e-balls.gif) | GIF | 480 × 480 | 240 | 16.000 s | 15 fps effective |

Both files fully decoded with `ffmpeg -v error -xerror ... -f null -`, exit 0.
The [MP4 probe](mp4-probe.json) and [GIF probe](gif-probe.json) include decoded
frame counts. FFprobe reports GIF `r_frame_rate=15/1` and
`avg_frame_rate=50/3`; the actual 240 frames use 0.06/0.07-second delays totaling
16.000 seconds, verified in [gif-frame-timing.json](gif-frame-timing.json).
The centisecond GIF timebase accounts for its alternating frame delays.

Visually inspected four sampled frames from each output, arranged left to right,
then top to bottom in [MP4 samples](evidence/mp4-samples.png) and
[GIF samples](evidence/gif-samples.png). Dates and counts are readable and in
chronological order; all seven balls show the supplied circular portrait; the
source footer is visible; faster and slower rows change position as expected.
The four-e row barely moves. No clipping, missing rows or corrupt frames was
observed in these samples. This is sampled inspection, not every-frame visual
inspection. [preview.png](preview.png) is the MP4 frame at 0.5 seconds.

Portrait URL: https://avatars.githubusercontent.com/u/15812269?v=4&s=512

The endpoint actually returned a **460 × 460 JPEG**, preserved unchanged as
`evidence/supplied-avatar.png` (the original workflow uses a PNG filename).
The renderer decoded it and wrote `avatar.png` as RGB PNG. An additional
verification initially demanded identical RGB bytes across FFmpeg and Rust JPEG
decoders and failed (exit 1, `media-assertions.log`). Independent decoder rounding
and chroma interpolation make that requirement inappropriate. The corrected
comparison measured mean absolute channel difference 0.853/255 and PSNR 46.79 dB
(acceptance: MAE < 2 and PSNR > 40 dB), with matching dimensions and visual review.
A second diagnostic attempt failed (exit 1, `media-assertions-2.log`) because
FFmpeg 7 exposes frame `duration_time`, not `pkt_duration_time`; that diagnostic
was corrected. Both failed scripts/transcripts are retained. The final
`media-assertions-3.log` passed (exit 0); [media-verification.json](media-verification.json)
records its result. No renderer changes or regenerated media were needed.

## Reproduction and integrity

Use the pinned-example commands in `.github/workflows/ci.yml`, selecting the
same pin/window and downloaded portrait, with a new output directory. Activate
Rust 1.88.0/Python 3.12.15 and an FFmpeg build with libx264; the sandbox's system
FFmpeg and Python 3.9 were unsuitable. [evidence/README.md](evidence/README.md)
explains the exact command records and environment. Downloading that avatar URL
later can return a different image; use the preserved supplied portrait for replay.

From this directory, run `sha256sum -c SHA256SUMS`. Checksums cover all bundle
files except SHA256SUMS itself and its own `evidence/sha256-check.log/.json`
transcript, which would otherwise be self-referential. Source and media checks
completed before packaging, with no source changes after testing.

Rendering derives from [Maria's Release Balls](https://github.com/maria-rcks/release-balls),
MIT, copyright (c) 2026 maria-rcks. The existing repository LICENSE and asset
attribution are retained. Maria's circular portraits, white canvas, linear
speeds, bouncing behavior and FFmpeg export remain intact.

No commit, push, PR, merge or release was performed, following the final task
instruction. The prepared changes remain on the assigned local task branch.
