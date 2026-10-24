"""Verify and reconcile both dry-run batches offline, keeping every logical use."""

import hashlib
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path.cwd()
FIRST = ROOT / "docs/evidence/t54-phase-a-2026-10-24"
SECOND = ROOT / "docs/evidence/t54-phase-a-continuation-2026-10-24"
SCOPE = ROOT / "docs/evidence/t54-bigquery-review-2026-10-24/dry-run-scope.json"
CAP = 24 * 1024**3


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


scope = read(SCOPE)
previous = read(FIRST / "manifest.json")
for ref in previous["files"]:
    path = FIRST / ref["path"]
    assert path.stat().st_size == ref["bytes"] and sha(path.read_bytes()) == ref["sha256"]
for ref in previous["related_inputs"]:
    assert sha((ROOT / ref["path"]).read_bytes()) == ref["sha256"]
all_outcomes = []
checks = []
for batch in (FIRST, SECOND):
    path = batch / "dry-run-journal.jsonl"
    entries = [json.loads(line) for line in path.read_text().splitlines()]
    chain = "0" * 64
    intents = []
    outcomes = []
    for entry in entries:
        digest = entry.pop("record_sha256")
        assert entry["previous_sha256"] == chain
        assert (
            sha(
                json.dumps(
                    entry, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                ).encode()
            )
            == digest
        )
        chain = digest
        payload = entry["payload"]
        if payload["kind"] == "dry_run_intent":
            intents.append(payload)
        elif payload["kind"] == "dry_run_outcome":
            outcomes.append(payload)
    assert entries[-1]["payload"]["kind"] == "terminal_seal"
    summary = read(batch / "dry-run-summary.json")
    assert sha(path.read_bytes()) == summary.get(
        "journal_sha256", summary.get("journal_file_sha256")
    )
    assert chain == summary.get(
        "terminal_record_sha256", summary.get("journal_terminal_record_sha256")
    )
    assert len(intents) == len(outcomes) == summary["attempted_requests"]
    for intent, outcome in zip(intents, outcomes, strict=True):
        index = outcome["scope_index"]
        query = scope["queries"][index]
        assert index == intent["scope_index"]
        assert query["sql_sha256"] == intent["sql_sha256"] == outcome["sql_sha256"]
        assert outcome["dry_run"] is True and intent["dry_run"] is True
        assert intent["project"] == "nl2sparql-thesis" and intent["location"] == "US"
        if batch == FIRST:
            config = outcome["response"]["configuration"]
            # First batch recorded SDK scalar estimates, not raw HTTP statistics.
        else:
            response = outcome["raw_http_response"]
            raw = (ROOT / response["path"]).read_bytes()
            assert sha(raw) == response["sha256"]
            body = json.loads(raw)
            if outcome["status"] == "dry_run_error":
                assert response["status_code"] == 404
                assert body["error"]["code"] == 404
                assert outcome["estimated_bytes"] is None
                assert outcome["provider_errors"] == body["error"]["errors"]
                config = read(SECOND / "request-policy.json")["request_configuration"]
                config = {"query": config["query"] | {"query": query["sql"]}, "dryRun": True}
            else:
                assert response["status_code"] == 200
                assert (
                    int(body["statistics"]["query"]["totalBytesProcessed"])
                    == outcome["estimated_bytes"]
                )
                config = body["configuration"]
                assert not body["status"].get("errorResult")
        assert config["dryRun"] is True
        q = config["query"]
        assert q["useQueryCache"] is False and q["useLegacySql"] is False
        assert int(q["maximumBytesBilled"]) == CAP
        assert sha(q["query"].encode()) == query["sql_sha256"]
        if outcome["estimated_bytes"] is not None:
            assert outcome["status"] == (
                "estimate_above_24_GiB" if outcome["estimated_bytes"] > CAP else "ok"
            )
        outcome["_journal_path"] = str(path.relative_to(ROOT))
        all_outcomes.append(outcome)
    checks.append(
        {
            "batch": str(batch.relative_to(ROOT)),
            "journal_chain_and_seal": "pass",
            "requests": len(outcomes),
            "statuses": dict(Counter(r["status"] for r in outcomes)),
        }
    )
