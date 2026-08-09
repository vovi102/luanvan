from __future__ import annotations

import json
import re
import time
from collections import Counter
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from nl2sparql.sql.label_layer import DEFAULT_LOCATION
from nl2sparql.sql.schema import load_catalog, validate_catalog, validate_date_window

TEMPLATES_PATH = Path(__file__).with_name("templates.json")
PER_TEMPLATE_BYTES_CAP = 5_368_709_120
TOTAL_TEMPLATE_BYTES_CAP = 32_212_254_720
SUPPORTED_DIFFICULTIES = {"easy", "medium", "hard"}
SUPPORTED_CATEGORIES = {
    "simple_filter",
    "time_range",
    "entity_lookup",
    "transaction_aggregation",
    "top_k",
    "multi_hop",
    "class_level",
    "token_specific",
    "comparison",
    "temporal_pattern",
}
SUPPORTED_SLOT_TYPES = {
    "integer",
    "date",
    "decimal_wei",
    "ethereum_address",
    "transaction_hash",
    "block_number",
    "token_symbol",
    "entity_owner",
    "entity_category",
    "concept_class",
    "duration_minutes",
}
REQUIRED_FIELDS = {
    "id",
    "name",
    "category",
    "difficulty",
    "slots",
    "sql_template",
    "nl_seed",
    "expected_columns",
    "schema_elements",
    "cq_ids",
    "example_fill",
    "validation",
}
PLACEHOLDER_RE = re.compile(r"{([A-Za-z_][A-Za-z0-9_]*)}")
ADDRESS_RE = re.compile(r"^0x[a-f0-9]{40}$")
TRANSACTION_HASH_RE = re.compile(r"^0x[a-f0-9]{64}$")
MUTATION_RE = re.compile(
    r"\b(CREATE|DROP|ALTER|INSERT|UPDATE|DELETE|MERGE|TRUNCATE|EXPORT|CALL)\b",
    re.IGNORECASE,
)
TABLE_RE = re.compile(r"`([^`]+)`")
MANAGED_PREFIX = "nl2sparql-thesis.nl2sparql_analytics."


class TemplateValidationError(ValueError):
    """Raised when a query-template artifact or fill violates contract v2."""


@dataclass(frozen=True)
class TemplateSummary:
    template_count: int
    category_count: int
    difficulty_counts: dict[str, int]
    schema_element_count: int
    cq_count: int


@dataclass(frozen=True)
class TemplateDryRun:
    template_id: str
    estimated_bytes: int


@dataclass(frozen=True)
class TemplatePreflight:
    templates: tuple[TemplateDryRun, ...]
    total_estimated_bytes: int


@dataclass(frozen=True)
class TemplateExecutionResult:
    template_id: str
    row_count: int
    columns: tuple[str, ...]
    estimated_bytes: int
    processed_bytes: int
    billed_bytes: int
    wall_latency_ms: float
    server_latency_ms: float | None
    slot_millis: int
    cache_hit: bool


@dataclass(frozen=True)
class TemplateExecutionReport:
    preflight: TemplatePreflight
    results: tuple[TemplateExecutionResult, ...]

    @property
    def all_passed(self) -> bool:
        return len(self.results) == len(self.preflight.templates)


