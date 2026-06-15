#!/usr/bin/env python
"""Run BigQuery Ethereum smoke checks.

This script requires Google Application Default Credentials, usually via:

    export GOOGLE_APPLICATION_CREDENTIALS=~/.gcp/nl2sparql-key.json
"""

from __future__ import annotations

import argparse
import os
import sys

from google.auth.exceptions import DefaultCredentialsError
from google.cloud import bigquery

from nl2sparql.kg.extraction.bigquery_smoke import (
    COUNT_TRANSACTIONS_SQL,
    build_monthly_extraction_estimate_sql,
    estimate_query_bytes,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default="2024-01-31")
    parser.add_argument(
        "--skip-count",
        action="store_true",
        help="Only run dry-run cost estimation, not the COUNT(*) query.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print(
            "GOOGLE_APPLICATION_CREDENTIALS is not set. "
            "Create a service account key and set the env var before running this script.",
            file=sys.stderr,
        )
        return 2

    try:
        client = bigquery.Client()
    except DefaultCredentialsError as exc:
        print(f"BigQuery authentication failed: {exc}", file=sys.stderr)
        return 2

    if not args.skip_count:
        rows = list(client.query(COUNT_TRANSACTIONS_SQL).result())
        print(f"transactions_2024_01_01={rows[0].n}")

    estimate_sql = build_monthly_extraction_estimate_sql(args.start_date, args.end_date)
    bytes_processed = estimate_query_bytes(client, estimate_sql)
    gib = bytes_processed / (1024**3)
    print(f"dry_run_bytes={bytes_processed}")
    print(f"dry_run_gib={gib:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
