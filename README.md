# e-balls

Occurrences of the letter `e` in perl-lsp commit messages, per day.
Same head on every ball.

A fork of [Maria's Release Balls](https://github.com/maria-rcks/release-balls).
The bouncing animation, circular portraits, white canvas, and FFmpeg exports
are retained. The rows are days instead of contributors, and the counts are
letters instead of pull requests.

## Make the clip

Requires Rust 1.88+, Python 3.10+, Git, FFmpeg, and FreeType headers
(`libfreetype6-dev` and `pkg-config` on Ubuntu).

```sh
cargo build --release --locked --bins

# Use an existing full checkout, or fetch commit history without file blobs.
git clone --bare --filter=blob:none --single-branch --branch main --no-tags \
  https://github.com/EffortlessMetrics/perl-lsp-swarm.git ../perl-lsp-history.git

python3 scripts/count_letters.py \
  --repo ../perl-lsp-history.git \
  --ref 31b87ee79b8fb55b6433bed7c1f1e4478443d61e \
  --repository EffortlessMetrics/perl-lsp-swarm --project perl-lsp \
  --start 2026-10-04 --end 2026-10-11 --out e-counts.json

# Independently recount the frozen snapshot from individual Git objects.
python3 scripts/verify_counts.py --repo ../perl-lsp-history.git --data e-counts.json

curl --fail --location 'https://avatars.githubusercontent.com/u/15812269?v=4&s=512' \
  --output steven.png

./target/release/e-balls --data e-counts.json --avatar steven.png --out out
```

`out/e-balls.mp4` is 1080×1080 at 60 fps. `out/e-balls.gif` is 480×480 at
15 fps. Both run for 16 seconds by default. The output also includes the exact
input JSON, the portrait used, and a render manifest. Existing output
directories are refused; use a new `--out` path for another render.

Rendering is offline. It does not look up avatars from row labels. An unreadable
portrait is an error, not permission to replace your head with initials.

To measure the last seven **completed UTC days**, replace the pinned `--ref`
with the source's current branch and omit `--start` and `--end`. The collector
records the resolved commit SHA before reading. `--days`, `--end`, and
`--letter` select other windows or ASCII letters.

## What gets counted

We count ASCII `e` and `E` in the **full raw commit message**, including the
subject, body, and trailers. Commit headers, diffs, code, PR comments, and
unmerged branch tips do not count. Accented letters are not folded into `e`.

Dates are UTC **committer** dates, not author dates or inferred merge times.
The start is inclusive and the end is exclusive: the example above covers
October 4–10, 2026. Empty days remain as zero rows. Shallow histories fail
rather than quietly producing incomplete figures.

All commits reachable from the pinned ref count once by SHA, including merge
commits and merged branch ancestry. This is not a first-parent view and not a
PR count. The collector walks the entire ancestry before filtering dates so
out-of-order commit timestamps cannot truncate the result.

The source is `EffortlessMetrics/perl-lsp-swarm`, the development repository
for perl-lsp. The source repository is shown in the footer; the JSON records
the ref, full SHA, window, counting rules, per-commit counts, and message
SHA-256 digests. All authors are included. Repeating Steven's portrait does
not turn this into an authorship claim.

Rows remain in input order. Speed is linear relative to the largest count;
the fastest ball crosses the arena in one second. A zero stays still. A small
count really does barely move. There is no minimum speed or log scale.

## Other ridiculous metrics

Supply your own ordered JSON rather than inventing PR records:

```json
{
  "schema_version": 1,
  "title": "Synthetic example, not repository data",
  "subtitle": "Any ordered labels and nonnegative integer counts",
  "footer": "Your actual source",
  "unit": "e's",
  "unit_singular": "e",
  "rows": [
    {"label": "Monday", "count": 12},
    {"label": "Tuesday", "count": 3},
    {"label": "Wednesday", "count": 0}
  ]
}
```

Extra fields such as source receipts are preserved in the output snapshot.
Labels, titles, units, and the portrait are independent. `--format mp4|gif|both`,
`--duration`, `--width`, and `--fps` control export; GIF delivery stays 480px/15fps.
Run `./target/release/e-balls --help` for all options.

## Checks and attribution

The fork's CI runs Git fixture tests, Rust tests, actual CLI/FFmpeg tests, and
a pinned perl-lsp render. Media and verification receipts are uploaded as
artifacts, not posted or attached to a release. No perl-lsp workflow is changed.
All work and PRs belong in **EffortlessSteven/e-balls**, not Maria's repository.

The original `release-balls` CLI and `action.yml` remain available for PR/release
races; their documentation is in [docs/releases.md](docs/releases.md). The new
letter-counter path uses `e-balls`, not that legacy action.

MIT. Maria's copyright and license are retained in [LICENSE](LICENSE).
Bundled asset notices remain in [assets/README.md](assets/README.md).
