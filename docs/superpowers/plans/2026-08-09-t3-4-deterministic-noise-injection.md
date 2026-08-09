# T3.4 Deterministic Noise Injection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a byte-stable Stage C-to-D augmentation pipeline that appends exactly 150 validated noisy English questions while preserving every GoogleSQL and provenance field.

**Architecture:** Pure contracts and transformations generate anchor-safe candidates without I/O. A deterministic allocator owns exact quotas and artifact validation; a thin Click CLI owns JSONL loading, atomic publication, and manifest hashes. Full-size generated fixtures keep tests independent of the credential-gated Stage C artifact.

**Tech Stack:** Python 3.11, standard library `dataclasses`, `hashlib`, `json`, `random`, `re`; Click 8; existing paraphrase validators; pytest 8; Ruff.

## Global Constraints

- Input is exactly 3,000 valid Stage C rows; output is exactly 3,150 rows.
- Append exactly 150 variants with quotas `typo=38`, `abbrev=38`, `fragment=37`, `mixed_case=37`.
- Seed is 42; output must be byte-stable for identical source bytes and configuration.
- Every source contributes at most one noisy variant.
- Allowed `noise_type` values are exactly `typo`, `abbrev`, `fragment`, and `mixed_case`.
- SQL, `record_sha256`, slot values, entity metadata, and Stage B/C metadata are immutable.
- T3.3 numeric/date/token/entity anchors must remain valid after transformation.
- Final files are atomically replaced only after complete validation.
- The 30-row manual audit is seed-42 deterministic and remains incomplete until a reviewer records at least 27 decipherable rows.

---

### Task 1: Noise contracts, dictionary, and pure transforms

**Files:**
- Create: `src/nl2sparql/dataset/noise/__init__.py`
- Create: `src/nl2sparql/dataset/noise/contracts.py`
- Create: `src/nl2sparql/dataset/noise/transforms.py`
- Create: `src/nl2sparql/dataset/noise/abbreviations.json`
- Create: `tests/unit/test_noise_transforms.py`

**Interfaces:**
- Produces `NoiseType`, `NoiseConfig`, `NoiseValidationError`, `load_abbreviations(path)`, `protected_terms(record, entity_index)`, and `transform_question(question, noise_type, abbreviations, protected, rng)`.
- `NoiseConfig()` defaults to seed 42 and the exact 38/38/37/37 quotas; construction rejects any other total than 150.
- `transform_question` returns `str | None`; `None` means that record is ineligible for that noise type.

- [ ] **Step 1: Write strict contract and dictionary tests**

```python
def test_noise_config_has_exact_contract() -> None:
    config = NoiseConfig()
    assert config.seed == 42
    assert config.quotas == {
        NoiseType.TYPO: 38,
        NoiseType.ABBREV: 38,
        NoiseType.FRAGMENT: 37,
        NoiseType.MIXED_CASE: 37,
    }
    assert sum(config.quotas.values()) == 150


def test_abbreviations_are_nonempty_normalized_and_exclude_entities() -> None:
    values = load_abbreviations()
    assert values["transactions"] == ("txs", "txns")
    assert all(key == key.casefold() for key in values)
    assert "binance" not in values
    assert "tornado cash" not in values
```

- [ ] **Step 2: Write pure transformation and anchor-protection tests**

```python
@pytest.mark.parametrize("noise_type", list(NoiseType))
def test_transform_changes_only_eligible_unprotected_text(noise_type: NoiseType) -> None:
    question = "Show transactions from Binance between 2026-06-01 and 2026-06-02?"
    protected = {"binance", "2026-06-01", "2026-06-02"}
    transformed = transform_question(
        question,
        noise_type,
        load_abbreviations(),
        protected,
        random.Random(42),
    )
    assert transformed is not None
    assert transformed != question
    assert "Binance" in transformed
    assert "2026-06-01" in transformed
    assert "2026-06-02" in transformed


def test_protected_terms_include_slots_and_dictionary_labels() -> None:
    terms = protected_terms(stage_c_record(), entity_index())
    assert "0x1111111111111111111111111111111111111111" in terms
    assert "binance" in terms
    assert "binance hot wallet" in terms
    assert "2026-06-01" in terms
```

- [ ] **Step 3: Run the tests and confirm RED**

Run: `uv run pytest tests/unit/test_noise_transforms.py -q`

Expected: collection fails because `nl2sparql.dataset.noise` does not exist.

- [ ] **Step 4: Implement contracts and the versioned dictionary**

