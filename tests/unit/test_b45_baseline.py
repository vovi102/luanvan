from __future__ import annotations

import ast
import asyncio
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from nl2sparql.models.b12 import CatalogSummary, SelectedExample
from nl2sparql.models.b45 import (
    BaselineB4,
    BaselineB5,
    LargeLLMConfig,
    LargeLLMError,
    ProviderPolicy,
)
from nl2sparql.models.b45.contracts import RemoteCompletion

SAFE_SQL = "SELECT address FROM `nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1`"


class ScriptedTransport:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[object, object, str]] = []

    async def complete(self, messages, config, *, request_id):
        self.calls.append((messages, config, request_id))
        return RemoteCompletion.synthetic(
            raw_text=self.text,
            model_id=config.model_id,
            provider_slug="scripted",
            input_tokens=12,
            output_tokens=7,
            charged_cost_usd=Decimal("0"),
            latency_ms=2.0,
        )


class ScriptedRetriever:
    training_sha256 = "c" * 64
    encoder_id = "sentence-transformers/all-MiniLM-L6-v2"
    encoder_revision = "d" * 40
    training_accepted = True

    def __init__(self, examples: tuple[SelectedExample, ...]) -> None:
        self.examples = examples
        self.calls: list[tuple[str, str | None]] = []

    def retrieve(
        self, question: str, *, target_id: str | None = None
    ) -> tuple[SelectedExample, ...]:
        self.calls.append((question, target_id))
        return self.examples


def policy() -> ProviderPolicy:
    return ProviderPolicy(
        provider_slug="deepinfra",
        prompt_price_per_million_usd=Decimal("0.50"),
        completion_price_per_million_usd=Decimal("1.00"),
    )


def summary() -> CatalogSummary:
    text = "GoogleSQL catalog\n"
    return CatalogSummary(
        text=text,
        catalog_sha256="a" * 64,
        summary_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def five_examples() -> tuple[SelectedExample, ...]:
    return tuple(
        SelectedExample(
            record_id=f"train-{index}",
            question=f"Question {index}",
            sql=SAFE_SQL,
            score=1.0 - index / 10,
        )
        for index in range(1, 6)
    )


def test_b4_returns_safe_sql_and_keeps_synthetic_marker() -> None:
    async def scenario() -> None:
        backend = ScriptedTransport(SAFE_SQL)
        baseline = BaselineB4(summary(), LargeLLMConfig(provider=policy()), backend)
        prediction = await baseline.predict_detailed("List labels", request_id="case-1")
        assert prediction.sql == SAFE_SQL
        assert prediction.baseline == "b4"
        assert baseline.config.sha256 == prediction.config_sha256
        assert baseline.evaluation_evidence.catalog_sha256 == prediction.catalog_sha256
        assert baseline.evaluation_evidence.training_sha256 is None
        assert prediction.completion.synthetic_backend is True
        assert "<examples>none</examples>" in backend.calls[0][0][1].content
        assert backend.calls[0][2] == "case-1"

    asyncio.run(scenario())


def test_b5_is_identical_except_for_exactly_five_examples() -> None:
    async def scenario() -> None:
        retriever = ScriptedRetriever(five_examples())
        backend = ScriptedTransport("Here is SQL: " + SAFE_SQL)
        baseline = BaselineB5(summary(), LargeLLMConfig(provider=policy()), backend, retriever)
        prediction = await baseline.predict_detailed(
            "List labels", request_id="case-1", target_id="case-1"
        )
        assert prediction.sql is None
        assert prediction.extraction_status == "prose"
        assert len(prediction.selected_examples) == 5
        assert baseline.evaluation_evidence.training_sha256 == retriever.training_sha256
        assert baseline.evaluation_evidence.training_accepted is True
        assert [item.record_id for item in prediction.selected_examples] == [
            "train-1",
            "train-2",
            "train-3",
            "train-4",
            "train-5",
        ]
        assert retriever.calls == [("List labels", "case-1")]

    asyncio.run(scenario())


def test_predict_returns_only_extracted_sql() -> None:
    async def scenario() -> None:
        baseline = BaselineB4(
            summary(), LargeLLMConfig(provider=policy()), ScriptedTransport("not a query")
        )
        assert await baseline.predict("List labels", request_id="case-1") is None

    asyncio.run(scenario())


@pytest.mark.parametrize("request_id", ["\x00", "\x7f"])
def test_invalid_request_id_fails_before_transport_or_retrieval(request_id: str) -> None:
    async def scenario() -> None:
        backend = ScriptedTransport(SAFE_SQL)
        retriever = ScriptedRetriever(five_examples())
        baseline = BaselineB5(summary(), LargeLLMConfig(provider=policy()), backend, retriever)
        with pytest.raises(LargeLLMError, match="request ID"):
            await baseline.predict_detailed(
                "List labels", request_id=request_id, target_id="case-1"
            )
        assert backend.calls == []
        assert retriever.calls == []

    asyncio.run(scenario())


def test_transport_exception_does_not_expose_adapter_message() -> None:
    class FailingTransport:
        async def complete(self, messages, config, *, request_id):
            raise RuntimeError("api-key=secret-value")

    async def scenario() -> None:
        baseline = BaselineB4(summary(), LargeLLMConfig(provider=policy()), FailingTransport())
        with pytest.raises(LargeLLMError, match="remote completion failed") as error:
            await baseline.predict_detailed("List labels", request_id="case-1")
        assert "secret-value" not in str(error.value)

    asyncio.run(scenario())


def test_compatibility_modules_only_export_baseline_classes_without_linking_imports() -> None:
    root = Path(__file__).parents[2] / "src" / "nl2sparql" / "models"
    b45_tree = ast.parse((root / "b45" / "__init__.py").read_text())
    imported = [
        alias.name
        for node in ast.walk(b45_tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [node.module or "" for node in ast.walk(b45_tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name.startswith("nl2sparql.linking") for name in imported)

    for filename, class_name in (
        ("b4_zero_shot.py", "BaselineB4"),
        ("b5_few_shot.py", "BaselineB5"),
    ):
        tree = ast.parse((root / filename).read_text())
        classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert classes == []
        assert functions == []
        assert any(
            isinstance(node, ast.ImportFrom)
            and node.module == "nl2sparql.models.b45.baseline"
            and any(alias.name == class_name for alias in node.names)
            for node in ast.walk(tree)
        )
