"""Schema and entity linking interfaces."""

from nl2sparql.linking.class_resolver import ClassResolver
from nl2sparql.linking.resolver import (
    ClassResolverError,
    FieldCandidate,
    ResolutionPlan,
    ResolvedEntity,
)
from nl2sparql.linking.schema_linker import LinkResult, SchemaLinker, SchemaMatch

__all__ = [
    "ClassResolver",
    "ClassResolverError",
    "FieldCandidate",
    "LinkResult",
    "ResolutionPlan",
    "ResolvedEntity",
    "SchemaLinker",
    "SchemaMatch",
]