```python
class NoiseType(StrEnum):
    TYPO = "typo"
    ABBREV = "abbrev"
    FRAGMENT = "fragment"
    MIXED_CASE = "mixed_case"


@dataclass(frozen=True)
class NoiseConfig:
    seed: int = 42
    quotas: Mapping[NoiseType, int] = field(default_factory=lambda: dict(DEFAULT_QUOTAS))

    def __post_init__(self) -> None:
        if dict(self.quotas) != DEFAULT_QUOTAS:
            raise NoiseValidationError("noise quotas must equal the T3.4 contract")
```

The JSON dictionary must include at least `transaction`, `transactions`, `address`, `addresses`, `token transfer`, `token transfers`, `between`, `greater than`, `less than`, `average`, `maximum`, `minimum`, `number of`, and `contract`, with nonempty unique string options.

- [ ] **Step 5: Implement protected spans and four single-edit transforms**

Use case-insensitive regex spans for every protected term, then choose only candidates whose spans do not overlap. Typo swaps one internal adjacent letter; abbreviation applies one longest phrase; fragment removes one matched scaffold/article/question mark; mixed case uppercases one non-uppercase word or alternates its case when already uppercase. Return `None` when no eligible change exists.

- [ ] **Step 6: Run focused GREEN and static checks**

Run:

```bash
uv run pytest tests/unit/test_noise_transforms.py -q
uv run ruff check src/nl2sparql/dataset/noise tests/unit/test_noise_transforms.py
uv run ruff format --check src/nl2sparql/dataset/noise tests/unit/test_noise_transforms.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 7: Commit Task 1**

```bash
git add src/nl2sparql/dataset/noise tests/unit/test_noise_transforms.py
git commit -m "feat(dataset): add deterministic noise transforms"
```

### Task 2: Exact-quota allocator and final validation

**Files:**
- Create: `src/nl2sparql/dataset/noise/pipeline.py`
- Create: `tests/unit/test_noise_pipeline.py`
- Modify: `src/nl2sparql/dataset/noise/__init__.py`

**Interfaces:**
- Consumes `NoiseConfig`, `NoiseType`, `transform_question`, T3.3 `validate_stage_c_records`, `validate_question_anchors`, and `normalized_levenshtein`.
- Produces `inject_noise(records, abbreviations, entity_index, config) -> list[dict[str, Any]]`, `validate_stage_d_records(stage_c, stage_d, entity_index, config) -> NoiseStats`, and immutable `NoiseStats`.

- [ ] **Step 1: Write a full-size valid Stage C fixture factory**

```python
def stage_c_records() -> list[dict[str, object]]:
    rows = []
    for index in range(3000):
        question = (
            f"Show transaction number {index} between 2026-06-01 and 2026-06-02?"
        )
        rows.append({
            "id": f"stage-c-{index:04d}",
            "parent_id": f"stage-b-{index // 3:04d}",
            "nl": question,
            "nl_normalized": normalize_question(question),
            "sql": f"SELECT {index} AS row_id",
            "record_sha256": f"{index:064x}",
            "slot_values": {
                "n": index,
                "start_date": "2026-06-01",
                "end_date": "2026-06-02",
            },
            "entities_used": [],
            "stage_c": {"pairwise_distances": [0.4, 0.5, 0.6]},
        })
    return rows
```

- [ ] **Step 2: Write RED tests for exact deterministic allocation**

```python
def test_inject_noise_is_exact_byte_stable_and_input_order_independent() -> None:
    source = stage_c_records()
    first = inject_noise(source, load_abbreviations(), {}, NoiseConfig())
    second = inject_noise(list(reversed(source)), load_abbreviations(), {}, NoiseConfig())
    assert canonical_noisy_rows(first) == canonical_noisy_rows(second)
    assert len(first) == 3150
    noisy = [row for row in first if "noise_type" in row]
    assert Counter(row["noise_type"] for row in noisy) == {
        "typo": 38,
        "abbrev": 38,
        "fragment": 37,
        "mixed_case": 37,
    }
    assert len({row["noise_parent_id"] for row in noisy}) == 150
```

- [ ] **Step 3: Write RED tests for immutability and rejection gates**

```python
def test_validator_proves_source_immutability_and_anchor_preservation() -> None:
    source = stage_c_records()
    output = inject_noise(source, load_abbreviations(), {}, NoiseConfig())
    stats = validate_stage_d_records(source, output, {}, NoiseConfig())
    assert stats.original_count == 3000
    assert stats.noisy_count == 150
    assert stats.output_count == 3150
    parent_by_id = {row["id"]: row for row in source}
    for row in output[3000:]:
        parent = parent_by_id[row["noise_parent_id"]]
        assert row["sql"] == parent["sql"]
        assert row["record_sha256"] == parent["record_sha256"]


