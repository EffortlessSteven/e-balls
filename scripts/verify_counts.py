#!/usr/bin/env python3
"""Independently recount a collector snapshot from individual raw Git objects."""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess


def verify(repo: Path, snapshot: Path) -> dict:
    data = json.loads(snapshot.read_text(encoding="utf-8"))
    source = data["source"]
    def git(*args):
        return subprocess.check_output(["git", "--no-replace-objects", "-C", str(repo), *args])
    start = dt.datetime.fromisoformat(source["start_inclusive"].replace("Z", "+00:00"))
    end = dt.datetime.fromisoformat(source["end_exclusive"].replace("Z", "+00:00"))
    needle = source["letter"].encode("ascii")
    counts, commits, receipts = Counter(), Counter(), {}
    # Unlike collection, use log for membership and read each object separately.
    for line in git("log", "--no-show-signature", "--no-notes", "--format=%H %ct", source["commit"], "--").splitlines():
        sha, epoch = line.decode("ascii").split()
        stamp = dt.datetime.fromtimestamp(int(epoch), dt.timezone.utc)
        if not start <= stamp < end:
            continue
        body = git("cat-file", "commit", sha).split(b"\n\n", 1)[1]
        count = sum(byte in (needle[0], needle.upper()[0]) for byte in body)
        day = stamp.date().isoformat()
        counts[day] += count
        commits[day] += 1
        receipts[sha] = (day, count, hashlib.sha256(body).hexdigest())
    expected_days = [(start.date() + dt.timedelta(days=i)).isoformat() for i in range((end - start).days)]
    if [row["date"] for row in data["rows"]] != expected_days:
        raise ValueError("calendar rows are missing, duplicated, or out of order")
    for row in data["rows"]:
        if (row["count"], row["commits"]) != (counts[row["date"]], commits[row["date"]]):
            raise ValueError(f"daily count mismatch: {row['date']}")
    provided = {c["sha"]: (c["day"], c["count"], c["message_sha256"]) for c in source["commits"]}
    if provided != receipts or len(provided) != len(source["commits"]):
        raise ValueError("per-commit receipts do not match the pinned Git history")
    if source["total_commits"] != sum(commits.values()) or source["total_count"] != sum(counts.values()):
        raise ValueError("snapshot totals do not reconcile")
    return {"verified": True, "source_commit": source["commit"], "commits": sum(commits.values()),
            "count": sum(counts.values()), "daily_counts": dict(sorted(counts.items())),
            "data_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--data", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.repo, args.data), indent=2))
