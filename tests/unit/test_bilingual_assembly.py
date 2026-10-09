from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nl2sparql.dataset.bilingual.assembly import (
    AssemblyValidationError,
    HeldOutSource,
    artifact_lock,
    assign_group_splits,
    build_exclusion_index,
    build_manifest,
    load_exclusion_index,
    publish_artifacts,
    select_audit_sample,
    serialize_audit_events,
    serialize_exclusion_index,
    serialize_manifest,
    validate_artifacts,
    validate_audit,
    validate_audit_evidence,
    validate_no_leakage,
)
from nl2sparql.dataset.bilingual.contracts import (
    AUDIT_SCHEMA_VERSION,
    AuditEvent,
    AuditSummary,
    ExpandedTrainingRecord,
    SplitConfig,
)
from nl2sparql.dataset.bilingual.rendering import (
    diversity_report,
    expanded_record_digest,
    serialize_records,
)
from nl2sparql.dataset.paraphrase.quality import normalize_question


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _record(
    question: str,
    *,
    record_id: str = "record-1",
    language: str = "en",
    style: str = "formal",
    family_id: str = "family-1",
    template_id: str = "T_COUNT_TX_IN_RANGE",
) -> ExpandedTrainingRecord:
    record = ExpandedTrainingRecord(
        id=record_id,
        language=language,
        style=style,
        semantic_family_id=family_id,
        catalog_entry_id=f"{template_id}__{language}__{style}",
        catalog_entry_sha256="a" * 64,
        source_record_id=family_id,
        source_record_sha256="b" * 64,
        source_template_sha256="c" * 64,
        renderer_version="deterministic-bilingual-renderer-v1",
        question=question,
        normalized_question=normalize_question(question),
        sql="SELECT 1 AS value",
        slot_values=(("n", 1),),
        expected_columns=("value",),
        schema_elements=("fixture.value",),
        entities_used=(),
        semantic_anchors=(("n", 1),),
        split="unassigned",
        producer_type="deterministic_template_renderer",
        author_type="agent",
        review_type="agent-reviewed",
        generation_model=None,
        provider=None,
        api_request_count=0,
        recorded_cost_usd=0.0,
        record_sha256="d" * 64,
    )
    return record


def test_exclusion_index_contains_only_irreversible_hashes_and_source_counts() -> None:
    english = "show the twelve most active addresses during this bounded ethereum interval"
    vietnamese = "hãy liệt kê mười hai địa chỉ hoạt động nhiều nhất trong giai đoạn này"
    sources = (
        HeldOutSource("english-t3.5", _sha(b"english-source"), (english,)),
        HeldOutSource("vietnamese-draft", _sha(b"vietnamese-source"), (vietnamese,)),
    )

    index = build_exclusion_index(sources, ngram_size=12)
    encoded = serialize_exclusion_index(index)

    assert index.ngram_size == 12
    assert index.source_sha256s == tuple(sorted(source.source_sha256 for source in sources))
    assert index.source_record_counts == (1, 1)
    assert len(index.normalized_text_sha256s) == 2
    assert index.index_sha256 == _sha(
        json.dumps(
            {key: value for key, value in asdict(index).items() if key != "index_sha256"},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    assert english.encode() not in encoded
    assert vietnamese.encode() not in encoded
    assert b"question_id" not in encoded
    assert b"review" not in encoded
    assert load_exclusion_index(encoded) == index


def test_leakage_validation_rejects_normalized_full_text_match() -> None:
    question = "Show 10 transactions from 2026-06-01 through 2026-06-02."
    index = build_exclusion_index(
        (HeldOutSource("english", _sha(b"source"), (question.upper(),)),),
        ngram_size=12,
    )

    with pytest.raises(AssemblyValidationError, match="full-text"):
        validate_no_leakage((_record(question),), index)


def test_leakage_validation_rejects_any_configured_high_order_ngram_match() -> None:
    held_out = "one two three four five six seven eight nine ten eleven twelve heldout ending"
    training = "prefix one two three four five six seven eight nine ten eleven twelve new ending"
    index = build_exclusion_index(
        (HeldOutSource("english", _sha(b"source"), (held_out,)),),
        ngram_size=12,
    )

    with pytest.raises(AssemblyValidationError, match="12-token"):
        validate_no_leakage((_record(training),), index)


def test_leakage_validation_reports_clean_records_without_raw_heldout_text() -> None:
    index = build_exclusion_index(
        (
            HeldOutSource(
                "english",
                _sha(b"source"),
                ("a completely unrelated held out sentence with enough distinct words",),
            ),
        ),
        ngram_size=12,
    )

    report = validate_no_leakage((_record("count one transaction in a safe interval"),), index)

    assert report.passed is True
    assert report.checked_records == 1
    assert report.full_text_matches == ()
    assert report.ngram_matches == ()


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        (lambda: build_exclusion_index((), ngram_size=12), "source"),
        (
            lambda: build_exclusion_index((HeldOutSource("empty", "a" * 64, ()),), ngram_size=12),
            "records",
        ),
        (
            lambda: build_exclusion_index(
                (HeldOutSource("bad", "not-a-digest", ("text",)),), ngram_size=12
            ),
            "SHA-256",
        ),
        (
            lambda: build_exclusion_index(
                (HeldOutSource("bad", "a" * 64, ("text",)),), ngram_size=3
            ),
            "ngram",
        ),
    ],
)
def test_exclusion_index_rejects_empty_or_malformed_input(operation, message: str) -> None:
    with pytest.raises(AssemblyValidationError, match=message):
        operation()


