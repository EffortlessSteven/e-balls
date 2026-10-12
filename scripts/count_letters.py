#!/usr/bin/env python3
"""Reference literal-string collector, grouped by UTC committer day."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

UTC = dt.timezone.utc
MAX_DAYS = 366
SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


def git(repo: Path, *args: str, input: bytes | None = None) -> bytes:
    # Ignore replacement objects so the recorded SHA describes the counted bytes.
    result = subprocess.run(
        ["git", "--no-replace-objects", "-C", str(repo), *args],
        input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def collect(repo: Path, ref: str, start: dt.date, end: dt.date,
            repository: str, project: str, letter: str = "e",
            *, text: str | None = None, case_sensitive: bool = False) -> dict[str, Any]:
    """Read one pinned ancestry, including merges; end is exclusive."""
    days = (end - start).days
    if not 1 <= days <= MAX_DAYS:
        raise ValueError(f"window must contain 1–{MAX_DAYS} complete UTC days")
    text = letter if text is None else text
    if not isinstance(text, str) or not text:
        raise ValueError("text must be a nonempty literal string")
    needle = text.encode("utf-8")
    if not case_sensitive:
        needle = needle.lower()
    legacy_letter = (needle.decode("ascii") if len(needle) == 1
                     and needle.isalpha() and not case_sensitive else None)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    if not project.strip() or len(project) > 80 or any(ord(c) < 32 for c in project):
        raise ValueError("project must be a nonempty, single-line label of at most 80 characters")
    if git(repo, "rev-parse", "--is-shallow-repository").strip() != b"false":
        raise ValueError("shallow history is incomplete; fetch the full history before counting")
    pin = git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    if not SHA.fullmatch(pin):
        raise ValueError("Git did not resolve the ref to a full commit SHA")
    first = int(dt.datetime.combine(start, dt.time(), UTC).timestamp())
    stop = int(dt.datetime.combine(end, dt.time(), UTC).timestamp())
    calendar = [start + dt.timedelta(days=i) for i in range(days)]
    buckets = {day.isoformat(): {"count": 0, "commits": 0} for day in calendar}
    selected: dict[str, int] = {}
    # Do not use --since: traversal can stop at an old-dated parent and miss
    # newer-dated ancestors. Visit the entire pinned ancestry, then filter.
    for line in git(repo, "rev-list", "--timestamp", pin, "--").splitlines():
        raw_time, raw_sha = line.split(b" ", 1)
        timestamp, sha = int(raw_time), raw_sha.decode("ascii")
        if not SHA.fullmatch(sha):
            raise ValueError("invalid commit SHA in rev-list output")
        if first <= timestamp < stop:
            selected[sha] = timestamp

    receipts: list[dict[str, Any]] = []
    # One batch request, length-framed raw objects: delimiters, NULs, encoding
    # headers, and multiline bodies cannot turn message text into metadata.
    ordered = sorted(selected, key=lambda sha: (selected[sha], sha))
    raw = git(repo, "cat-file", "--batch", input="".join(sha + "\n" for sha in ordered).encode())
    offset = 0
    for sha in ordered:
        header_end = raw.find(b"\n", offset)
        if header_end < 0:
            raise ValueError("truncated cat-file header")
        header = raw[offset:header_end].split()
        if len(header) != 3 or header[0].decode() != sha or header[1] != b"commit":
            raise ValueError(f"missing or invalid commit object: {sha}")
        size = int(header[2])
        offset = header_end + 1
        payload = raw[offset:offset + size]
        offset += size
        if len(payload) != size or raw[offset:offset + 1] != b"\n":
            raise ValueError(f"truncated commit object: {sha}")
        offset += 1
        headers, separator, message = payload.partition(b"\n\n")
        if not separator:
            raise ValueError(f"commit has no message boundary: {sha}")
        committer = next((line for line in headers.splitlines() if line.startswith(b"committer ")), None)
        if committer is None or int(committer.rsplit(b" ", 2)[1]) != selected[sha]:
            raise ValueError(f"committer timestamp disagrees with revision walk: {sha}")
        count = (message if case_sensitive else message.lower()).count(needle)
        timestamp = dt.datetime.fromtimestamp(selected[sha], UTC)
        day = timestamp.date().isoformat()
        buckets[day]["count"] += count
        buckets[day]["commits"] += 1
        receipts.append({
            "sha": sha, "committed_at": timestamp.isoformat().replace("+00:00", "Z"),
            "day": day, "count": count,
            "message_sha256": hashlib.sha256(message).hexdigest(),
        })
    if offset != len(raw):
        raise ValueError("unexpected trailing cat-file data")
    rows = [{"label": day.strftime("%a %b %d"), "count": buckets[day.isoformat()]["count"],
             "date": day.isoformat(), "commits": buckets[day.isoformat()]["commits"]}
            for day in calendar]
    final_day = end - dt.timedelta(days=1)
    data = {
        "schema_version": 1,
        "title": f"Occurrences of '{legacy_letter or display_text(text)}' in {project} commit messages",
        "subtitle": f"{start.isoformat()} to {final_day.isoformat()} · UTC",
        "footer": f"github.com/{repository}",
        "unit": f"{legacy_letter}'s" if legacy_letter else "matches",
        "unit_singular": legacy_letter or "match", "rows": rows,
        "source": {
            "repository": repository, "requested_ref": ref, "commit": pin,
            "start_inclusive": start.isoformat() + "T00:00:00Z",
            "end_exclusive": end.isoformat() + "T00:00:00Z",
            "timestamp": "committer", "timezone": "UTC",
            "traversal": "all reachable commits, including merges; each SHA once",
            "message": "full raw commit message, including body and trailers",
            "matcher": {"kind": "literal", "text": text,
                        "case": "sensitive" if case_sensitive else "ascii-insensitive",
                        "overlapping": False},
            "total_commits": len(receipts), "total_count": sum(row["count"] for row in rows),
            "commits": receipts,
        },
    }
    if legacy_letter:
        data["source"].update(letter=legacy_letter, case="ASCII-insensitive")
    return data


def display_text(text: str) -> str:
    """Escape unsupported glyphs/control characters without changing counted bytes."""
    short = {"\n": r"\n", "\r": r"\r", "\t": r"\t", "\\": r"\\", "'": r"\'", '"': r'\"'}
    label = ""
    for character in text:
        escaped = short.get(character, character if " " <= character <= "~" else f"\\u{{{ord(character):x}}}")
        if len(label) + len(escaped) > 64:
            return label + "..."
        label += escaped
    return label


def write_json(path: Path, value: dict[str, Any]) -> None:
    """Replace only a complete output; failed collection leaves no partial JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, delete=False) as stream:
            name = stream.name
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(name, path)
        name = None
    finally:
        if name is not None:
            Path(name).unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True, help="local full Git checkout or bare repository")
    parser.add_argument("--ref", default="HEAD", help="commit/ref to freeze before reading")
    parser.add_argument("--repository", required=True, help="source owner/name, for attribution only")
    parser.add_argument("--project", default="perl-lsp")
    parser.add_argument("--text", "--letter", dest="text", default="e", help="nonempty literal UTF-8 string")
    parser.add_argument("--case-sensitive", action="store_true", help="disable ASCII case folding")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--since", choices=["7d"], help="seven completed UTC days before --end (default today)")
    group.add_argument("--start", type=dt.date.fromisoformat)
    group.add_argument("--days", type=int, help="completed UTC days; default 7")
    parser.add_argument("--end", type=dt.date.fromisoformat, default=dt.datetime.now(UTC).date(),
                        help="exclusive UTC end date; default today")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        days = args.days if args.days is not None else 7
        if args.start is None and not 1 <= days <= MAX_DAYS:
            raise ValueError(f"days must be between 1 and {MAX_DAYS}")
        start = args.start or args.end - dt.timedelta(days=days)
        data = collect(args.repo, args.ref, start, args.end, args.repository, args.project,
                       text=args.text, case_sensitive=args.case_sensitive)
        write_json(args.out, data)
    except (ValueError, OSError, OverflowError) as error:
        parser.exit(2, f"error: {error}\n")
    print(f"{data['source']['total_commits']} commits, {data['source']['total_count']} {data['unit']}; "
          f"{data['source']['commit']} → {args.out}")


if __name__ == "__main__":
    main()
