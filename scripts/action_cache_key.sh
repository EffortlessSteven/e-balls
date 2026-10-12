#!/usr/bin/env bash
# Hash build inputs by relative path and content, including embedded JSON/assets.
set -euo pipefail
root=${1:?usage: action_cache_key.sh ACTION_DIRECTORY}
cd -- "$root"
for required in Cargo.toml Cargo.lock src assets; do
  test -e "$required" || { echo "missing build input: $required" >&2; exit 2; }
done
inputs=(Cargo.toml Cargo.lock src assets)
for optional in action.yml build.rs rust-toolchain rust-toolchain.toml .cargo; do
  if [[ -e "$optional" ]]; then inputs+=("$optional"); fi
done
# A symlink's external target is not a self-contained build input.
if [[ -n "$(find "${inputs[@]}" -type l -print)" ]]; then
  echo 'symlinked build inputs cannot be fingerprinted safely' >&2
  exit 2
fi
listing=$(mktemp)
trap 'rm -f -- "$listing"' EXIT
find "${inputs[@]}" -type f -print0 | LC_ALL=C sort -z > "$listing"
mapfile -d '' -t files < "$listing"
{
  printf 'e-balls-build-v2\0rust-1.88.0\0'
  printf '%s\0' "${RUSTFLAGS-}" "${CARGO_ENCODED_RUSTFLAGS-}" "${CARGO_BUILD_TARGET-}"
  printf '%s\0' "${CARGO_PROFILE_RELEASE_OPT_LEVEL-}" "${CARGO_PROFILE_RELEASE_LTO-}"
  printf '%s\0' "${CARGO_PROFILE_RELEASE_CODEGEN_UNITS-}" "${CARGO_PROFILE_RELEASE_PANIC-}" "${CARGO_PROFILE_RELEASE_STRIP-}"
  sha256sum --zero -- "${files[@]}"
} | sha256sum | cut -d ' ' -f 1
