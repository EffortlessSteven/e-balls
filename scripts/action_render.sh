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
if [[ ! "$EB_LETTER" =~ ^[A-Za-z]$ ]]; then
  echo "letter must be one ASCII letter" >&2
  exit 2
fi
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
    git check-ref-format --branch "$EB_REF" >/dev/null
    clone_args+=(--branch "$EB_REF")
    source_ref="$EB_REF"
  fi
  # Read-only clone; never pass the GitHub token to Git.
  git clone "${clone_args[@]}" "https://github.com/$EB_REPOSITORY.git" "$work/history.git"
  git -C "$work/history.git" config remote.origin.pushurl DISABLED
  data="$work/counts.json"
  counter_args=(
    --repo "$work/history.git" --ref "$source_ref"
    --repository "$EB_REPOSITORY" --project "$project"
    --letter "$EB_LETTER" --since "$EB_SINCE" --out "$data"
  )
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
"$GITHUB_ACTION_PATH/target/release/e-balls" \
  --data "$data" --avatar "$avatar" --format "$EB_FORMAT" --out "$output"

base="$EB_ASSET_BASE"
if [[ -n "$base" && "$base" != */ ]]; then
  base="$base/"
fi
{
  if [[ "$EB_FORMAT" != mp4 ]]; then
    printf '![e-balls](%se-balls.gif)\n' "$base"
  fi
  if [[ "$EB_FORMAT" != gif ]]; then
    printf '\n[MP4](%se-balls.mp4)\n' "$base"
  fi
} > "$output/embed.md"

printf 'directory=%s\n' "$output" >> "$GITHUB_OUTPUT"
printf 'markdown=%s/embed.md\n' "$output" >> "$GITHUB_OUTPUT"
printf 'manifest=%s/manifest.json\n' "$output" >> "$GITHUB_OUTPUT"
printf 'data=%s/data.json\n' "$output" >> "$GITHUB_OUTPUT"
