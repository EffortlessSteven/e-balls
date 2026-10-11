<img src="assets/logo.svg" alt="" width="96" align="right">

# e-balls

A tool that turns a week of [perl-lsp](https://github.com/EffortlessMetrics/perl-lsp) commit messages into a short race between days. Each day is a ball with Steven's avatar; the more occurrences of `e` it has, the faster it goes. You get a GIF, an MP4, and the counts as JSON.

![Top 7 perl-lsp days in the past week](examples/perl-lsp-2026-10-04-teal/e-balls.gif)

*Top 7 perl-lsp days in the past week, rendered with `since: 7d`.*

October 4–10, 2026 (UTC). [MP4](examples/perl-lsp-2026-10-04-teal/e-balls.mp4).

## Quick start

Build the Rust binary and render the example:

```sh
cargo build --release --locked --bins
./target/release/e-balls \
  --data examples/perl-lsp-2026-10-04-teal/data.json \
  --avatar examples/perl-lsp-2026-10-04-teal/avatar.png
```

Files go to `out/`.

## Render without publishing

To get the files as a workflow artifact instead, run [CI](https://github.com/EffortlessSteven/e-balls/actions/workflows/ci.yml) on demand. The workflow:

1. Counts the `e`s committed each day in the example week.
2. Renders the GIF and MP4.
3. Uploads the media and counts as the `e-balls-perl-lsp-workflow_dispatch` artifact.

## Rank a time window

Set `--since 7d` to count the `e`s committed in the past week. The title reads "Occurrences of 'e' in perl-lsp commit messages".

```sh
python3 scripts/count_letters.py \
  --repo ../perl-lsp-history.git --ref main \
  --repository EffortlessMetrics/perl-lsp-swarm \
  --since 7d --out data.json
```

The window covers seven completed UTC days. Set `--end 2026-10-11` to reproduce the example week.

## Inputs

For `scripts/count_letters.py`:

| Input | Default | What it does |
| --- | --- | --- |
| `--repo` | required | Local Git checkout or bare repository to read. |
| `--repository` | required | Source `owner/repo`, shown in the footer. |
| `--ref` | `HEAD` | Branch or commit to read. |
| `--since` | unset | `7d` selects the past week. |
| `--letter` | `e` | Letter to count. |
| `--end` | today | Exclusive UTC end date. |
| `--out` | required | Output JSON file. |

For `e-balls`:

| Input | Default | What it does |
| --- | --- | --- |
| `--data` | required | JSON with the daily counts. |
| `--avatar` | required | Local portrait to use for every day. |
| `--format` | `both` | `gif`, `mp4`, or `both`. |
| `--out` | `out` | New output directory. |

## Outputs

All outputs are paths in the output directory.

| Output | Contents |
| --- | --- |
| `e-balls.gif` | Animated GIF. |
| `e-balls.mp4` | MP4 video. |
| `manifest.json` | Daily counts and generated file paths. |
| `data.json` | A snapshot of the commit messages' letter counts. |
| `avatar.png` | The portrait used for each ball. |

To use the files in another job, upload the output directory as an artifact.

## What gets counted

- Only `e` and `E` in commit messages count.
- A commit present in several merged branches counts once.
- All authors are included.
- The seven days are shown in calendar order, using UTC committer dates. Empty days stay still.
- The fastest ball crosses in one second, so speeds are relative within a clip. Clips last 16 seconds. MP4 is 1080px at 60fps, GIF is 480px at 15fps.

## Run it locally

Needs Rust 1.88+, Python 3.10+, Git, FFmpeg, and FreeType headers (`libfreetype6-dev` and `pkg-config` on Ubuntu).

```sh
cargo build --release --locked --bins

git clone --bare --filter=blob:none --single-branch --branch main --no-tags \
  https://github.com/EffortlessMetrics/perl-lsp-swarm.git ../perl-lsp-history.git

python3 scripts/count_letters.py \
  --repo ../perl-lsp-history.git --ref main \
  --repository EffortlessMetrics/perl-lsp-swarm \
  --since 7d --out data.json

./target/release/e-balls --data data.json \
  --avatar examples/perl-lsp-2026-10-04-teal/avatar.png --format both
```

Files go to `out/`. Useful flags: `--days`, `--start`, and `--end` for other windows; `--width`, `--fps`, and `--duration` for rendering. Run `--help` for the rest.

## More

The `release-balls` CLI and action remain available for release races; see [release publishing details](docs/releases.md).

## License

[MIT](LICENSE). The bundled fonts are CC0 and SIL OFL 1.1; see [assets](assets/README.md).
