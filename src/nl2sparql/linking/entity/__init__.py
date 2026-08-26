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
from nl2sparql.linking.entity.index import EntityIndex, EntityIndexMetadata, build_index, load_index

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
    "EntityIndexError",
    "EntityIndex",
    "EntityIndexMetadata",
    "EntityLinkerError",
    "EntityMatch",
    "EntityTarget",
    "build_entity_corpus",
    "build_index",
    "load_index",
    "normalize_phrase",
]
