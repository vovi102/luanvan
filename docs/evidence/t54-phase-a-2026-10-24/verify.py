"""Verify phase-A evidence offline; never contacts a provider."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

from nl2sparql.evaluation.artifacts import load_and_verify_artifact

ROOT = Path.cwd()
BASE = ROOT / "docs/evidence/t54-phase-a-2026-10-24"


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


scope = read(ROOT / "docs/evidence/t54-bigquery-review-2026-10-24/dry-run-scope.json")
summary = read(BASE / "dry-run-summary.json")
records = [json.loads(line) for line in (BASE / "dry-run-journal.jsonl").read_text().splitlines()]
previous = "0" * 64
outcomes = []
intents = []
for record in records:
    digest = record.pop("record_sha256")
    assert record["previous_sha256"] == previous
    assert (
        sha(json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())
        == digest
    )
    previous = digest
    payload = record["payload"]
    if payload["kind"] == "dry_run_intent":
        intents.append(payload)
    elif payload["kind"] == "dry_run_outcome":
        outcomes.append(payload)
assert records[-1]["payload"]["kind"] == "terminal_seal"
assert previous == summary["journal_terminal_record_sha256"]
assert sha((BASE / "dry-run-journal.jsonl").read_bytes()) == summary["journal_file_sha256"]
assert len(intents) == len(outcomes) == summary["attempted_requests"] == 25
assert [p["scope_index"] for p in intents] == list(range(25))
assert [p["scope_index"] for p in outcomes] == list(range(25))
counts = Counter()
per_run = defaultdict(lambda: {"known_estimated_bytes": 0, "estimated_queries": 0})
for i, (intent, outcome) in enumerate(zip(intents, outcomes, strict=True)):
    query = scope["queries"][i]
    assert intent["sql_sha256"] == outcome["sql_sha256"] == query["sql_sha256"]
    assert outcome["dry_run"] is True
    config = outcome["response"]["configuration"]
    assert config["dryRun"] is True and config["query"]["useQueryCache"] is False
    assert config["query"]["useLegacySql"] is False
    assert int(config["query"]["maximumBytesBilled"]) == 24 * 1024**3
    assert sha(config["query"]["query"].encode()) == query["sql_sha256"]
    # QueryJob.to_api_repr() stores configuration, not the raw HTTP statistics.
    # The runner recorded this scalar directly from job.total_bytes_processed.
    amount = outcome["estimated_bytes"]
    assert isinstance(amount, int) and not isinstance(amount, bool) and amount >= 0
    assert outcome["status"] == ("estimate_above_24_GiB" if amount > 24 * 1024**3 else "ok")
    for use in query["uses"]:
        counts[use["role"]] += 1
        per_run[use["run_id"]]["known_estimated_bytes"] += amount
        per_run[use["run_id"]]["estimated_queries"] += 1
assert counts == Counter(gold=228, prediction=18)
assert sum(counts.values()) == summary["logical_uses_estimated"] == 246
assert summary["campaign_complete_estimated_bytes"] is None
assert summary["logical_uses_unestimated"] == 1083
for run_id, values in per_run.items():
    assert all(summary["per_run"][run_id][key] == value for key, value in values.items())
assert len(summary["unattempted_sql_sha256"]) == 118
assert summary["unattempted_sql_sha256"] == [q["sql_sha256"] for q in scope["queries"][25:]]
assert outcomes[-1]["estimated_bytes"] == 30470124008
mapping = read(BASE / "privacy-bound-runs.json")
for entry in mapping["runs"]:
    old_path = ROOT / entry["original_canonical_path"]
    new_path = ROOT / entry["canonical_path"]
    assert sha(old_path.read_bytes()) == entry["original_canonical_sha256"]
    assert sha(new_path.read_bytes()) == entry["canonical_file_sha256"]
    load_and_verify_artifact(new_path)
    old = read(old_path)["body"]
    new = read(new_path)["body"]
    old_refs = old.pop("source_artifacts")
    new_refs = new.pop("source_artifacts")
    assert old_refs == [ref for ref in new_refs if ref["role"] != "privacy_review"]
    review_path = ROOT / entry["privacy_path"]
    load_and_verify_artifact(review_path)
    digest = sha(review_path.read_bytes())
    assert [ref["sha256"] for ref in new_refs if ref["role"] == "privacy_review"] == [digest]
    for case in old["cases"]:
        case.pop("privacy")
    for case in new["cases"]:
        privacy = case.pop("privacy")
        assert (
            privacy["documentation_status"] == "documented" and privacy["review_sha256"] == digest
        )
    assert old == new
checks = {
    "journal_hash_chain_and_terminal_seal": "pass",
    "exact_request_configuration_snapshots_bound": 25,
    "raw_http_response_statistics_preserved": False,
    "estimate_source": "job.total_bytes_processed observed by runner; scalar preserved",
    "all_requests_dry_run_no_cache_cap_24GiB": True,
    "stopped_at_first_over_cap": True,
    "logical_uses_estimated": dict(counts),
    "logical_uses_unestimated": 1083,
    "untouched_original_and_privacy_only_rebound_runs": 12,
    "canonical_privacy_sidecars": 4,
    "live_requests": 0,
    "full_campaign_estimate": None,
    "free_quota_balance": None,
}
print(
    json.dumps(
        {
            "kind": "phase_A_offline_verification",
            "verified_at_utc": datetime.now(UTC).isoformat(),
            "checks": checks,
        },
        indent=2,
    )
)