def test_validator_rejects_sql_mutation_duplicate_source_and_distance_drift() -> None:
    source = stage_c_records()
    output = inject_noise(source, load_abbreviations(), {}, NoiseConfig())
    output[3000]["sql"] = "SELECT 'mutated'"
    with pytest.raises(NoiseValidationError, match="immutable"):
        validate_stage_d_records(source, output, {}, NoiseConfig())
```

- [ ] **Step 4: Run tests and confirm RED**

Run: `uv run pytest tests/unit/test_noise_pipeline.py -q`

Expected: import failure for the missing `pipeline` module.

- [ ] **Step 5: Implement deterministic candidate allocation**

For each `NoiseType` in enum order, derive an integer RNG seed from SHA-256 of `f"{config.seed}:{noise_type.value}"`, shuffle sorted source IDs, skip already selected IDs, create a candidate, validate anchors and type-specific distance, then accept until the exact quota is filled. Raise `NoiseValidationError("insufficient valid <type> candidates")` before returning if a quota cannot be filled.

- [ ] **Step 6: Implement complete Stage D validation and stats**

`NoiseStats` contains source/output/noisy counts, per-type counts, unique raw count, unique normalized count, and mean/max nonzero distance. Compare each noisy row to the source after removing only `id`, `nl`, `noise_parent_id`, `nl_original`, `noise_type`, `noise_seed`, and `noise_distance`. Re-run anchor validation and recompute distance rather than trusting stored metadata.

- [ ] **Step 7: Run Task 1+2 GREEN and static checks**

Run:

```bash
uv run pytest tests/unit/test_noise_transforms.py tests/unit/test_noise_pipeline.py -q
uv run ruff check src/nl2sparql/dataset/noise tests/unit/test_noise_transforms.py tests/unit/test_noise_pipeline.py
uv run ruff format --check src/nl2sparql/dataset/noise tests/unit/test_noise_transforms.py tests/unit/test_noise_pipeline.py
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 8: Commit Task 2**

```bash
git add src/nl2sparql/dataset/noise tests/unit/test_noise_pipeline.py
git commit -m "feat(dataset): allocate exact Stage D noise quotas"
```

### Task 3: Atomic artifacts, manifest, CLI, and notebook

**Files:**
- Create: `src/nl2sparql/dataset/noise/artifacts.py`
- Create: `scripts/11_inject_noise.py`
- Create: `tests/unit/test_noise_artifacts.py`
- Create: `notebooks/10_noise_injection.ipynb`
- Modify: `src/nl2sparql/dataset/noise/__init__.py`

**Interfaces:**
- Produces `file_sha256(path)`, `build_noise_manifest(...)`, `validate_noise_manifest(...)`, and CLI modes `generate` and `validate-output`.
- Reuses T3.3 `write_jsonl_atomic`, `write_json_atomic`, and `deterministic_audit_ids` rather than duplicating serializers.

- [ ] **Step 1: Write RED tests for manifest evidence**

```python
def test_manifest_records_hashes_counts_quotas_and_deterministic_audit_ids(tmp_path: Path) -> None:
    source_path, output_path = write_valid_artifacts(tmp_path)
    manifest = build_noise_manifest(
        source_path=source_path,
        output_path=output_path,
        stage_c=load_jsonl(source_path),
        stage_d=load_jsonl(output_path),
        stats=validated_stats(),
        config=NoiseConfig(),
    )
    assert manifest["source"]["sha256"] == file_sha256(source_path)
    assert manifest["output"]["sha256"] == file_sha256(output_path)
    assert manifest["output"]["records"] == 3150
    assert len(manifest["manual_audit"]["record_ids"]) == 30
    assert manifest["manual_audit"]["completed"] is False
```

- [ ] **Step 2: Write RED CLI tests for missing input and atomic publication**

```python
def test_cli_missing_stage_c_fails_without_creating_outputs(tmp_path: Path) -> None:
    output = tmp_path / "stage-d.jsonl"
    manifest = tmp_path / "noise-config.json"
    result = CliRunner().invoke(
        script.main,
        ["--source", str(tmp_path / "missing.jsonl"), "--output", str(output),
         "--manifest", str(manifest)],
    )
    assert result.exit_code != 0
    assert not output.exists()
    assert not manifest.exists()


def test_cli_generates_then_revalidates_complete_artifacts(tmp_path: Path) -> None:
    source = write_stage_c_fixture(tmp_path)
    result = invoke_generate(source, tmp_path)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["output_records"] == 3150
    assert invoke_validate_output(source, tmp_path).exit_code == 0
```

