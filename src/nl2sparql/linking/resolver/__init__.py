"""GoogleSQL entity-constraint resolution primitives."""

from nl2sparql.linking.resolver.catalog import ResolverCatalog, load_resolver_catalog
from nl2sparql.linking.resolver.contracts import (
    ClassResolverError,
    FieldCandidate,
    ResolutionPlan,
    ResolvedEntity,
)
from nl2sparql.linking.resolver.evaluate import (
    ResolverEvaluationError,
    ResolverEvaluationReport,
    ResolverExpected,
    ResolverGroundTruth,
    ResolverGroundTruthCase,
    evaluate_resolver,
    load_resolver_ground_truth,
)
from nl2sparql.linking.resolver.resolver import ClassResolver

__all__ = [
    "ClassResolver",
    "ClassResolverError",
    "FieldCandidate",
    "ResolvedEntity",
    "ResolutionPlan",
    "ResolverEvaluationError",
    "ResolverEvaluationReport",
    "ResolverExpected",
    "ResolverGroundTruth",
    "ResolverGroundTruthCase",
    "ResolverCatalog",
    "load_resolver_catalog",
    "evaluate_resolver",
    "load_resolver_ground_truth",
]
