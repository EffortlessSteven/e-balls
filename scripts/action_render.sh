#!/usr/bin/env bash
# Git transport and FFmpeg glue. Counting and avatar selection are Rust.
set -euo pipefail

: "${GITHUB_ACTION_PATH:?}"
: "${GITHUB_OUTPUT:?}"
: "${RUNNER_TEMP:?}"

if [[ ! "$EB_REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "repository must be a GitHub owner/name" >&2
  exit 2
fi
# Keep the old input as an alias without making whitespace or punctuation special.
text="${EB_TEXT-}"
if [[ -n "${EB_LETTER-}" ]]; then
  if [[ -n "$text" ]]; then
    echo "use text or letter, not both" >&2
    exit 2
  fi
  text="$EB_LETTER"
fi
# Empty composite-action inputs are unset; the CLI still rejects --text=.
text="${text:-e}"
case "${EB_CASE_SENSITIVE-false}" in
  true|false) ;;
  *) echo "case-sensitive must be true or false" >&2; exit 2 ;;
esac
if [[ "$EB_SINCE" != "7d" ]]; then
  echo "since currently supports exactly 7d" >&2
  exit 2
fi
case "$EB_FORMAT" in
  mp4|gif|both) ;;
  *) echo "format must be mp4, gif, or both" >&2; exit 2 ;;
esac
if [[ -n "$EB_DATA" && -z "$EB_AVATAR" ]]; then
  echo "saved data requires an explicit avatar; a top contributor cannot be selected without Git history" >&2
  exit 2
fi

# Reject invalid destinations/overrides before cloning or calling GitHub.
if [[ -z "$EB_OUTPUT" || "$EB_OUTPUT" == *$'\n'* || "$EB_OUTPUT" == *$'\r'* ]]; then
  echo "output must be a nonempty path without newlines" >&2
  exit 2
fi
if [[ -e "$EB_OUTPUT" || -L "$EB_OUTPUT" ]]; then
  echo "output already exists; choose a new output directory" >&2
  exit 2
fi
if [[ -n "$EB_AVATAR" && ! -f "$EB_AVATAR" ]]; then
  echo "avatar file not found: $EB_AVATAR" >&2
  exit 2
fi
source_git() {
  env -u EB_TOKEN -u GITHUB_TOKEN -u GH_TOKEN GIT_TERMINAL_PROMPT=0 git "$@"
}

work=""
cleanup() {
  if [[ -n "$work" ]]; then
    rm -rf -- "$work"
  fi
}
trap cleanup EXIT

output=$(realpath -m "$EB_OUTPUT")
project="$EB_PROJECT"
if [[ -z "$project" ]]; then
  project="${EB_REPOSITORY##*/}"
fi

if [[ -n "$EB_DATA" ]]; then
  if [[ ! -f "$EB_DATA" ]]; then
    echo "data file not found: $EB_DATA" >&2
    exit 2
  fi
  data=$(realpath "$EB_DATA")
  avatar=$(realpath "$EB_AVATAR")
else
  work=$(mktemp -d "$RUNNER_TEMP/e-balls-source.XXXXXXXX")
  clone_args=(--bare --filter=blob:none --single-branch --no-tags)
  source_ref=HEAD
  if [[ "$EB_REF" =~ ^([0-9a-fA-F]{40}|[0-9a-fA-F]{64})$ ]]; then
    # A full reachable SHA makes the weekly replay reproducible.
    source_ref="$EB_REF"
  elif [[ -n "$EB_REF" ]]; then
    source_git check-ref-format --branch "$EB_REF" >/dev/null
    clone_args+=(--branch "$EB_REF")
    source_ref="$EB_REF"
  fi
  # Read-only clone; never pass the GitHub token to Git.
  source_git clone "${clone_args[@]}" "https://github.com/$EB_REPOSITORY.git" "$work/history.git"
  source_git -C "$work/history.git" config remote.origin.pushurl DISABLED
  data="$work/counts.json"
  counter_args=(
    --repo "$work/history.git" --ref "$source_ref"
    --repository "$EB_REPOSITORY" --project "$project"
    --text "$text" --since "$EB_SINCE" --out "$data"
  )
  if [[ "${EB_CASE_SENSITIVE-false}" == true ]]; then
    counter_args+=(--case-sensitive)
  fi
  if [[ -n "$EB_END" ]]; then
    counter_args+=(--end "$EB_END")
  fi
  if [[ -z "$EB_AVATAR" ]]; then
    avatar="$work/top-contributor.png"
    counter_args+=(--avatar-out "$avatar")
  else
    avatar=$(realpath "$EB_AVATAR")
  fi
  GITHUB_TOKEN="$EB_TOKEN" "$GITHUB_ACTION_PATH/target/release/e-balls-collect" "${counter_args[@]}"
fi

if [[ ! -f "$avatar" ]]; then
  echo "avatar file not found: $avatar" >&2
  exit 2
fi
env -u EB_TOKEN -u GITHUB_TOKEN -u GH_TOKEN \
  "$GITHUB_ACTION_PATH/target/release/e-balls" \
  --data "$data" --avatar "$avatar" --format "$EB_FORMAT" --out "$output" \
  --asset-base-url "$EB_ASSET_BASE"
