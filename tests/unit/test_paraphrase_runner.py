"""Tests for the resumable, cost-bounded paraphrase runner."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from nl2sparql.dataset.paraphrase.contracts import build_preserved_facts, load_entity_index
from nl2sparql.dataset.paraphrase.runner import (
    CompletionAPIError,
    CompletionResult,
    ParaphraseRunError,
    load_checkpoint,
    run_stage_b,
    run_stage_c,
)

STAGE_A_PATH = Path("data/dataset/raw/synthetic-stage-a.jsonl")


def source_records(count: int = 3) -> list[dict[str, object]]:
    return [json.loads(line) for line in STAGE_A_PATH.read_text().splitlines()[:count]]


class FakeClient:
    def __init__(
        self,
        *,
        fail_first: bool = False,
        missing_cost: bool = False,
        cost_usd: float = 0.0,
    ) -> None:
        self.fail_first = fail_first
        self.missing_cost = missing_cost
        self.cost_usd = cost_usd
        self.calls: dict[str, int] = {}

    async def complete(self, request) -> CompletionResult:
        count = self.calls.get(request.source_id, 0) + 1
        self.calls[request.source_id] = count
        if self.fail_first and count == 1:
            raise CompletionAPIError("rate limited", retryable=True)
        facts = json.loads(
            next(
                line.split("Required preserved facts:\n", 1)[1].split("\n\n", 1)[0]
                for line in [request.user_prompt]
            )
        )
        if request.stage == "stage_b":
            content = json.dumps(
                {
                    "question": request.user_prompt.split("NL seed:\n", 1)[1].split("\n\n", 1)[0],
                    "preserved_facts": facts,
                }
            )
        else:
            formal = request.user_prompt.split("Formal question:\n", 1)[1].split("\n\n", 1)[0]
            content = json.dumps(
                {
                    "casual": formal,
                    "abbreviated": formal.replace("How many", "Count"),
                    "alternative": formal.replace("happened", "occurred"),
                    "preserved_facts": facts,
                }
            )
        return CompletionResult(
            content=content,
            generation_id=f"gen-{request.source_id}",
            model=request.model,
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
            cost_usd=None if self.missing_cost else self.cost_usd,
            latency_ms=10.0,
        )


def test_stage_b_stable_order_checkpoint_and_resume(tmp_path: Path) -> None:
    records = source_records()
    checkpoint = tmp_path / "stage-b.checkpoint.jsonl"
    client = FakeClient()

    report = asyncio.run(
        run_stage_b(records, client, checkpoint, load_entity_index(), concurrency=2)
    )

    assert [record["id"] for record in report.records] == [record["id"] for record in records]
    assert all(record["nl_formal"] == record["nl_seed"] for record in report.records)
    assert report.total_cost_usd == 0.0
    assert len(load_checkpoint(checkpoint)) == 3

    resumed = FakeClient()
    second = asyncio.run(
        run_stage_b(records, resumed, checkpoint, load_entity_index(), concurrency=2)
    )
    assert second.records == report.records
    assert second.total_cost_usd == 0.0
    assert second.resumed_records == 3
    assert resumed.calls == {}


def test_retryable_failure_retries_but_schema_failure_does_not(tmp_path: Path) -> None:
    sleeps: list[float] = []

    async def sleeper(delay: float) -> None:
        sleeps.append(delay)

    client = FakeClient(fail_first=True)
    report = asyncio.run(
        run_stage_b(
            source_records(1),
            client,
            tmp_path / "retry.jsonl",
            load_entity_index(),
            sleeper=sleeper,
        )
    )
    assert len(report.records) == 1
    assert list(client.calls.values()) == [2]
    assert sleeps == [1.0]

    class InvalidClient(FakeClient):
        async def complete(self, request) -> CompletionResult:
            result = await super().complete(request)
            return CompletionResult(**{**result.__dict__, "content": "{}"})

    invalid = InvalidClient()
    with pytest.raises(ParaphraseRunError, match="response"):
        asyncio.run(
            run_stage_b(
                source_records(1),
                invalid,
                tmp_path / "invalid.jsonl",
                load_entity_index(),
            )
        )
    assert list(invalid.calls.values()) == [1]


def test_global_request_pacing_spaces_concurrent_api_starts(tmp_path: Path) -> None:
    now = 0.0
    starts: list[float] = []

    def clock() -> float:
        return now

    async def pacing_sleeper(delay: float) -> None:
        nonlocal now
        now += delay

    class TimestampClient(FakeClient):
        async def complete(self, request) -> CompletionResult:
            starts.append(clock())
            return await super().complete(request)

    asyncio.run(
        run_stage_b(
            source_records(3),
            TimestampClient(),
            tmp_path / "paced.jsonl",
            load_entity_index(),
            concurrency=3,
            requests_per_minute=4,
            pacing_clock=clock,
            pacing_sleeper=pacing_sleeper,
        )
    )

    assert starts == [0.0, 15.0, 30.0]


def test_fatal_failure_drains_in_flight_completion_before_resume(tmp_path: Path) -> None:
    records = source_records(3)
    checkpoint = tmp_path / "drain.jsonl"

    class OneFatalClient(FakeClient):
        def __init__(self) -> None:
            super().__init__()
            self.started = 0
            self.both_started = asyncio.Event()

        async def complete(self, request) -> CompletionResult:
            self.started += 1
            if self.started == 2:
                self.both_started.set()
            await self.both_started.wait()
            if request.source_id == records[0]["id"]:
                raise CompletionAPIError("daily quota", retryable=False)
            await asyncio.sleep(0.01)
            return await super().complete(request)

    with pytest.raises(ParaphraseRunError, match="daily quota"):
        asyncio.run(
            run_stage_b(
                records,
                OneFatalClient(),
                checkpoint,
                load_entity_index(),
                concurrency=2,
            )
        )

    accepted_before_resume = load_checkpoint(checkpoint)
    assert len(accepted_before_resume) == 1

    resumed = FakeClient()
    report = asyncio.run(
        run_stage_b(records, resumed, checkpoint, load_entity_index(), concurrency=1)
    )

    accepted_id = next(iter(accepted_before_resume.values()))["output"]["id"]
    assert accepted_id not in resumed.calls
    assert len(resumed.calls) == 2
    assert report.resumed_records == 1


def test_missing_cost_and_hard_cost_cap_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ParaphraseRunError, match="cost metadata"):
        asyncio.run(
            run_stage_b(
                source_records(1),
                FakeClient(missing_cost=True),
                tmp_path / "missing.jsonl",
                load_entity_index(),
            )
        )
    with pytest.raises(ParaphraseRunError, match="cost cap"):
        asyncio.run(
            run_stage_b(
                source_records(1),
                FakeClient(cost_usd=0.001),
                tmp_path / "cap.jsonl",
                load_entity_index(),
                cost_cap_usd=0.0001,
            )
        )


def test_zero_cost_cap_accepts_free_tier_completion(tmp_path: Path) -> None:
    class FreeTierClient(FakeClient):
        async def complete(self, request) -> CompletionResult:
            result = await super().complete(request)
            return CompletionResult(**{**result.__dict__, "cost_usd": 0.0})

    report = asyncio.run(
        run_stage_b(
            source_records(1),
            FreeTierClient(),
            tmp_path / "free-tier.jsonl",
            load_entity_index(),
            cost_cap_usd=0.0,
        )
    )

    assert report.total_cost_usd == 0.0
    assert report.completed_calls == 1


def test_checkpoint_conflict_is_rejected(tmp_path: Path) -> None:
    checkpoint = tmp_path / "conflict.jsonl"
    checkpoint.write_text('{"key":"same","output":1}\n{"key":"same","output":2}\n')
    with pytest.raises(ParaphraseRunError, match="conflicting checkpoint"):
        load_checkpoint(checkpoint)


def test_stage_c_validates_facts_and_returns_parent_rows(tmp_path: Path) -> None:
    sources = source_records(1)
    stage_b = [
        {
            **sources[0],
            "nl_formal": sources[0]["nl_seed"],
            "stage_b": {"preserved_facts": build_preserved_facts(sources[0])},
        }
    ]
    report = asyncio.run(
        run_stage_c(
            stage_b,
            FakeClient(),
            tmp_path / "stage-c.jsonl",
            load_entity_index(),
        )
    )
    assert len(report.records) == 1
    assert set(report.records[0]["stage_c"]["responses"]) == {
        "casual",
        "abbreviated",
        "alternative",
    }
