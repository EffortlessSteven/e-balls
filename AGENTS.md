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
EBALLS_BIN=target/release/e-balls EBALLS_COLLECT_BIN=target/release/e-balls-collect python3 -m unittest discover -s tests -v
```

Count full raw messages, including trailers, by UTC committer date over a
half-open window. Read one pinned Git ancestry, count every reachable SHA
once (including merges), preserve zero days, and reject shallow history.
The repeated portrait is presentation, not an assertion of commit authorship.

`text` is a nonempty literal UTF-8 string, not a regex or a letter allowlist.
Matching is non-overlapping per message; ASCII-only case folding is the default,
and `case-sensitive` enables exact byte matching. `letter` remains an alias.
Keep the q/2.0 roadmap and "other 29 letters" non-goal wording as jokes, not
runtime restrictions. Preserve frozen examples and their original receipts.

CI has no schedules. Keep README-only changes out of Rust/media jobs.
Run live GitHub/avatar smoke tests and full examples only via manual CI dispatch.
Do not add background demo refreshes or artifact-publishing loops.
