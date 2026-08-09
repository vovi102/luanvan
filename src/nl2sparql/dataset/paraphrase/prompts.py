"""Pinned SQL-to-English prompt builders for T3.3."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from nl2sparql.dataset.paraphrase.contracts import (
    STAGE_B_MODEL,
    STAGE_C_MODEL,
    StageBResponse,
    StageCResponse,
    build_preserved_facts,
    validate_preserved_facts,
)

STAGE_B_SYSTEM = """You are a precise GoogleSQL-to-English translator.
Write one natural, formal English question answered by the supplied query.
Preserve every limit, threshold, date, duration, token, and entity identity.
Use a supplied entity owner name instead of its address when possible.
Do not output SQL, Markdown, explanations, or facts not present in the input.
Return only the required strict JSON object."""

STAGE_C_SYSTEM = """You are a meaning-preserving English paraphraser.
Return casual, abbreviated, and alternative phrasings of the formal question.
Preserve every supplied fact exactly. Make the three phrasings substantially
different in wording and structure. Do not rewrite or output SQL. Do not output
Markdown or explanations. Return only the required strict JSON object."""


@dataclass(frozen=True)
class PromptRequest:
    stage: str
    source_id: str
    source_hash: str
    model: str
    temperature: float
    system_prompt: str
    user_prompt: str
    response_schema: dict[str, Any]
    prompt_sha256: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _entity_context(
    record: dict[str, Any], entity_index: dict[str, dict[str, str]]
) -> list[dict[str, str]]:
    context: list[dict[str, str]] = []
    for entity in record.get("entities_used", []):
        value = str(entity["value"])
        item = {"slot": entity["slot"], "type": entity["type"], "value": value}
        known = entity_index.get(value.lower())
        if known:
            item.update(known)
        context.append(item)
    return context


def _request(
    *,
    stage: str,
    source_id: str,
    source_hash: str,
    model: str,
    temperature: float,
    system_prompt: str,
    user_prompt: str,
    response_schema: dict[str, Any],
) -> PromptRequest:
    prompt_sha256 = hashlib.sha256(
        _canonical_json(
            {
                "stage": stage,
                "model": model,
                "temperature": temperature,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "response_schema": response_schema,
            }
        ).encode()
    ).hexdigest()
    return PromptRequest(
        stage=stage,
        source_id=source_id,
        source_hash=source_hash,
        model=model,
        temperature=temperature,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        response_schema=response_schema,
        prompt_sha256=prompt_sha256,
    )


def build_stage_b_request(
    record: dict[str, Any], entity_index: dict[str, dict[str, str]]
) -> PromptRequest:
    facts = build_preserved_facts(record)
    user_prompt = "\n\n".join(
        (
            f"GoogleSQL:\n{record['sql']}",
            f"NL seed:\n{record['nl_seed']}",
            f"Required preserved facts:\n{json.dumps(facts, ensure_ascii=False)}",
            "Entity context:\n"
            + json.dumps(_entity_context(record, entity_index), ensure_ascii=False),
            "Write the formal English question and repeat the preserved facts exactly.",
        )
    )
    return _request(
        stage="stage_b",
        source_id=record["id"],
        source_hash=record["record_sha256"],
        model=STAGE_B_MODEL,
        temperature=0.0,
        system_prompt=STAGE_B_SYSTEM,
        user_prompt=user_prompt,
        response_schema=StageBResponse.model_json_schema(),
    )


def build_stage_c_request(
    record: dict[str, Any], entity_index: dict[str, dict[str, str]]
) -> PromptRequest:
    facts = record.get("stage_b", {}).get("preserved_facts")
    validate_preserved_facts(facts, record)
    user_prompt = "\n\n".join(
        (
            f"Formal question:\n{record['nl_formal']}",
            f"Required preserved facts:\n{json.dumps(facts, ensure_ascii=False)}",
            "Entity context:\n"
            + json.dumps(_entity_context(record, entity_index), ensure_ascii=False),
            "Write all three paraphrases and repeat the preserved facts exactly.",
        )
    )
    return _request(
        stage="stage_c",
        source_id=record["id"],
        source_hash=record["record_sha256"],
        model=STAGE_C_MODEL,
        temperature=0.7,
        system_prompt=STAGE_C_SYSTEM,
        user_prompt=user_prompt,
        response_schema=StageCResponse.model_json_schema(),
    )
