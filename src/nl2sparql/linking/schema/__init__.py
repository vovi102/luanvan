"""Plan B analytical schema linking primitives."""

from nl2sparql.linking.schema.contracts import (
    DEFAULT_MODEL_ID,
    DOCUMENT_VERSION,
    INDEX_SCHEMA_VERSION,
    Encoder,
    SchemaCachePaths,
    SchemaDocumentError,
    SchemaElement,
    SchemaEncoderUnavailableError,
    SchemaIndexError,
    SchemaLinkerError,
    ScoreWeights,
)
from nl2sparql.linking.schema.documents import build_schema_elements, load_synonyms
from nl2sparql.linking.schema.evaluate import (
    CaseEvaluation,
    EvaluationReport,
    GroundTruthCase,
    evaluate_linker,
    load_ground_truth,
)
from nl2sparql.linking.schema.index import (
    SchemaIndex,
    SchemaIndexMetadata,
    build_index,
    load_index,
)
from nl2sparql.linking.schema.linker import LinkResult, SchemaLinker, SchemaMatch

__all__ = [
    "DEFAULT_MODEL_ID",
    "DOCUMENT_VERSION",
    "INDEX_SCHEMA_VERSION",
    "LinkResult",
    "CaseEvaluation",
    "Encoder",
    "EvaluationReport",
    "GroundTruthCase",
    "SchemaCachePaths",
    "SchemaDocumentError",
    "SchemaElement",
    "SchemaEncoderUnavailableError",
    "SchemaIndex",
    "SchemaIndexError",
    "SchemaIndexMetadata",
    "SchemaLinker",
    "SchemaLinkerError",
    "SchemaMatch",
    "ScoreWeights",
    "build_schema_elements",
    "build_index",
    "evaluate_linker",
    "load_index",
    "load_ground_truth",
    "load_synonyms",
]