def test_exclusion_index_loader_rejects_extra_fields_and_digest_tampering() -> None:
    index = build_exclusion_index(
        (HeldOutSource("english", "a" * 64, ("held out text",)),), ngram_size=12
    )
    document = json.loads(serialize_exclusion_index(index))

    with pytest.raises(AssemblyValidationError, match="field set"):
        load_exclusion_index(json.dumps(document | {"question_id": "benchmark-1"}).encode())

    document["index_sha256"] = "0" * 64
    with pytest.raises(AssemblyValidationError, match="digest"):
        load_exclusion_index(json.dumps(document).encode())


def test_leakage_validator_accepts_only_derived_index_not_raw_paths(tmp_path: Path) -> None:
    raw_benchmark = tmp_path / "benchmark.jsonl"
    raw_benchmark.write_text('{"question":"held out wording"}\n', encoding="utf-8")

    with pytest.raises(TypeError):
        validate_no_leakage((_record("safe question"),), raw_benchmark)  # type: ignore[arg-type]


def test_leakage_recomputes_normalization_instead_of_trusting_record_metadata() -> None:
    held_out = "held out normalized sentence"
    index = build_exclusion_index((HeldOutSource("english", "a" * 64, (held_out,)),), ngram_size=12)
    stale = replace(_record(held_out), normalized_question="not the real normalization")

    with pytest.raises(AssemblyValidationError, match="normalized question"):
        validate_no_leakage((stale,), index)


def _family_records(family_count: int = 100) -> tuple[ExpandedTrainingRecord, ...]:
    result: list[ExpandedTrainingRecord] = []
    wording = {
        "formal": "Please enumerate the formally bounded transaction activity for",
        "conversational": "Could you show me what happened around the wallet owned by",
        "abbreviated": "tx stats acct",
        "alternative": "Inspect blockchain flows during the reporting window involving",
    }
    for family_index in range(family_count):
        family_id = f"family-{family_index:03d}"
        template_id = f"T_FIXTURE_{family_index % 25:02d}"
        for language in ("en", "vi"):
            for style in ("formal", "conversational", "abbreviated", "alternative"):
                record_id = f"{family_id}__{language}__{style}"
                result.append(
                    _record(
                        f"{wording[style]} family {family_index} in language {language}",
                        record_id=record_id,
                        language=language,
                        style=style,
                        family_id=family_id,
                        template_id=template_id,
                    )
                )
    return tuple(result)


def _audit_event(
    record: ExpandedTrainingRecord,
    index: int,
    *,
    faithful: bool = True,
    natural: bool = True,
    decision: str = "accept",
    reviewer_type: str = "agent",
    supersedes: str | None = None,
    minute: int | None = None,
) -> AuditEvent:
    timestamp = datetime(2026, 10, 8, tzinfo=UTC) + timedelta(
        minutes=index if minute is None else minute
    )
    return AuditEvent(
        schema_version=AUDIT_SCHEMA_VERSION,
        event_id=f"audit-{index:04d}",
        record_id=record.id,
        record_sha256=record.record_sha256,
        decision=decision,
        faithful=faithful,
        natural=natural,
        notes="reviewed against the Stage A semantics",
        reviewer_type=reviewer_type,
        reviewed_at=timestamp.isoformat(),
        supersedes_event_id=supersedes,
    )


