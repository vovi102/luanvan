"""Read-only local consistency audit; no provider client or execution requests."""

import gzip
import hashlib
import json
import runpy
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.evaluation.artifacts import load_and_verify_artifact

root = Path.cwd()
base = root / "docs/evidence/t54-bigquery-review-2026-10-24"
checks = {}


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


manifest = read(base / "manifest.json")
for entry in manifest["files"]:
    path = base / entry["path"]
    require(path.stat().st_size == entry["bytes"] and sha(path) == entry["sha256"], entry["path"])
checks["review_package_payload_hashes_and_sizes"] = len(manifest["files"])
for entry in manifest["frozen_review_inputs"]:
    require(
        sha(root / entry["original_path"]) == entry["sha256"] == sha(base / entry["snapshot_path"]),
        entry["original_path"],
    )
checks["frozen_review_inputs_equal_current"] = len(manifest["frozen_review_inputs"])
for entry in read(base / "sources/manifest.json"):
    if "path" in entry:
        path = root / entry["path"]
        data = gzip.decompress(path.read_bytes())
        require(sha(path) == entry["gzip_sha256"], "gzip source")
        require(
            len(data) == entry["bytes"]
            and hashlib.sha256(data).hexdigest() == entry["uncompressed_sha256"],
            "uncompressed source",
        )
checks["compressed_and_uncompressed_source_hashes"] = 4

proposal = read("configs/t54/b12-bigquery-review-proposal.json")
scope = read(base / "dry-run-scope.json")
require(
    sha(base / "dry-run-scope.json") == proposal["phase_a"]["scope_file_sha256"], "scope digest"
)
require(
    proposal["allow_dry_run"] is False
    and proposal["allow_bigquery"] is False
    and proposal["authorization"] is None,
    "authorization",
)
require(
    proposal["paid_spend_authorized_usd"] == "0.00"
    and proposal["billing_state"]["billing_enabled"] is False,
    "free only",
)
require(
    scope["dry_run"] is True
    and scope["allow_live_execution"] is False
    and scope["use_legacy_sql"] is False
    and scope["use_query_cache"] is False,
    "scope flags",
)
require(
    scope["maximum_bytes_billed"] == proposal["phase_a"]["maximum_bytes_billed"] == 24 * 1024**3,
    "cap",
)
require(
    scope["project"] == proposal["job_project"] == "nl2sparql-thesis"
    and scope["location"] == proposal["location"] == "US",
    "project/location",
)
require(proposal["free_only_policy"]["free_allowance_remaining_bytes"] is None, "unknown allowance")
runs = {}
expected_uses = {}
for entry in proposal["execution_scope"]["runs"]:
    path = root / entry["canonical_path"]
    require(sha(path) == entry["canonical_file_sha256"], "canonical digest")
    artifact = load_and_verify_artifact(path)
    body = read(path)["body"]
    require(
        body["run_id"] == entry["run_id"]
        and body["baseline_id"] == entry["baseline"]
        and body["test_case_count"] == len(body["cases"]) == 100,
        "run identity/N",
    )
    require(not artifact.provenance.synthetic, "synthetic")
    runs[entry["run_id"]] = entry
    counts = Counter()
    for case in body["cases"]:
        for role, sql in [
            ("gold", case["gold_sql"]),
            ("prediction", case["predicted_sql"] if case["prediction_status"] == "ok" else None),
        ]:
            if sql is not None:
                expected_uses[(body["run_id"], case["case_id"], role)] = sql
                counts[role] += 1
    require(
        counts["gold"] == entry["gold_queries_max"]
        and counts["prediction"] == entry["predicted_queries_max"],
        "run scope count",
    )
require(len(runs) == 12, "twelve runs")
actual_uses = {}
unique_roles = Counter()
seen = set()
for query in scope["queries"]:
    digest = hashlib.sha256(query["sql"].encode()).hexdigest()
    require(digest == query["sql_sha256"] and digest not in seen, "unique SQL hash")
    seen.add(digest)
    validate_sql_text(query["sql"])
    unique_roles.update(set(use["role"] for use in query["uses"]))
    for use in query["uses"]:
        key = (use["run_id"], use["case_id"], use["role"])
        require(key not in actual_uses, "duplicate logical use")
        entry = runs[use["run_id"]]
        require(
            use["canonical_path"] == entry["canonical_path"]
            and use["canonical_file_sha256"] == entry["canonical_file_sha256"],
            "use source",
        )
        actual_uses[key] = query["sql"]