- [ ] **Step 3: Run tests and confirm RED**

Run: `uv run pytest tests/unit/test_noise_artifacts.py -q`

Expected: import failure for the missing artifact and CLI modules.

- [ ] **Step 4: Implement manifest construction and validation**

Hash source, output, and the abbreviation dictionary from bytes. Record exact quotas/counts, selected source IDs, stats, and 30 noisy audit IDs sampled with seed 42. Manifest validation compares every stored hash/count/stat to freshly recomputed values and requires manual audit fields to be either the untouched incomplete contract or a completed result with exactly 30 decisions and at least 27 decipherable.

- [ ] **Step 5: Implement Click orchestration**

Default paths are `data/dataset/raw/synthetic-stage-c.jsonl`, `synthetic-stage-d.jsonl`, and `noise-config.json`. Generate mode loads source and dictionary, injects/validates entirely in memory, writes Stage D atomically, builds the manifest from final bytes, and writes the manifest atomically. If manifest construction fails after Stage D replacement, delete only the newly written Stage D when no previous Stage D existed; when a previous artifact exists, preserve it by staging both siblings before coordinated replacement.

- [ ] **Step 6: Create the analysis notebook**

Notebook cells import source functions, display Python/package versions, load `noise-config.json`, show exact type counts and 30 audit rows, and compute the manual decipherability ratio from filled decisions. With artifacts absent, its final cell prints the credential-gated message without error. Keep source logic out of the notebook.

- [ ] **Step 7: Run focused GREEN and static checks**

Run:

```bash
uv run pytest tests/unit/test_noise_transforms.py tests/unit/test_noise_pipeline.py tests/unit/test_noise_artifacts.py -q
uv run ruff check src/nl2sparql/dataset/noise scripts/11_inject_noise.py tests/unit/test_noise_*.py
uv run ruff format --check src/nl2sparql/dataset/noise scripts/11_inject_noise.py tests/unit/test_noise_*.py notebooks/10_noise_injection.ipynb
uv run python -m json.tool notebooks/10_noise_injection.ipynb >/dev/null
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/nl2sparql/dataset/noise scripts/11_inject_noise.py tests/unit/test_noise_artifacts.py notebooks/10_noise_injection.ipynb
git commit -m "feat(dataset): publish validated Stage D artifacts"
```

### Task 4: Task migration, decision evidence, and credential-gated closure

**Files:**
- Rewrite: `docs/tasks/phase-3-dataset/04-noise-injection.md`
- Modify: `docs/memory/05-DECISION_LOG.md`
- Modify: `docs/superpowers/plans/2026-08-09-t3-4-deterministic-noise-injection.md`

**Interfaces:**
- Documents the exact GoogleSQL Stage D contract, commands, verification evidence, and the dependency on T3.3 live artifacts.

- [ ] **Step 1: Run the default CLI and capture the honest gate**

Run: `uv run python scripts/11_inject_noise.py --mode generate`

Expected in the current environment: nonzero exit naming the missing `synthetic-stage-c.jsonl`; no Stage D or manifest is created.

- [ ] **Step 2: Rewrite the task from SPARQL/probabilistic wording to the approved contract**

Mark implementation/test/atomic-publication acceptance checked. Leave final 3,150 artifact, 30-row manual audit, and source/output hash evidence unchecked. State `implementation complete; artifact blocked by T3.3 credential gate` without reducing acceptance.

- [ ] **Step 3: Add the decision-log entry**

Record why exact deterministic quotas replaced Bernoulli selection, why only structural phrases may be abbreviated, how SQL/provenance immutability is proven, and why manual decipherability remains a live acceptance gate.

- [ ] **Step 4: Run final verification from the clean implementation state**

Run:

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run python -m json.tool notebooks/10_noise_injection.ipynb >/dev/null
git diff --check
```

Expected: full tests pass; Ruff, format, notebook JSON, and whitespace checks exit 0.

- [ ] **Step 5: Commit and push the checkpoint**

```bash
git add docs/tasks/phase-3-dataset/04-noise-injection.md docs/memory/05-DECISION_LOG.md docs/superpowers/plans/2026-08-09-t3-4-deterministic-noise-injection.md
git commit -m "docs(dataset): record Stage D credential gate"
git push origin wip/continuous-backlog
```

- [ ] **Step 6: Verify Git evidence**

Run:

```bash
git status -sb
git rev-parse HEAD
git rev-parse '@{upstream}'
```

Expected: worktree clean, no ahead/behind marker, and local/upstream hashes equal.
