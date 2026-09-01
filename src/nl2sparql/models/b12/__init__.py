"""Public interface for the B1/B2 GoogleSQL baselines."""

from nl2sparql.models.b12.backend import GenerationBackend
from nl2sparql.models.b12.baseline import BaselineB1, BaselineB2
from nl2sparql.models.b12.catalog_summary import compile_catalog_summary
from nl2sparql.models.b12.contracts import (
    MODEL_ID,
    CatalogSummary,
    ChatMessage,
    Completion,
    GenerationConfig,
    SelectedExample,
    SmallLLMError,
    SmallLLMPrediction,
    validate_question,
)
from nl2sparql.models.b12.extraction import extract_google_sql
from nl2sparql.models.b12.prompts import build_messages, prompt_sha256
from nl2sparql.models.b12.retrieval import FewShotRetriever, TextEncoder

__all__ = [
    "MODEL_ID",
    "BaselineB1",
    "BaselineB2",
    "CatalogSummary",
    "ChatMessage",
    "Completion",
    "GenerationConfig",
    "GenerationBackend",
    "FewShotRetriever",
    "SelectedExample",
    "SmallLLMError",
    "SmallLLMPrediction",
    "TextEncoder",
    "compile_catalog_summary",
    "build_messages",
    "extract_google_sql",
    "prompt_sha256",
    "validate_question",
]
