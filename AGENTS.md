# e-balls

The working repository is **EffortlessSteven/e-balls**. All commits, pushes,
issues, and pull requests for this work target this fork. Do not open a PR,
comment, issue, or branch in maria-rcks/release-balls. Use an explicit
`--repo EffortlessSteven/e-balls` for GitHub CLI writes; never rely on fork
upstream defaults.

Keep Maria's renderer and attribution. The `e-balls` binary adds arbitrary
ordered counts and one local portrait for every ball. The original
`release-balls` binary remains available. No automatic publication, release
notes edits, or changes to perl-lsp CI.

Verify with:

```sh
cargo fmt --all -- --check
cargo clippy --release --locked --all-targets -- -D warnings
cargo test --locked --all-targets
cargo build --release --locked --bins
EBALLS_BIN=target/release/e-balls python3 -m unittest discover -s tests -v
```

Count full raw messages, including trailers, by UTC committer date over a
half-open window. Read one pinned Git ancestry, count every reachable SHA
once (including merges), preserve zero days, and reject shallow history.
The repeated portrait is presentation, not an assertion of commit authorship.
