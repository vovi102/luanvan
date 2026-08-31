"""GoogleSQL entity-constraint resolution primitives."""

from nl2sparql.linking.resolver.catalog import ResolverCatalog, load_resolver_catalog
from nl2sparql.linking.resolver.contracts import (
    ClassResolverError,
    FieldCandidate,
    ResolutionPlan,
    ResolvedEntity,
)

__all__ = [
    "ClassResolverError",
    "FieldCandidate",
    "ResolvedEntity",
    "ResolutionPlan",
    "ResolverCatalog",
    "load_resolver_catalog",
]
