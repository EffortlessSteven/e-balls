#!/usr/bin/env python3
"""Independently recount a collector snapshot from individual raw Git objects."""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import subprocess


def count_value(value, name):
    """Reject booleans, fractions, negative values, and renderer overflow."""
    if type(value) is not int or not 0 <= value < 2**64:
        raise ValueError(f"{name} must be a nonnegative u64 integer")
    return value


def verify(repo: Path, snapshot: Path) -> dict:
    """Verify one immutable input against complete, pinned Git history."""
    raw_data = snapshot.read_bytes()
    data = json.loads(raw_data)
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("unsupported schema_version; expected 1")
    source = data["source"]

    def git(*args):
        return subprocess.check_output(["git", "--no-replace-objects", "-C", str(repo), *args])

    if git("rev-parse", "--is-shallow-repository").strip() != b"false":
        raise ValueError("shallow history is incomplete; fetch full history before verifying")
    pin = source["commit"]
    if not isinstance(pin, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", pin):
        raise ValueError("source commit must be a full commit SHA, not a moving ref")
    if git("cat-file", "-t", pin).strip() != b"commit":
        raise ValueError("source SHA must identify a commit object")
    dates = []
    for key in ("start_inclusive", "end_exclusive"):
        value = source[key]
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T00:00:00Z", value):
            raise ValueError("window boundaries must be midnight UTC")
        dates.append(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
    start, end = dates
    if not 1 <= (end - start).days <= 366:
        raise ValueError("window must contain 1–366 complete UTC days")
    letter = source["letter"]
    if not isinstance(letter, str) or not re.fullmatch(r"[a-z]", letter):
        raise ValueError("source letter must be one lowercase ASCII letter")
    needle = letter.encode("ascii")
    counts, commits, receipts = Counter(), Counter(), {}
    # Unlike collection, use log for membership and read each object separately.
    for line in git("log", "--no-show-signature", "--no-notes", "--format=%H %ct", pin, "--").splitlines():
        sha, epoch = line.decode("ascii").split()
        stamp = dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc)
        if not start <= stamp < end:
            continue
        body = git("cat-file", "commit", sha).split(b"\n\n", 1)[1]
        count = sum(byte in (needle[0], needle.upper()[0]) for byte in body)
        day = stamp.date().isoformat()
        committed_at = stamp.isoformat().replace("+00:00", "Z")
        counts[day] += count
        commits[day] += 1
        receipts[sha] = (day, committed_at, count, hashlib.sha256(body).hexdigest())
    expected_days = [(start.date() + dt.timedelta(days=i)).isoformat() for i in range((end - start).days)]
    if [row["date"] for row in data["rows"]] != expected_days:
        raise ValueError("calendar rows are missing, duplicated, or out of order")
    for row in data["rows"]:
        daily_count = count_value(row["count"], "daily count")
        daily_commits = count_value(row["commits"], "daily commits")
        if (daily_count, daily_commits) != (counts[row["date"]], commits[row["date"]]):
            raise ValueError(f"daily count mismatch: {row['date']}")
    provided = {
        c["sha"]: (c["day"], c["committed_at"], count_value(c["count"], "receipt count"), c["message_sha256"])
        for c in source["commits"]
    }
    if provided != receipts or len(provided) != len(source["commits"]):
        raise ValueError("per-commit receipts do not match the pinned Git history")
    total_commits = count_value(source["total_commits"], "total commits")
    total_count = count_value(source["total_count"], "total count")
    if total_commits != sum(commits.values()) or total_count != sum(counts.values()):
        raise ValueError("snapshot totals do not reconcile")
    return {"verified": True, "source_commit": pin, "commits": total_commits,
            "count": total_count, "daily_counts": {day: counts[day] for day in expected_days},
            "data_sha256": hashlib.sha256(raw_data).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.repo, args.data), indent=2))
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"error: {error}\n")
