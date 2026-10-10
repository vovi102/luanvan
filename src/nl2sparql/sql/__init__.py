"""GoogleSQL contracts with provider modules loaded only on demand."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORT_MODULES = {
    "BENCHMARK_CASES": "benchmark",
    "TOTAL_BENCHMARK_BYTES_CAP": "benchmark",
    "BenchmarkCase": "benchmark",
    "BenchmarkDryRun": "benchmark",
    "BenchmarkError": "benchmark",
    "BenchmarkPreflight": "benchmark",
    "BenchmarkReport": "benchmark",
    "BenchmarkResult": "benchmark",
    "dry_run_benchmark": "benchmark",
    "execute_benchmark": "benchmark",
    "validate_benchmark_cases": "benchmark",
    "DEFAULT_DATASET": "label_layer",
    "DEFAULT_LOCATION": "constants",
    "DEFAULT_MAXIMUM_BYTES_BILLED": "label_layer",
    "LABEL_TABLE_SCHEMA": "label_layer",
    "DeploymentPlan": "label_layer",
    "DeploymentResult": "label_layer",
    "LabelLayerError": "label_layer",
    "LabelSnapshot": "label_layer",
    "SqlObject": "label_layer",
    "apply_deployment": "label_layer",
    "apply_rollback": "label_layer",
    "build_deployment_plan": "label_layer",
    "build_label_snapshot": "label_layer",
    "render_label_layer_ddl": "label_layer",
    "render_rollback_ddl": "label_layer",
    "CATALOG_PATH": "schema",
    "CatalogSummary": "schema",
    "LiveField": "schema",
    "LiveSchemaSummary": "schema",
    "SchemaCatalogError": "schema",
    "load_catalog": "schema",
    "normalize_live_schema": "schema",
    "validate_catalog": "schema",
    "validate_date_window": "schema",
    "validate_live_schemas": "schema",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(f"nl2sparql.sql.{module_name}"), name)
    globals()[name] = value
    return value
