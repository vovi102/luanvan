"""GoogleSQL-native entity linking primitives."""

from nl2sparql.linking.entity.contracts import (
    DEFAULT_MODEL_ID,
    DOCUMENT_VERSION,
    INDEX_SCHEMA_VERSION,
    Encoder,
    EntityAlternative,
    EntityCachePaths,
    EntityCorpus,
    EntityDocumentError,
    EntityEncoderUnavailableError,
    EntityIndexError,
    EntityLinkerError,
    EntityMatch,
    EntityTarget,
)
from nl2sparql.linking.entity.documents import build_entity_corpus, normalize_phrase
from nl2sparql.linking.entity.evaluate import (
    EntityEvaluationError,
    EntityEvaluationReport,
    GroundTruthCase,
    GroundTruthMention,
    evaluate_linker,
    load_ground_truth,
)
from nl2sparql.linking.entity.index import EntityIndex, EntityIndexMetadata, build_index, load_index
from nl2sparql.linking.entity.linker import EntityLinker

__all__ = [
    "DEFAULT_MODEL_ID",
    "DOCUMENT_VERSION",
    "INDEX_SCHEMA_VERSION",
    "Encoder",
    "EntityAlternative",
    "EntityCachePaths",
    "EntityCorpus",
    "EntityDocumentError",
    "EntityEncoderUnavailableError",
    "EntityEvaluationError",
    "EntityEvaluationReport",
    "EntityIndexError",
    "EntityIndex",
    "EntityIndexMetadata",
    "EntityLinker",
    "EntityLinkerError",
    "EntityMatch",
    "EntityTarget",
    "GroundTruthCase",
    "GroundTruthMention",
    "build_entity_corpus",
    "build_index",
    "evaluate_linker",
    "load_index",
    "load_ground_truth",
    "normalize_phrase",
]