assert len(all_outcomes) == 99
assert [r["scope_index"] for r in all_outcomes] == list(range(99))
assert len({r["sql_sha256"] for r in all_outcomes}) == 99
assert all_outcomes[-1]["status"] == "dry_run_error"
assert len([r for r in all_outcomes if r["estimated_bytes"] is not None]) == 98
lookup = {r["scope_index"]: r for r in all_outcomes}
rebound = {r["run_id"]: r for r in read(FIRST / "privacy-bound-runs.json")["runs"]}
logical_rows = []
per_run = defaultdict(
    lambda: {
        "expected_queries": 0,
        "estimated_queries": 0,
        "error_queries": 0,
        "unattempted_queries": 0,
        "over_cap_estimate_queries": 0,
        "known_component_estimated_bytes": 0,
        "roles": {
            role: {
                "expected": 0,
                "estimated": 0,
                "error": 0,
                "unattempted": 0,
                "known_component_estimated_bytes": 0,
            }
            for role in ("gold", "prediction")
        },
    }
)
queries = []
logical_status = Counter()
for index, query in enumerate(scope["queries"]):
    outcome = lookup.get(index)
    status = outcome["status"] if outcome else "unattempted"
    estimate = outcome["estimated_bytes"] if outcome else None
    queries.append(
        {
            "scope_index": index,
            "sql_sha256": query["sql_sha256"],
            "status": status,
            "estimated_bytes": estimate,
            "journal_path": outcome["_journal_path"] if outcome else None,
            "logical_uses": len(query["uses"]),
        }
    )
    for use in query["uses"]:
        run_id = use["run_id"]
        mapping = rebound[run_id]
        totals = per_run[run_id]
        role = use["role"]
        totals["expected_queries"] += 1
        totals["roles"][role]["expected"] += 1
        if estimate is not None:
            key = "estimated"
            totals["estimated_queries"] += 1
            totals["known_component_estimated_bytes"] += estimate
            totals["roles"][role]["known_component_estimated_bytes"] += estimate
            if estimate > CAP:
                totals["over_cap_estimate_queries"] += 1
        elif outcome:
            key = "error"
            totals["error_queries"] += 1
        else:
            key = "unattempted"
            totals["unattempted_queries"] += 1
        totals["roles"][role][key] += 1
        logical_status[(role, key)] += 1
        logical_rows.append(
            {
                "run_id": run_id,
                "baseline": mapping["baseline"],
                "language": mapping["language"],
                "case_id": use["case_id"],
                "role": role,
                "scope_index": index,
                "sql_sha256": query["sql_sha256"],
                "dry_run_status": status,
                "estimated_bytes": estimate,
                "original_canonical_sha256": use["canonical_file_sha256"],
                "privacy_bound_canonical_sha256": mapping["canonical_file_sha256"],
                "journal_path": outcome["_journal_path"] if outcome else None,
            }
        )
for totals in per_run.values():
    totals["complete_estimated_bytes"] = (
        totals["known_component_estimated_bytes"]
        if totals["estimated_queries"] == totals["expected_queries"]
        else None
    )
    totals["known_preflight_blocker_under_current_CLI19"] = (
        "any known query over per-query cap blocks whole run in initial aggregate guard"
        if totals["over_cap_estimate_queries"]
        else None
    )
assert len(logical_rows) == 1329
assert len({(r["run_id"], r["case_id"], r["role"]) for r in logical_rows}) == 1329
assert sum(r["expected_queries"] for r in per_run.values()) == 1329
out = {
    "kind": "combined_phase_A_estimates_not_execution_evidence",
    "created_at_utc": datetime.now(UTC).isoformat(),
    "original_scope_path": str(SCOPE.relative_to(ROOT)),
    "original_scope_sha256": sha(SCOPE.read_bytes()),
    "batch_checks": checks,
    "unique_SQL": {
        "scope": 143,
        "attempted": 99,
        "estimated": 98,
        "compile_error": 1,
        "unattempted": 44,
        "over_cap_estimates": sum(r["status"] == "estimate_above_24_GiB" for r in all_outcomes),
    },
    "logical_uses": {
        role: {key: logical_status[(role, key)] for key in ("estimated", "error", "unattempted")}
        for role in ("gold", "prediction")
    },
    "full_campaign_estimated_bytes": None,
    "known_component_estimated_bytes": sum(
        r["known_component_estimated_bytes"] for r in per_run.values()
    ),
    "per_run": dict(per_run),
    "query_inventory": queries,
    "no_new_live_queries": True,
    "free_allowance_remaining_bytes": None,
    "execution_accuracy": None,
    "limitations": [
        "First 25 estimates are SDK-observed scalars; "
        "raw HTTP statistics not preserved for that batch.",
        "Continuation has 74 raw HTTP bodies, including 73 estimates and the original 404.",
        "Both batches reuse only preparatory estimates; no live gold evidence reused.",
        "Fixed SQL hashes do not make public source data immutable.",
        "Current CLI19 initial aggregate guard blocks an entire run if any request "
        "exceeds per-query cap. No policy or implementation changes made.",
    ],
}
write(SECOND / "combined-estimates.json", out)
with (SECOND / "logical-estimates.jsonl").open("x") as stream:
    for row in logical_rows:
        stream.write(json.dumps(row, ensure_ascii=False) + "\n")
print(
    json.dumps(
        {
            "unique_SQL": out["unique_SQL"],
            "logical_uses": out["logical_uses"],
            "known_component_estimated_bytes": out["known_component_estimated_bytes"],
            "full_campaign_estimate": None,
            "journal_checks": "pass",
            "logical_rows": len(logical_rows),
        },
        indent=2,
    )
)