require(actual_uses == expected_uses, "lossless logical mapping")
require(
    len(seen) == scope["unique_sql_count"] == proposal["phase_a"]["dry_run_requests_max"] == 143,
    "143 requests",
)
require(unique_roles == Counter(gold=100, prediction=43), "unique roles")
logical = Counter(k[2] for k in actual_uses)
require(
    logical == Counter(scope["logical_request_counts"]) == Counter(gold=1200, prediction=129),
    "logical totals",
)
checks["canonical_codec_and_N100"] = len(runs)
checks["unique_sql_hashes_and_static_safety"] = len(seen)
checks["unique_sql_by_role"] = dict(unique_roles)
checks["exact_source_bound_logical_uses"] = dict(logical)

policy = Path(proposal["privacy"]["policy_path"])
worksheets = read(proposal["privacy"]["worksheets_path"])
require(
    sha(policy) == proposal["privacy"]["policy_sha256"] == worksheets["policy_sha256"],
    "policy digest",
)
require(
    sha(proposal["privacy"]["worksheets_path"]) == proposal["privacy"]["worksheets_sha256"],
    "worksheet digest",
)
require(
    worksheets["review_decision"] is None and len(worksheets["reviews"]) == 4, "unsigned reviews"
)
for review in worksheets["reviews"]:
    require(
        review["reviewer_id"] is None
        and review["reviewed_at"] is None
        and review["data_egress"] == "provider",
        "review fields",
    )
    require(
        sha(review["test_set_path"]) == review["test_set_sha256"]
        and review["policy_sha256"] == sha(policy),
        "snapshot/policy",
    )
require(
    {(r["baseline_id"], r["language"]) for r in worksheets["reviews"]}
    == {(baseline, language) for baseline in ["b1", "b2"] for language in ["en", "vi"]},
    "four roles",
)
approval = read("configs/t54/phase-a-approval.template.json")
require(
    approval["proposal_file_sha256"] == sha("configs/t54/b12-bigquery-review-proposal.json"),
    "approval proposal",
)
require(
    approval["privacy_policy_sha256"] == sha(policy)
    and approval["dry_run_scope_sha256"] == sha(base / "dry-run-scope.json"),
    "approval scope",
)
require(
    approval["authorization_recorded"] is False
    and all(approval[k] is None for k in ["reviewer_id", "reviewed_at_utc", "decision"]),
    "unsigned decision",
)
ledger = read("configs/t54/free-tier-ledger.template.json")
require(
    ledger["reservations"] == []
    and ledger["verified_remaining_processed_bytes"] is None
    and ledger["verified_remaining_billed_bytes"] is None,
    "empty ledger",
)
checks["unsigned_privacy_worksheets"] = 4
checks["unsigned_approval_and_uninitialized_ledger"] = "pass"

# Reproduce offline artifacts in memory using the existing source/adapter checks.
module = runpy.run_path(str(root / "scripts/28_prepare_t54_offline.py"))
files, _ = module["prepare"](root, root / module["MATRIX"])
for name, payload in files.items():
    require(
        payload == (root / module["OUTPUT"] / name).read_bytes(), "offline reproduction: " + name
    )
checks["byte_identical_offline_artifacts_reproduced_in_memory"] = len(files)
checks["retained_setup_failures_source_manifests"] = (
    "22 and 45 entries verified by existing prepare()"
)
result = {
    "kind": "T5.4_local_review_reverification_not_execution_evidence",
    "checked_at_utc": datetime.now(UTC).isoformat(),
    "audit_script_sha256": sha(Path(__file__)),
    "review_manifest_sha256": sha(base / "manifest.json"),
    "proposal_sha256": sha("configs/t54/b12-bigquery-review-proposal.json"),
    "policy_sha256": sha(policy),
    "scope_sha256": sha(base / "dry-run-scope.json"),
    "checks": checks,
    "network_requests_performed": False,
    "bigquery_requests_performed": False,
    "scientific_status": "blocked",
    "remaining_gates": [
        "real privacy decision and reviewer identity/access/retention",
        "separate phase A dry-run authorization",
        "current dry-run estimates and authoritative free allowance",
        "new privacy-bound canonical hashes and separate live approval",
        "genuine sealed execution evidence/reports/comparisons",
        "B3 feasible configuration and resource plan",
    ],
}
print(json.dumps(result, ensure_ascii=False, indent=2))