def test_group_splits_are_deterministic_balanced_and_never_cross_families() -> None:
    records = _family_records()
    config = SplitConfig(seed=42, development_percent=10)

    first = assign_group_splits(records, config)
    second = assign_group_splits(tuple(reversed(records)), config)

    assert first == second
    by_family: dict[str, set[str]] = defaultdict(set)
    for record in first:
        by_family[record.semantic_family_id].add(record.split)
    assert all(len(splits) == 1 for splits in by_family.values())
    family_splits = Counter(next(iter(splits)) for splits in by_family.values())
    assert set(family_splits) == {"train", "development"}
    for split in ("train", "development"):
        split_records = [record for record in first if record.split == split]
        languages = Counter(record.language for record in split_records)
        styles = Counter(record.style for record in split_records)
        assert languages["en"] == languages["vi"]
        assert len(set(styles.values())) == 1
    assert all(record.record_sha256 != "d" * 64 for record in first)


@pytest.mark.parametrize(
    "config",
    [
        SplitConfig(seed=-1, development_percent=10),
        SplitConfig(seed=42, development_percent=0),
        SplitConfig(seed=42, development_percent=100),
    ],
)
def test_group_split_rejects_invalid_config(config: SplitConfig) -> None:
    with pytest.raises(AssemblyValidationError, match="split config"):
        assign_group_splits(_family_records(1), config)


def test_audit_samples_cover_each_intent_and_style_once_per_language() -> None:
    records = _family_records(25)

    english_ids = select_audit_sample(records, "en", seed=42)
    vietnamese_ids = select_audit_sample(tuple(reversed(records)), "vi", seed=42)

    assert len(english_ids) == len(set(english_ids)) == 100
    assert len(vietnamese_ids) == len(set(vietnamese_ids)) == 100
    by_id = {record.id: record for record in records}
    for language, sample_ids in (("en", english_ids), ("vi", vietnamese_ids)):
        selected = [by_id[record_id] for record_id in sample_ids]
        assert {record.language for record in selected} == {language}
        assert len({record.catalog_entry_id.split("__", 1)[0] for record in selected}) == 25
        assert Counter(record.style for record in selected) == {
            "formal": 25,
            "conversational": 25,
            "abbreviated": 25,
            "alternative": 25,
        }
        assert (
            len({(record.catalog_entry_id.split("__", 1)[0], record.style) for record in selected})
            == 100
        )


def test_audit_sample_fails_closed_when_an_intent_style_stratum_is_missing() -> None:
    records = tuple(
        record
        for record in _family_records(25)
        if not (
            record.language == "vi"
            and record.style == "alternative"
            and record.catalog_entry_id.startswith("T_FIXTURE_24__")
        )
    )

    with pytest.raises(AssemblyValidationError, match="25 intents"):
        select_audit_sample(records, "vi", seed=42)


def test_agent_audit_accepts_append_only_revisions_and_threshold_boundaries() -> None:
    records = _family_records(25)
    sample_ids = select_audit_sample(records, "en", seed=42)
    by_id = {record.id: record for record in records}
    sample = tuple(by_id[record_id] for record_id in sample_ids)
    events = [
        _audit_event(
            record,
            index,
            faithful=index >= 5,
            natural=index >= 10,
            decision="accept" if index >= 10 else "reject",
        )
        for index, record in enumerate(sample)
    ]
    first = events[0]
    events.append(
        _audit_event(
            sample[0],
            100,
            faithful=False,
            natural=False,
            decision="reject",
            supersedes=first.event_id,
            minute=100,
        )
    )

    summary = validate_audit(events, sample_ids, records=records, language="en")

    assert summary.sample_size == 100
    assert summary.faithful_count == 95
    assert summary.natural_count == 90
    assert summary.accepted_count == 90
    assert summary.passed is True


