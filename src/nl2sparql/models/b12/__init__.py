"""Public interface for the B1/B2 GoogleSQL baselines."""

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

__all__ = [
    "MODEL_ID",
    "CatalogSummary",
    "ChatMessage",
    "Completion",
    "GenerationConfig",
    "SelectedExample",
    "SmallLLMError",
    "SmallLLMPrediction",
    "compile_catalog_summary",
    "validate_question",
]
