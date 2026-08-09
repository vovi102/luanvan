"""Resumable, asynchronous, actual-cost-bounded paraphrase runner."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from nl2sparql.dataset.paraphrase.contracts import (
    ParaphraseValidationError,
    StageBResponse,
    StageCResponse,
    validate_preserved_facts,
)
from nl2sparql.dataset.paraphrase.prompts import (
    PromptRequest,
    build_stage_b_request,
    build_stage_c_request,
)
from nl2sparql.dataset.paraphrase.quality import (
    validate_question_anchors,
    validate_stage_c_questions,
)

DEFAULT_COST_CAP_USD = 30.0
RESERVATION_PER_REQUEST_USD = 0.02


class ParaphraseRunError(ValueError):
    """Raised when a paraphrase run cannot safely continue."""


class CompletionAPIError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class CompletionResult:
    content: str
    generation_id: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float | None
    latency_ms: float


class CompletionClient(Protocol):
    async def complete(self, request: PromptRequest) -> CompletionResult: ...


@dataclass(frozen=True)
class StageRunReport:
    stage: str
    records: tuple[dict[str, Any], ...]
    total_cost_usd: float
    completed_calls: int
    resumed_records: int


class CostLedger:
    def __init__(self, cap_usd: float, *, initial_spent_usd: float = 0.0) -> None:
        if cap_usd <= 0:
            raise ParaphraseRunError("cost cap must be positive")
        if initial_spent_usd < 0 or initial_spent_usd > cap_usd:
            raise ParaphraseRunError(f"checkpoint cost exceeds API cost cap ${cap_usd:.2f}")
        self.cap_usd = cap_usd
        self.spent_usd = initial_spent_usd
        self.reserved_usd = 0.0
        self._lock = asyncio.Lock()

    async def reserve(self) -> None:
        async with self._lock:
            if self.spent_usd + self.reserved_usd + RESERVATION_PER_REQUEST_USD > self.cap_usd:
                raise ParaphraseRunError(f"API cost cap ${self.cap_usd:.2f} would be exceeded")
            self.reserved_usd += RESERVATION_PER_REQUEST_USD

    async def settle(self, cost_usd: float | None) -> None:
        async with self._lock:
            self.reserved_usd -= RESERVATION_PER_REQUEST_USD
            if cost_usd is None:
                raise ParaphraseRunError("OpenRouter response is missing usage.cost")
            if cost_usd < 0 or self.spent_usd + cost_usd > self.cap_usd:
                raise ParaphraseRunError(f"API cost cap ${self.cap_usd:.2f} exceeded")
            self.spent_usd += cost_usd


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _checkpoint_key(request: PromptRequest) -> str:
    return hashlib.sha256(
        _canonical_json(
            {
                "stage": request.stage,
                "source_hash": request.source_hash,
                "prompt_sha256": request.prompt_sha256,
                "model": request.model,
            }
        ).encode()
    ).hexdigest()


def load_checkpoint(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    values: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            row = json.loads(line)
            key = row["key"]
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ParaphraseRunError(f"Invalid checkpoint row at line {line_number}") from exc
        if key in values and values[key] != row:
            raise ParaphraseRunError(f"conflicting checkpoint rows for key {key}")
        values[key] = row
    return values


def _append_checkpoint(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(row) + "\n")


async def _complete_with_retry(
    client: CompletionClient,
    request: PromptRequest,
    *,
    sleeper: Callable[[float], Awaitable[None]],
) -> tuple[CompletionResult, int]:
    for attempt in range(1, 4):
        try:
            return await client.complete(request), attempt
        except CompletionAPIError as exc:
            if not exc.retryable or attempt == 3:
                raise ParaphraseRunError(
                    f"completion failed after {attempt} attempt(s): {exc}"
                ) from exc
            await sleeper(float(2 ** (attempt - 1)))
    raise AssertionError("unreachable")


def _completion_metadata(
    result: CompletionResult, request: PromptRequest, attempts: int
) -> dict[str, Any]:
    return {
        **asdict(result),
        "prompt_sha256": request.prompt_sha256,
        "preserved_facts": None,
        "attempts": attempts,
    }


async def _run_stage(
    *,
    stage: str,
    records: Sequence[dict[str, Any]],
    client: CompletionClient,
    checkpoint_path: Path,
    entity_index: dict[str, dict[str, str]],
    concurrency: int,
    cost_cap_usd: float,
    sleeper: Callable[[float], Awaitable[None]],
) -> StageRunReport:
    if concurrency <= 0:
        raise ParaphraseRunError("concurrency must be positive")
    checkpoint = load_checkpoint(checkpoint_path)
    checkpoint_cost = 0.0
    matched_keys: set[str] = set()
    for record in records:
        request = (
            build_stage_b_request(record, entity_index)
            if stage == "stage_b"
            else build_stage_c_request(record, entity_index)
        )
        key = _checkpoint_key(request)
        existing = checkpoint.get(key)
        if existing is None or key in matched_keys:
            continue
        matched_keys.add(key)
        try:
            value = existing["output"][stage]["cost_usd"]
            checkpoint_cost += float(value)
        except (KeyError, TypeError, ValueError) as exc:
            raise ParaphraseRunError(
                f"checkpoint row {key} is missing valid {stage} cost metadata"
            ) from exc
    ledger = CostLedger(cost_cap_usd, initial_spent_usd=checkpoint_cost)
    semaphore = asyncio.Semaphore(concurrency)
    checkpoint_lock = asyncio.Lock()
    resumed = 0
    completed_calls = 0

    async def process(record: dict[str, Any]) -> dict[str, Any]:
        nonlocal resumed, completed_calls
        request = (
            build_stage_b_request(record, entity_index)
            if stage == "stage_b"
            else build_stage_c_request(record, entity_index)
        )
        key = _checkpoint_key(request)
        existing = checkpoint.get(key)
        if existing is not None:
            resumed += 1
            return existing["output"]
        async with semaphore:
            await ledger.reserve()
            result, attempts = await _complete_with_retry(client, request, sleeper=sleeper)
            await ledger.settle(result.cost_usd)
            try:
                if stage == "stage_b":
                    response = StageBResponse.model_validate_json(result.content)
                    validate_preserved_facts(response.preserved_facts, record)
                    validate_question_anchors(response.question, record, entity_index)
                    metadata = _completion_metadata(result, request, attempts)
                    metadata["preserved_facts"] = response.preserved_facts
                    output = {
                        **record,
                        "nl_formal": response.question,
                        "stage_b": metadata,
                    }
                else:
                    response = StageCResponse.model_validate_json(result.content)
                    validate_preserved_facts(response.preserved_facts, record)
                    distances = validate_stage_c_questions(response, record, entity_index)
                    metadata = _completion_metadata(result, request, attempts)
                    metadata.update(
                        preserved_facts=response.preserved_facts,
                        responses={
                            "casual": response.casual,
                            "abbreviated": response.abbreviated,
                            "alternative": response.alternative,
                        },
                        pairwise_distances=list(distances),
                    )
                    output = {**record, "stage_c": metadata}
            except (ValidationError, ParaphraseValidationError) as exc:
                raise ParaphraseRunError(
                    f"invalid {stage} response for {record['id']}: {exc}"
                ) from exc
            row = {"key": key, "output": output}
            async with checkpoint_lock:
                _append_checkpoint(checkpoint_path, row)
                checkpoint[key] = row
            completed_calls += 1
            return output

    outputs = await asyncio.gather(*(process(record) for record in records))
    return StageRunReport(
        stage=stage,
        records=tuple(outputs),
        total_cost_usd=ledger.spent_usd,
        completed_calls=completed_calls,
        resumed_records=resumed,
    )


async def run_stage_b(
    records: Sequence[dict[str, Any]],
    client: CompletionClient,
    checkpoint_path: Path,
    entity_index: dict[str, dict[str, str]],
    *,
    concurrency: int = 10,
    cost_cap_usd: float = DEFAULT_COST_CAP_USD,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> StageRunReport:
    return await _run_stage(
        stage="stage_b",
        records=records,
        client=client,
        checkpoint_path=checkpoint_path,
        entity_index=entity_index,
        concurrency=concurrency,
        cost_cap_usd=cost_cap_usd,
        sleeper=sleeper,
    )


async def run_stage_c(
    records: Sequence[dict[str, Any]],
    client: CompletionClient,
    checkpoint_path: Path,
    entity_index: dict[str, dict[str, str]],
    *,
    concurrency: int = 10,
    cost_cap_usd: float = DEFAULT_COST_CAP_USD,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> StageRunReport:
    return await _run_stage(
        stage="stage_c",
        records=records,
        client=client,
        checkpoint_path=checkpoint_path,
        entity_index=entity_index,
        concurrency=concurrency,
        cost_cap_usd=cost_cap_usd,
        sleeper=sleeper,
    )