def load_templates(path: Path = TEMPLATES_PATH) -> list[dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TemplateValidationError(f"Unable to read template library: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TemplateValidationError(f"Invalid template JSON: {path}") from exc
    if not isinstance(value, list):
        raise TemplateValidationError("Template library must contain a list")
    return value


def _require_strings(value: object, owner: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(item, str) and item for item in value)
    ):
        raise TemplateValidationError(f"{owner} must be a non-empty string list")
    return value


def _catalog_references() -> tuple[set[str], set[str], set[str]]:
    catalog = load_catalog()
    validate_catalog(catalog)
    relations = set(catalog["analytical_relations"])
    elements = set(relations)
    for relation_id, relation in catalog["analytical_relations"].items():
        elements.update(f"{relation_id}.{field}" for field in relation["fields"])
    cq_ids = {question["id"] for question in catalog["competency_questions"]}
    return relations, elements, cq_ids


def _validate_slot_definition(name: str, definition: object, owner: str) -> None:
    if not isinstance(definition, dict):
        raise TemplateValidationError(f"{owner}.{name} must be an object")
    slot_type = definition.get("type")
    if slot_type not in SUPPORTED_SLOT_TYPES:
        raise TemplateValidationError(f"{owner}.{name} has unknown slot type {slot_type!r}")
    allowed = {"type", "min", "max", "description"}
    if set(definition) - allowed:
        raise TemplateValidationError(f"{owner}.{name} has unknown slot metadata")


def _escaped_slot_value(name: str, definition: Mapping[str, Any], value: object) -> str:
    slot_type = definition["type"]
    if slot_type in {"integer", "block_number", "duration_minutes"}:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TemplateValidationError(f"Slot {name} must be an {slot_type} integer")
        minimum = int(definition.get("min", 0 if slot_type == "block_number" else 1))
        maximum = int(definition.get("max", 100 if slot_type == "integer" else 10**12))
        if not minimum <= value <= maximum:
            raise TemplateValidationError(
                f"Slot {name} {slot_type} value must be between {minimum} and {maximum}"
            )
        return str(value)
    if slot_type == "date":
        if not isinstance(value, str):
            raise TemplateValidationError(f"Slot {name} must be an ISO date")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise TemplateValidationError(f"Slot {name} must be an ISO date") from exc
        return value
    if slot_type == "decimal_wei":
        text = str(value)
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
            raise TemplateValidationError(f"Slot {name} must be a non-negative decimal_wei")
        return text
    if slot_type == "ethereum_address":
        if not isinstance(value, str) or not ADDRESS_RE.fullmatch(value):
            raise TemplateValidationError(f"Slot {name} must be an ethereum_address")
        return value
    if slot_type == "transaction_hash":
        if not isinstance(value, str) or not TRANSACTION_HASH_RE.fullmatch(value):
            raise TemplateValidationError(f"Slot {name} must be a transaction_hash")
        return value
    if (
        not isinstance(value, str)
        or not value.strip()
        or any(character in value for character in "\n\r\0")
    ):
        raise TemplateValidationError(f"Slot {name} must be a non-empty {slot_type}")
    return value.replace("'", "''")


def render_template(template: Mapping[str, Any], values: Mapping[str, object] | None = None) -> str:
    slots = template.get("slots")
    if not isinstance(slots, dict):
        raise TemplateValidationError("Template slots must be an object")
    selected = template.get("example_fill") if values is None else values
    if not isinstance(selected, Mapping) or set(selected) != set(slots):
        raise TemplateValidationError("Template fill keys must exactly match slots")
    rendered_values = {
        name: _escaped_slot_value(name, definition, selected[name])
        for name, definition in slots.items()
    }
    if "start_date" in selected and "end_date" in selected:
        try:
            validate_date_window(
                date.fromisoformat(str(selected["start_date"])),
                date.fromisoformat(str(selected["end_date"])),
            )
        except ValueError as exc:
            message = "31 days" if "31 days" in str(exc) else "date window"
            raise TemplateValidationError(f"Invalid template {message}: {exc}") from exc
    sql_template = template.get("sql_template")
    if not isinstance(sql_template, str):
        raise TemplateValidationError("Template requires sql_template")
    try:
        return sql_template.format(**rendered_values)
    except (KeyError, ValueError) as exc:
        raise TemplateValidationError(f"Unable to render template: {exc}") from exc


def validate_template_library(
    templates: list[dict[str, Any]] | None = None,
) -> TemplateSummary:
    values = load_templates() if templates is None else templates
    if len(values) != 25:
        raise TemplateValidationError(f"Expected exactly 25 templates, received {len(values)}")
    _, known_elements, known_cqs = _catalog_references()
    ids: list[str] = []
    difficulties: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    used_elements: set[str] = set()
    used_cqs: set[str] = set()
    for index, template in enumerate(values):
        owner = f"templates[{index}]"
        if not isinstance(template, dict):
            raise TemplateValidationError(f"{owner} must be an object")
        if set(template) != REQUIRED_FIELDS:
            raise TemplateValidationError(
                f"{owner} must use contract v2 fields; received {sorted(template)}"
            )
        template_id = template.get("id")
        if not isinstance(template_id, str) or not template_id.startswith("T_"):
            raise TemplateValidationError(f"{owner}.id must be a stable T_ identifier")
        ids.append(template_id)
        difficulty = template.get("difficulty")
        category = template.get("category")
        if difficulty not in SUPPORTED_DIFFICULTIES:
            raise TemplateValidationError(f"{template_id} has invalid difficulty")
        if category not in SUPPORTED_CATEGORIES:
            raise TemplateValidationError(f"{template_id} has invalid category")
        difficulties[difficulty] += 1
        categories[category] += 1
        slots = template.get("slots")
        if not isinstance(slots, dict) or not slots:
            raise TemplateValidationError(f"{template_id}.slots must be a non-empty object")
        for name, definition in slots.items():
            _validate_slot_definition(name, definition, f"{template_id}.slots")
        placeholders = set(PLACEHOLDER_RE.findall(template["sql_template"])) | set(
            PLACEHOLDER_RE.findall(template["nl_seed"])
        )
        if placeholders != set(slots):
            raise TemplateValidationError(
                f"{template_id} placeholders must exactly match slots: {sorted(placeholders)}"
            )
        rendered = render_template(template)
        if not rendered.lstrip().upper().startswith(("SELECT", "WITH")):
            raise TemplateValidationError(f"{template_id} SQL must be read-only SELECT/WITH")
        if MUTATION_RE.search(rendered) or re.search(r"SELECT\s+\*", rendered, re.IGNORECASE):
            raise TemplateValidationError(f"{template_id} SQL must be read-only and explicit")
        table_refs = TABLE_RE.findall(rendered)
        if not table_refs or any(not ref.startswith(MANAGED_PREFIX) for ref in table_refs):
            raise TemplateValidationError(f"{template_id} must use managed fully qualified objects")
        expected_columns = _require_strings(
            template.get("expected_columns"), f"{template_id}.expected_columns"
        )
        if any(column not in rendered for column in expected_columns):
            raise TemplateValidationError(f"{template_id} expected column is not projected")
        schema_elements = set(
            _require_strings(template.get("schema_elements"), f"{template_id}.schema_elements")
        )
        unknown_elements = schema_elements - known_elements
        if unknown_elements:
            raise TemplateValidationError(
                f"{template_id} has unknown schema_elements: {sorted(unknown_elements)}"
            )
        cq_ids = set(_require_strings(template.get("cq_ids"), f"{template_id}.cq_ids"))
        unknown_cqs = cq_ids - known_cqs
        if unknown_cqs or "CQ24" in cq_ids:
            unsupported_cqs = unknown_cqs | (cq_ids & {"CQ24"})
            raise TemplateValidationError(
                f"{template_id} has unsupported/unknown cq_ids: {sorted(unsupported_cqs)}"
            )
        validation = template.get("validation")
        if not isinstance(validation, dict) or set(validation) != {
            "expect_non_empty",
            "scope_note",
        }:
            raise TemplateValidationError(f"{template_id}.validation has invalid shape")
        if not isinstance(validation["expect_non_empty"], bool) or not isinstance(
            validation["scope_note"], str
        ):
            raise TemplateValidationError(f"{template_id}.validation has invalid values")
        used_elements.update(schema_elements)
        used_cqs.update(cq_ids)
    if len(set(ids)) != len(ids):
        raise TemplateValidationError("Template IDs must be unique")
    if difficulties != {"easy": 8, "medium": 11, "hard": 6}:
        raise TemplateValidationError(f"Invalid difficulty distribution: {dict(difficulties)}")
    if set(categories) != SUPPORTED_CATEGORIES:
        raise TemplateValidationError("Template categories must cover all 10 approved values")
    return TemplateSummary(
        template_count=len(values),
        category_count=len(categories),
        difficulty_counts={key: difficulties[key] for key in ("easy", "medium", "hard")},
        schema_element_count=len(used_elements),
        cq_count=len(used_cqs),
    )


def _query_config(*, dry_run: bool, maximum_bytes_billed: int) -> bigquery.QueryJobConfig:
    return bigquery.QueryJobConfig(
        dry_run=dry_run,
        use_query_cache=False,
        use_legacy_sql=False,
        maximum_bytes_billed=maximum_bytes_billed,
    )


def _dry_run_template(
    client: Any,
    template: Mapping[str, Any],
    *,
    location: str,
    per_template_bytes_cap: int,
) -> int:
    job = client.query(
        render_template(template),
        job_config=_query_config(
            dry_run=True,
            maximum_bytes_billed=per_template_bytes_cap,
        ),
        location=location,
    )
    return int(getattr(job, "total_bytes_processed", 0) or 0)


def _validate_budget(
    template_id: str,
    estimated_bytes: int,
    per_template_bytes_cap: int,
) -> None:
    if estimated_bytes > per_template_bytes_cap:
        raise TemplateValidationError(
            f"{template_id} exceeds the 5 GiB per-template cap: {estimated_bytes} bytes"
        )


def dry_run_templates(
    client: Any,
    *,
    templates: list[dict[str, Any]] | None = None,
    location: str = DEFAULT_LOCATION,
    per_template_bytes_cap: int = PER_TEMPLATE_BYTES_CAP,
    total_bytes_cap: int = TOTAL_TEMPLATE_BYTES_CAP,
) -> TemplatePreflight:
    """Compile all rendered templates and fail before execution on a budget breach."""
    values = load_templates() if templates is None else templates
    validate_template_library(values)
    results: list[TemplateDryRun] = []
    for template in values:
        template_id = template["id"]
        estimated_bytes = _dry_run_template(
            client,
            template,
            location=location,
            per_template_bytes_cap=per_template_bytes_cap,
        )
        _validate_budget(template_id, estimated_bytes, per_template_bytes_cap)
        results.append(
            TemplateDryRun(
                template_id=template_id,
                estimated_bytes=estimated_bytes,
            )
        )
    total_estimated_bytes = sum(result.estimated_bytes for result in results)
    if total_estimated_bytes > total_bytes_cap:
        raise TemplateValidationError(
            f"Template aggregate estimate exceeds the 30 GiB cap: {total_estimated_bytes} bytes"
        )
    return TemplatePreflight(
        templates=tuple(results),
        total_estimated_bytes=total_estimated_bytes,
    )


def _server_latency_ms(job: Any) -> float | None:
    started = getattr(job, "started", None)
    ended = getattr(job, "ended", None)
    if started is None or ended is None:
        return None
    return (ended - started).total_seconds() * 1000


def _execute_template(
    client: Any,
    template: Mapping[str, Any],
    *,
    estimated_bytes: int,
    location: str,
    per_template_bytes_cap: int,
    clock_ns: Callable[[], int],
) -> TemplateExecutionResult:
    template_id = template["id"]
    start_ns = clock_ns()
    job = client.query(
        render_template(template),
        job_config=_query_config(
            dry_run=False,
            maximum_bytes_billed=per_template_bytes_cap,
        ),
        location=location,
    )
    row_iterator = job.result()
    rows = list(row_iterator)
    end_ns = clock_ns()
    schema = getattr(row_iterator, "schema", None)
    if schema is None:
        raise TemplateValidationError(f"{template_id} result does not expose a schema")
    columns = tuple(field.name for field in schema)
    expected_columns = tuple(template["expected_columns"])
    if columns != expected_columns:
        raise TemplateValidationError(
            f"{template_id} returned columns {columns}; expected {expected_columns}"
        )
    if template["validation"]["expect_non_empty"] and not rows:
        raise TemplateValidationError(f"{template_id} requires a non-empty result")
    return TemplateExecutionResult(
        template_id=template_id,
        row_count=len(rows),
        columns=columns,
        estimated_bytes=estimated_bytes,
        processed_bytes=int(getattr(job, "total_bytes_processed", 0) or 0),
        billed_bytes=int(getattr(job, "total_bytes_billed", 0) or 0),
        wall_latency_ms=(end_ns - start_ns) / 1_000_000,
        server_latency_ms=_server_latency_ms(job),
        slot_millis=int(getattr(job, "slot_millis", 0) or 0),
        cache_hit=bool(getattr(job, "cache_hit", False)),
    )


def execute_templates(
    client: Any,
    *,
    templates: list[dict[str, Any]] | None = None,
    location: str = DEFAULT_LOCATION,
    per_template_bytes_cap: int = PER_TEMPLATE_BYTES_CAP,
    total_bytes_cap: int = TOTAL_TEMPLATE_BYTES_CAP,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> TemplateExecutionReport:
    """Preflight the library, then re-check and execute each rendered template once."""
    values = load_templates() if templates is None else templates
    preflight = dry_run_templates(
        client,
        templates=values,
        location=location,
        per_template_bytes_cap=per_template_bytes_cap,
        total_bytes_cap=total_bytes_cap,
    )
    results: list[TemplateExecutionResult] = []
    for template in values:
        estimated_bytes = _dry_run_template(
            client,
            template,
            location=location,
            per_template_bytes_cap=per_template_bytes_cap,
        )
        _validate_budget(template["id"], estimated_bytes, per_template_bytes_cap)
        results.append(
            _execute_template(
                client,
                template,
                estimated_bytes=estimated_bytes,
                location=location,
                per_template_bytes_cap=per_template_bytes_cap,
                clock_ns=clock_ns,
            )
        )
    return TemplateExecutionReport(preflight=preflight, results=tuple(results))
