#!/usr/bin/env bash
# e-balls GitHub Action: read a public Git branch, verify counts, render media.
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

avatar="$EB_AVATAR"
if [[ -z "$avatar" ]]; then
  avatar="$GITHUB_ACTION_PATH/examples/perl-lsp-2026-10-04-teal/avatar.png"
fi
if [[ ! -f "$avatar" ]]; then
  echo "avatar file not found: $avatar" >&2
  exit 2
fi
avatar=$(realpath "$avatar")
output=$(realpath -m "$EB_OUTPUT")

if [[ -n "$EB_DATA" ]]; then
  if [[ ! -f "$EB_DATA" ]]; then
    echo "data file not found: $EB_DATA" >&2
    exit 2
  fi
  data=$(realpath "$EB_DATA")
else
  # Never execute source files. Read the full ancestry from an isolated bare clone.
  git check-ref-format --branch "$EB_REF" >/dev/null
  work=$(mktemp -d "$RUNNER_TEMP/e-balls-source.XXXXXXXX")
  trap 'rm -rf -- "$work"' EXIT
  git clone --bare --filter=blob:none --single-branch --branch "$EB_REF" --no-tags \
    "https://github.com/$EB_REPOSITORY.git" "$work/history.git"
  git -C "$work/history.git" config remote.origin.pushurl DISABLED
  data="$work/counts.json"
  args=(
    --repo "$work/history.git" --ref "$EB_REF"
    --repository "$EB_REPOSITORY" --project "$EB_PROJECT"
    --letter "$EB_LETTER" --since "$EB_SINCE" --out "$data"
  )
  if [[ -n "$EB_END" ]]; then
    args+=(--end "$EB_END")
  fi
  python3 "$GITHUB_ACTION_PATH/scripts/count_letters.py" "${args[@]}"
  python3 "$GITHUB_ACTION_PATH/scripts/verify_counts.py" \
    --repo "$work/history.git" --data "$data" > "$work/count-verification.json"
fi

"$GITHUB_ACTION_PATH/target/release/e-balls" \
  --data "$data" --avatar "$avatar" --format "$EB_FORMAT" --out "$output"

if [[ -z "$EB_DATA" ]]; then
  cp "$work/count-verification.json" "$output/count-verification.json"
fi

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