def test_agent_audit_rejects_weak_scores_fabricated_reviewers_and_bad_chains() -> None:
    records = _family_records(25)
    sample_ids = select_audit_sample(records, "vi", seed=42)
    by_id = {record.id: record for record in records}
    sample = tuple(by_id[record_id] for record_id in sample_ids)
    passing = [_audit_event(record, index) for index, record in enumerate(sample)]

    weak = list(passing)
    weak[:6] = [_audit_event(sample[index], index, faithful=False) for index in range(6)]
    with pytest.raises(AssemblyValidationError, match="95 faithful"):
        validate_audit(weak, sample_ids, records=records, language="vi")

    fabricated = list(passing)
    fabricated[0] = _audit_event(sample[0], 0, reviewer_type="human-independent")
    with pytest.raises(AssemblyValidationError, match="reviewer_type=agent"):
        validate_audit(fabricated, sample_ids, records=records, language="vi")

    bad_digest = list(passing)
    bad_digest[0] = replace(bad_digest[0], record_sha256="0" * 64)
    with pytest.raises(AssemblyValidationError, match="record digest"):
        validate_audit(bad_digest, sample_ids, records=records, language="vi")

    duplicate_initial = [*passing, _audit_event(sample[0], 100, minute=100)]
    with pytest.raises(AssemblyValidationError, match="supersedes"):
        validate_audit(duplicate_initial, sample_ids, records=records, language="vi")


def test_agent_audit_rejects_non_boolean_quality_values() -> None:
    records = _family_records(25)
    sample_ids = select_audit_sample(records, "en", seed=42)
    by_id = {record.id: record for record in records}
    events = [_audit_event(by_id[record_id], index) for index, record_id in enumerate(sample_ids)]
    events[0] = replace(events[0], faithful=2)  # type: ignore[arg-type]

    with pytest.raises(AssemblyValidationError, match="faithful.*boolean"):
        validate_audit(events, sample_ids, records=records, language="en")


def test_combined_audit_rejects_every_event_outside_both_samples() -> None:
    records = assign_group_splits(_family_records(26), SplitConfig())
    by_id = {record.id: record for record in records}
    events: list[AuditEvent] = []
    offset = 0
    sampled: set[str] = set()
    for language in ("en", "vi"):
        sample_ids = select_audit_sample(records, language, seed=42)
        sampled.update(sample_ids)
        events.extend(
            _audit_event(by_id[record_id], offset + index)
            for index, record_id in enumerate(sample_ids)
        )
        offset += 100
    extra = next(record for record in records if record.id not in sampled)
    events.append(_audit_event(extra, 200))

    with pytest.raises(AssemblyValidationError, match="outside the deterministic samples"):
        validate_audit_evidence(events, records=records, seed=42)


def test_combined_audit_uses_final_post_split_record_digests() -> None:
    records = assign_group_splits(_family_records(25), SplitConfig())
    by_id = {record.id: record for record in records}
    events: list[AuditEvent] = []
    offset = 0
    for language in ("en", "vi"):
        sample_ids = select_audit_sample(records, language, seed=42)
        events.extend(
            _audit_event(by_id[record_id], offset + index)
            for index, record_id in enumerate(sample_ids)
        )
        offset += 100

    summaries = validate_audit_evidence(events, records=records, seed=42)

    assert [summary.language for summary in summaries] == ["en", "vi"]
    assert all(summary.passed for summary in summaries)

    duplicate_across_languages = list(events)
    duplicate_across_languages[100] = replace(
        duplicate_across_languages[100], event_id=duplicate_across_languages[0].event_id
    )
    with pytest.raises(AssemblyValidationError, match="globally unique"):
        validate_audit_evidence(duplicate_across_languages, records=records, seed=42)


