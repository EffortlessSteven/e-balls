# Teal/cream pinned week

Renderer starts at PR #4 head `c1425299af74ba21afd58832d85b2d0b67dc1c28`.
Implementation is an uncommitted workspace patch: see `renderer-source.json`,
`evidence/source.patch`, and per-check `evidence/inputs-*.json` SHA-256 maps.
No commit, push, follow-up PR, merge, release, or upstream write was performed.

## Source and reproduction

The complete read-only source history was cloned from
`https://github.com/EffortlessMetrics/perl-lsp-swarm.git` into
`/tmp/e-balls-perl-history.git` using `git clone --bare --filter=blob:none
--single-branch --branch main --no-tags`. Full history was verified (not shallow).
The pinned commit is `31b87ee79b8fb55b6433bed7c1f1e4478443d61e`.

```sh
python3 scripts/count_letters.py --repo /tmp/e-balls-perl-history.git \
  --ref 31b87ee79b8fb55b6433bed7c1f1e4478443d61e \
  --repository EffortlessMetrics/perl-lsp-swarm --project perl-lsp \
  --since 7d --end 2026-10-11 --out /tmp/e-balls-counts.json
python3 scripts/verify_counts.py --repo /tmp/e-balls-perl-history.git \
  --data /tmp/e-balls-counts.json
target/release/e-balls --data /tmp/e-balls-counts.json \
  --avatar examples/perl-lsp-2026-10-04/avatar.png \
  --format both --duration 16 --width 1080 --fps 60 --out <new-directory>
```

129 reachable commits; 19,412 e/E occurrences. Daily counts:
5773, 5691, 3809, 3292, 109, 4, 734. Independent raw-object recount passed.
Data JSON is byte-identical to the old example; portrait pixels match exactly.
All 83 old example files remain byte-identical. README opening, exact caption,
and 96px right-aligned placement are preserved.

## Checks

All commands ran in this fork with Rust 1.88.0, Python 3.12.15, Git 2.49.0,
FFmpeg/ffprobe 7.0.2 with libx264, and system FreeType.
Exact argv, working directory, input identities, statuses and logs are under
`evidence/`. No previous task's passing checks were substituted.

- `cargo fmt --all` and `cargo fmt --all -- --check`: passed.
- `cargo clippy --release --locked --all-targets -- -D warnings`: passed.
- `cargo test --locked --all-targets`: 14 test executions passed.
- `cargo build --release --locked --bins`: both binaries built.
- `EBALLS_BIN=$PWD/target/release/e-balls python3 -m unittest discover -s tests -v`:
  final run passed all 36 tests, none skipped. First run found one overly strict
  small H.264 text-color assertion. Actual decoded pixels were inspected; the
  assertion now accounts for YUV420 chroma averaging, limits the inspected region
  to the title, and retains stricter GIF and exact Rust RGB checks. Both logs remain.
- Full FFmpeg `-xerror` decodes passed for both streams. MP4: 1080×1080,
  60 fps, 960 frames, 16 seconds. GIF: 480×480, 240 frames, 16 seconds;
  60/70ms delays implement 15 fps with GIF centisecond timing.
- Actual preview and both contact sheets inspected at 0, 0.5, 1, 3.5, 8 and
  15.9 seconds: readable teal text, cream canvas, preserved portrait, chronological
  rows and expected bounce behavior; no visible white trails or chroma stripes.
  Exact dirty/YUV parity, sprite edge, sparse downsampling, transparency, font,
  linear-speed and portrait-sharing regressions passed.

`manifest.json` records the theme and official IBM/plex font sources and hashes;
licenses remain in source assets. No font files or executable binaries are in this
example or its delivery archive. `SHA256SUMS` covers the evidence and media.

## About metadata

Unsupported: `gh repo edit --help` returned exit 89,
`CODERABBIT_AGENT_RUNTIME_OWNS_GIT_DELIVERY`: “GitHub repo is unavailable inside
this Coding task because CodeRabbit owns remote branch and pull request delivery.”
No authorized metadata tool was exposed. No permissions were changed.
