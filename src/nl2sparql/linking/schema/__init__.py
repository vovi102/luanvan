"""Plan B analytical schema linking primitives."""

from nl2sparql.linking.schema.contracts import (
    DEFAULT_MODEL_ID,
    DOCUMENT_VERSION,
    INDEX_SCHEMA_VERSION,
    Encoder,
    SchemaCachePaths,
    SchemaDocumentError,
    SchemaElement,
    SchemaIndexError,
    SchemaLinkerError,
    ScoreWeights,
)
from nl2sparql.linking.schema.documents import build_schema_elements, load_synonyms
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
    "Encoder",
    "SchemaCachePaths",
    "SchemaDocumentError",
    "SchemaElement",
    "SchemaIndex",
    "SchemaIndexError",
    "SchemaIndexMetadata",
    "SchemaLinker",
    "SchemaLinkerError",
    "SchemaMatch",
    "ScoreWeights",
    "build_schema_elements",
    "build_index",
    "load_index",
    "load_synonyms",
]
