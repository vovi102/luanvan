"""Shared prompt construction for raw B1/B2 GoogleSQL baselines."""

from __future__ import annotations

import hashlib
import html
import json

from nl2sparql.dataset.testset.contracts import TestSetError
from nl2sparql.dataset.testset.sql_safety import validate_sql_text
from nl2sparql.models.b12.contracts import (
    CatalogSummary,
    ChatMessage,
    SelectedExample,
    SmallLLMError,
    validate_question,
)

_SYSTEM_TEMPLATE = """You write GoogleSQL for Ethereum analytics.

Use only the catalog below. Return exactly one read-only GoogleSQL query with
explicit projections. Do not output markdown, prose, comments, semicolons,
mutations, physical source tables, or invented schema/entity values.

{catalog}"""


def _format_example(example: SelectedExample) -> str:
    try:
        validate_sql_text(example.sql)
    except TestSetError as exc:
        raise SmallLLMError(f"few-shot example {example.record_id} has unsafe SQL: {exc}") from exc
    if "</google_sql>" in example.sql.casefold():
        raise SmallLLMError("few-shot SQL must not contain the prompt closing delimiter")
    record_id = html.escape(example.record_id, quote=True)
    question = html.escape(example.question, quote=False)
    return (
        f'<example id="{record_id}">\n'
        f"<question>{question}</question>\n"
        f"<google_sql>{example.sql}</google_sql>\n"
        "</example>"
    )


def build_messages(
    question: str,
    summary: CatalogSummary,
    *,
    examples: tuple[SelectedExample, ...] = (),
) -> tuple[ChatMessage, ...]:
    """Build the shared prompt, adding either zero or exactly five examples."""
    validate_question(question)
    if not isinstance(summary, CatalogSummary):
        raise SmallLLMError("summary must be a CatalogSummary")
    if not isinstance(examples, tuple) or any(
        not isinstance(example, SelectedExample) for example in examples
    ):
        raise SmallLLMError("examples must be an immutable tuple of SelectedExample values")
    if len(examples) not in {0, 5}:
        raise SmallLLMError("prompt requires zero or five examples")

    if examples:
        examples_text = (
            "<examples>\n"
            + "\n".join(_format_example(example) for example in examples)
            + "\n</examples>"
        )
    else:
        examples_text = "<examples>none</examples>"
    escaped_question = html.escape(question, quote=False)
    user = f"{examples_text}\n<question>{escaped_question}</question>\n<google_sql>"
    return (
        ChatMessage(role="system", content=_SYSTEM_TEMPLATE.format(catalog=summary.text.rstrip())),
        ChatMessage(role="user", content=user),
    )


def prompt_sha256(messages: tuple[ChatMessage, ...]) -> str:
    """Fingerprint the exact ordered messages sent to a backend."""
    if (
        not isinstance(messages, tuple)
        or not messages
        or any(not isinstance(message, ChatMessage) for message in messages)
    ):
        raise SmallLLMError("messages must be a non-empty immutable ChatMessage tuple")
    payload = json.dumps(
        [{"role": message.role, "content": message.content} for message in messages],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