@pytest.fixture(scope="module")
def artifact_bundle():
    records = assign_group_splits(_family_records(1000), SplitConfig())
    by_id = {record.id: record for record in records}
    events: list[AuditEvent] = []
    summaries: list[AuditSummary] = []
    offset = 0
    for language in ("en", "vi"):
        sample_ids = select_audit_sample(records, language, seed=42)
        language_events = [
            _audit_event(by_id[record_id], offset + index)
            for index, record_id in enumerate(sample_ids)
        ]
        events.extend(language_events)
        summaries.append(
            validate_audit(
                language_events,
                sample_ids,
                records=records,
                language=language,
            )
        )
        offset += 100
    output_bytes = serialize_records(records)
    audit_bytes = serialize_audit_events(events)
    exclusion = build_exclusion_index(
        (
            HeldOutSource(
                "english",
                _sha(b"held-out-source"),
                ("unrelated held out benchmark wording that cannot match fixture records",),
            ),
        ),
        ngram_size=12,
    )
    exclusion_bytes = serialize_exclusion_index(exclusion)
    diversity = diversity_report(records)
    leakage = validate_no_leakage(records, exclusion)
    stage_a_bytes = b"accepted-stage-a-fixture\n"
    catalog_bytes = b'{"catalog":"fixture"}\n'
    config = SplitConfig()
    manifest = build_manifest(
        records,
        output_bytes=output_bytes,
        stage_a_bytes=stage_a_bytes,
        catalog_bytes=catalog_bytes,
        split_config=config,
        diversity=diversity,
        leakage=leakage,
        audit_summaries=tuple(summaries),
        audit_bytes=audit_bytes,
        exclusion_index=exclusion,
    )
    manifest_bytes = serialize_manifest(manifest)
    return {
        "records": records,
        "events": tuple(events),
        "output": output_bytes,
        "audit": audit_bytes,
        "exclusion": exclusion_bytes,
        "stage_a": stage_a_bytes,
        "catalog": catalog_bytes,
        "config": config,
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
    }


