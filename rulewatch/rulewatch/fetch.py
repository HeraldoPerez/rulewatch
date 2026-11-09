"""Fetch recent Federal Register documents for every watch and save them as JSON.

Usage:
    python -m rulewatch.fetch --config watches.yml --out data --days 30

Writes one file per watch, data/<watch name>.json. Each run replaces the file
with the documents published in the last --days days.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import ConfigError, Watch, load_watches
from .federal_register import FederalRegisterClient, FederalRegisterError, SearchResult

EXIT_OK = 0
EXIT_FETCH_FAILED = 1
EXIT_BAD_CONFIG = 2


def main(
    argv: list[str] | None = None,
    *,
    client: FederalRegisterClient | None = None,
    today: date | None = None,
    now: datetime | None = None,
) -> int:
    args = _parse_args(argv)

    try:
        watches = load_watches(args.config)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return EXIT_BAD_CONFIG

    today = today or date.today()
    now = now or datetime.now(timezone.utc)
    since = today - timedelta(days=args.days)

    own_client = client is None
    client = client or FederalRegisterClient()
    failures = 0
    try:
        for watch in watches:
            try:
                result = client.search(watch, since)
            except FederalRegisterError as exc:
                print(f"{watch.name}: failed, {exc}", file=sys.stderr)
                failures += 1
                continue

            payload = build_payload(watch, result, since=since, now=now)
            write_json(args.out / f"{watch.name}.json", payload)
            print(summarize(watch, result, today))
    finally:
        if own_client:
            client.close()

    return EXIT_FETCH_FAILED if failures else EXIT_OK


def build_payload(watch: Watch, result: SearchResult, *, since: date, now: datetime) -> dict:
    return {
        "watch": watch.to_json(),
        "fetched_at": now.isoformat(timespec="seconds"),
        "since": since.isoformat(),
        "total": result.total,
        "complete": result.complete,
        "documents": [document.to_json() for document in result.documents],
    }


def summarize(watch: Watch, result: SearchResult, today: date) -> str:
    open_count = sum(document.comments_open(today) for document in result.documents)
    line = (
        f"{watch.name}: {len(result.documents)} documents, "
        f"{open_count} with comment periods still open"
    )
    if not result.complete:
        line += (
            f" (only the newest {len(result.documents)} of {result.total} were saved; "
            "narrow the watch or use a smaller --days)"
        )
    return line


def write_json(path: Path, data: dict) -> None:
    """Write through a temporary file, so a failed run never leaves half a file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _positive_int(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m rulewatch.fetch",
        description="Fetch recent Federal Register documents for every watch in a config file.",
    )
    parser.add_argument(
        "--config", type=Path, default=Path("watches.yml"),
        help="watches file (default: watches.yml)",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("data"),
        help="folder for the JSON output (default: data)",
    )
    parser.add_argument(
        "--days", type=_positive_int, default=30,
        help="how many days back to search (default: 30)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
