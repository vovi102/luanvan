"""GoogleSQL entity-constraint resolution primitives."""

from nl2sparql.linking.resolver.catalog import ResolverCatalog, load_resolver_catalog
from nl2sparql.linking.resolver.contracts import (
    ClassResolverError,
    FieldCandidate,
    ResolutionPlan,
    ResolvedEntity,
)
from nl2sparql.linking.resolver.resolver import ClassResolver

__all__ = [
    "ClassResolver",
    "ClassResolverError",
    "FieldCandidate",
    "ResolvedEntity",
    "ResolutionPlan",
    "ResolverCatalog",
    "load_resolver_catalog",
]
