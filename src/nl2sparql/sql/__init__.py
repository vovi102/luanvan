"""GoogleSQL analytical schema contracts for Plan B."""

from nl2sparql.sql.label_layer import (
    LABEL_TABLE_SCHEMA,
    LabelLayerError,
    LabelSnapshot,
    SqlObject,
    build_label_snapshot,
    render_label_layer_ddl,
    render_rollback_ddl,
)
from nl2sparql.sql.schema import (
    CATALOG_PATH,
    CatalogSummary,
    LiveField,
    LiveSchemaSummary,
    SchemaCatalogError,
    load_catalog,
    normalize_live_schema,
    validate_catalog,
    validate_date_window,
    validate_live_schemas,
)

__all__ = [
    "CATALOG_PATH",
    "LABEL_TABLE_SCHEMA",
    "CatalogSummary",
    "LabelLayerError",
    "LabelSnapshot",
    "LiveField",
    "LiveSchemaSummary",
    "SchemaCatalogError",
    "SqlObject",
    "build_label_snapshot",
    "load_catalog",
    "normalize_live_schema",
    "render_label_layer_ddl",
    "render_rollback_ddl",
    "validate_catalog",
    "validate_date_window",
    "validate_live_schemas",
]