def test_manifest_records_exact_counts_hashes_quality_and_honest_provenance(
    artifact_bundle,
) -> None:
    manifest = artifact_bundle["manifest"]

    assert manifest["status"] == "completed"
    assert manifest["producer"] == {
        "producer_type": "deterministic_template_renderer",
        "author_type": "agent",
        "review_type": "agent-reviewed",
        "generation_model": None,
        "provider": None,
        "api_request_count": 0,
        "recorded_cost_usd": 0.0,
        "cost_note": "Recorded cost is operational evidence, not a provider billing statement.",
    }
    assert manifest["output"]["records"] == 8000
    assert manifest["output"]["sha256"] == _sha(artifact_bundle["output"])
    assert manifest["counts"]["language"] == {"en": 4000, "vi": 4000}
    assert manifest["counts"]["style"] == {
        "abbreviated": 2000,
        "alternative": 2000,
        "conversational": 2000,
        "formal": 2000,
    }
    assert manifest["counts"]["semantic_families"] == 1000
    assert len(manifest["counts"]["intent"]) == 25
    assert manifest["quality"]["diversity"]["minimum"] > 0.30
    assert manifest["quality"]["leakage"]["passed"] is True
    assert {summary["language"] for summary in manifest["quality"]["audits"]} == {
        "en",
        "vi",
    }
    assert manifest["sources"]["audit_sha256"] == _sha(artifact_bundle["audit"])
    assert (
        manifest["sources"]["exclusion_index_sha256"]
        == json.loads(artifact_bundle["exclusion"])["index_sha256"]
    )
    assert manifest["manifest_body_sha256"] == _sha(
        json.dumps(
            {key: value for key, value in manifest.items() if key != "manifest_body_sha256"},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    assert serialize_manifest(manifest) == artifact_bundle["manifest_bytes"]


def test_artifact_validation_recomputes_hashes_counts_leakage_and_audits(
    artifact_bundle,
) -> None:
    report = validate_artifacts(
        output_bytes=artifact_bundle["output"],
        manifest_bytes=artifact_bundle["manifest_bytes"],
        audit_bytes=artifact_bundle["audit"],
        exclusion_index_bytes=artifact_bundle["exclusion"],
        stage_a_bytes=artifact_bundle["stage_a"],
        catalog_bytes=artifact_bundle["catalog"],
        split_config=artifact_bundle["config"],
        expected_records=artifact_bundle["records"],
    )

    assert report.passed is True
    assert report.record_count == 8000
    assert report.semantic_family_count == 1000
    assert report.output_sha256 == _sha(artifact_bundle["output"])
    assert report.manifest_sha256 == _sha(artifact_bundle["manifest_bytes"])


@pytest.mark.parametrize("field", ["output", "manifest_bytes", "audit", "exclusion"])
def test_artifact_validation_rejects_tampered_bytes(artifact_bundle, field: str) -> None:
    values = {
        "output_bytes": artifact_bundle["output"],
        "manifest_bytes": artifact_bundle["manifest_bytes"],
        "audit_bytes": artifact_bundle["audit"],
        "exclusion_index_bytes": artifact_bundle["exclusion"],
        "stage_a_bytes": artifact_bundle["stage_a"],
        "catalog_bytes": artifact_bundle["catalog"],
        "split_config": artifact_bundle["config"],
        "expected_records": artifact_bundle["records"],
    }
    argument = {
        "output": "output_bytes",
        "manifest_bytes": "manifest_bytes",
        "audit": "audit_bytes",
        "exclusion": "exclusion_index_bytes",
    }[field]
    values[argument] += b"tamper"

    with pytest.raises(AssemblyValidationError):
        validate_artifacts(**values)


def test_artifact_validation_rejects_self_consistent_semantic_row_tampering(
    artifact_bundle,
) -> None:
    records = list(artifact_bundle["records"])
    changed = replace(records[0], sql="SELECT 2 AS forged_value", record_sha256="")
    records[0] = replace(changed, record_sha256=expanded_record_digest(changed))

    with pytest.raises(AssemblyValidationError, match="reconstructed source records"):
        validate_artifacts(
            output_bytes=serialize_records(tuple(records)),
            manifest_bytes=artifact_bundle["manifest_bytes"],
            audit_bytes=artifact_bundle["audit"],
            exclusion_index_bytes=artifact_bundle["exclusion"],
            stage_a_bytes=artifact_bundle["stage_a"],
            catalog_bytes=artifact_bundle["catalog"],
            split_config=artifact_bundle["config"],
            expected_records=artifact_bundle["records"],
        )


def test_three_file_publication_rejects_aliases_and_rolls_back_second_replace(
    tmp_path: Path,
    artifact_bundle,
) -> None:
    output = tmp_path / "training.jsonl"
    manifest = tmp_path / "manifest.json"
    audit = tmp_path / "audit.jsonl"
    with pytest.raises(AssemblyValidationError, match="paths must differ"):
        publish_artifacts(
            artifact_bundle["output"],
            artifact_bundle["manifest_bytes"],
            artifact_bundle["audit"],
            output_path=output,
            manifest_path=output,
            audit_path=audit,
        )

    output.write_bytes(b"old-output\n")
    manifest.write_bytes(b"old-manifest\n")
    audit.write_bytes(b"old-audit\n")
    calls = 0

    def fail_second_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated second replace failure")
        source.replace(target)

    with pytest.raises(OSError, match="second replace"):
        publish_artifacts(
            artifact_bundle["output"],
            artifact_bundle["manifest_bytes"],
            artifact_bundle["audit"],
            output_path=output,
            manifest_path=manifest,
            audit_path=audit,
            replace_file=fail_second_replace,
        )

    assert output.read_bytes() == b"old-output\n"
    assert manifest.read_bytes() == b"old-manifest\n"
    assert audit.read_bytes() == b"old-audit\n"
    assert not list(tmp_path.glob("*.tmp"))


def test_publication_lock_rejects_concurrent_nonblocking_writer(tmp_path: Path) -> None:
    paths = (
        tmp_path / "training.jsonl",
        tmp_path / "manifest.json",
        tmp_path / "audit.jsonl",
    )
    with artifact_lock(*paths):
        with pytest.raises(BlockingIOError):
            with artifact_lock(*paths, blocking=False):
                raise AssertionError("concurrent writer acquired the lock")


def test_interrupted_publication_recovers_before_next_lock(
    tmp_path: Path,
    artifact_bundle,
) -> None:
    output = tmp_path / "training.jsonl"
    manifest = tmp_path / "manifest.json"
    audit = tmp_path / "audit.jsonl"
    output.write_bytes(b"old-output\n")
    manifest.write_bytes(b"old-manifest\n")
    audit.write_bytes(b"old-audit\n")
    calls = 0

    def interrupt_second_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        source.replace(target)

    with pytest.raises(KeyboardInterrupt):
        publish_artifacts(
            artifact_bundle["output"],
            artifact_bundle["manifest_bytes"],
            artifact_bundle["audit"],
            output_path=output,
            manifest_path=manifest,
            audit_path=audit,
            replace_file=interrupt_second_replace,
        )

    with artifact_lock(output, manifest, audit):
        pass
    assert output.read_bytes() == b"old-output\n"
    assert manifest.read_bytes() == b"old-manifest\n"
    assert audit.read_bytes() == b"old-audit\n"
