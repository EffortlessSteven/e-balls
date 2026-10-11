# Execution evidence

Each command has a `.log` containing its exact shell command, complete combined
stdout/stderr and exit status, plus a `.json` with working directory and UTC
start/end times. An exit status of zero records successful execution; skipped
unit tests would still need to be reported separately.

Commands ran from the e-balls checkout with Rust 1.88.0 and Python 3.12.15
activated using `mise exec rust@1.88.0 python@3.12 -- ...`. Media commands and
compiled CLI tests used `/home/vercel-sandbox/runtime/e-balls-tools` first on
`PATH` for FFmpeg/ffprobe 7.0.2. See `tool-versions.log` for exact versions.
System FreeType development headers and pkg-config were already installed.
The system Python 3.9 and FFmpeg without libx264 were unsuitable; setup logs
record installation of the required tools, outside the repository.

- `pr-context.json`: retrieved PR #1 description, head/base revisions and file
  changes; checkout matched the head before editing.
- `renderer-commit.txt`: starting source revision. This is **not** a claim that
  the checkout was unchanged: `tested-source.patch` contains the formatting
  changes, and `tested-inputs.json` hashes every tracked source/config/test/asset
  file as tested, including Cargo.lock and the existing font.
- `binary-hashes.json`: identities of the two compiled release binaries.
  The binaries and fonts are not included in this evidence bundle.
- `clone-history.*`, `collect.*`, `verify-counts.*`: full reachable commit
  ancestry and independent raw-object recount. The source clone's push URL
  was disabled locally; no source repository content was changed.
- `supplied-avatar.png`: original bytes downloaded from
  `https://avatars.githubusercontent.com/u/15812269?v=4&s=512`.
  The renderer writes the normalized RGB PNG as `../avatar.png`.
- `check-media.py`, `check-source.py`: the additional assertions actually run
  for this verification. They use Python's standard library and FFmpeg.
- Sample contact sheets use MP4 frames 30, 270, 510, 930 (0.5, 4.5, 8.5,
  15.5 seconds) and GIF frames 8, 68, 128, 233 (approximately 0.53, 4.53,
  8.53, 15.53 seconds), arranged left to right, then top to bottom.

Scratch paths in command transcripts refer to the original execution sandbox.
To reproduce, use a new full-history bare clone and new temporary paths; the
renderer refuses existing output directories. The top-level verification
report gives the portable sequence.
