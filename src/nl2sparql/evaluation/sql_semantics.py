"""GoogleSQL exact, structural and failure-diagnostic semantics."""

from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse_one
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope

from nl2sparql.evaluation.contracts import EvaluationError


@dataclass(frozen=True)
class StructuralFacts:
    """Alias-insensitive SQL facts that retain literal values."""

    relations: tuple[str, ...]
    projections: tuple[str, ...]
    filters: tuple[str, ...]
    joins: tuple[str, ...]
    aggregations: tuple[str, ...]
    grouping: tuple[str, ...]
    windows: tuple[str, ...]
    ordering: tuple[str, ...]
    limit: str | None
    offset: str | None


@dataclass(frozen=True)
class SqlAnalysis:
    """Canonical rendering, structural signature and diagnostic facts."""

    canonical_sql: str
    structural_signature: str
    result_order: str
    facts: StructuralFacts


def _sql(node: exp.Expression) -> str:
    return node.sql(dialect="bigquery", pretty=False)


def _relation_name(table: exp.Table) -> str:
    parts = (table.catalog, table.db, table.name)
    return ".".join(part for part in parts if part)


def _direct_relations(expression: exp.Expression) -> tuple[str, ...]:
    relations: list[str] = []
    for scope in traverse_scope(expression):
        cte_names = {name.casefold() for name in scope.cte_sources}
        for table in scope.tables:
            is_cte = (
                isinstance(table.this, exp.Identifier)
                and not table.catalog
                and not table.db
                and table.name.casefold() in cte_names
            )
            if not is_cte:
                relations.append(_relation_name(table))
    return tuple(dict.fromkeys(relations))


def _normalized_aliases(expression: exp.Expression) -> exp.Expression:
    normalized = expression.copy()
    alias_map: dict[str, str] = {}
    for index, table in enumerate(normalized.find_all(exp.Table)):
        alias = table.alias
        if alias:
            replacement = f"_t{index}"
            alias_map[alias.casefold()] = replacement
            table.set("alias", exp.TableAlias(this=exp.to_identifier(replacement)))
    for column in normalized.find_all(exp.Column):
        if column.table and column.table.casefold() in alias_map:
            column.set("table", exp.to_identifier(alias_map[column.table.casefold()]))
    for index, alias in enumerate(normalized.find_all(exp.Alias)):
        alias.set("alias", exp.to_identifier(f"_c{index}"))
    return normalized


def _replace_literals(expression: exp.Expression) -> exp.Expression:
    def transform(node: exp.Expression) -> exp.Expression:
        if isinstance(node, exp.Literal):
            if node.is_string:
                return exp.Literal.string("__STRING__")
            return exp.Literal.number("0")
        if isinstance(node, exp.Boolean):
            return exp.true()
        if isinstance(node, exp.Null):
            return exp.null()
        return node

    return expression.transform(transform, copy=True)


def _without_output_alias(projection: exp.Expression) -> exp.Expression:
    return projection.this if isinstance(projection, exp.Alias) else projection


def _facts(expression: exp.Expression) -> StructuralFacts:
    alias_normalized = _normalized_aliases(expression)
    select = (
        alias_normalized
        if isinstance(alias_normalized, exp.Select)
        else alias_normalized.find(exp.Select)
    )
    projections = (
        tuple(_sql(_without_output_alias(item)) for item in select.expressions)
        if select is not None
        else ()
    )
    filters = tuple(
        _sql(node.this)
        for node_type in (exp.Where, exp.Having, exp.Qualify)
        for node in alias_normalized.find_all(node_type)
    )
    joins = tuple(_sql(node) for node in alias_normalized.find_all(exp.Join))
    aggregations = tuple(_sql(node) for node in alias_normalized.find_all(exp.AggFunc))
    groups = tuple(
        _sql(item) for group in alias_normalized.find_all(exp.Group) for item in group.expressions
    )
    windows = tuple(_sql(node) for node in alias_normalized.find_all(exp.Window))

    top_order = alias_normalized.args.get("order")
    ordering = tuple(_sql(item) for item in top_order.expressions) if top_order else ()
    top_limit = alias_normalized.args.get("limit")
    top_offset = alias_normalized.args.get("offset")
    limit = _sql(top_limit.expression) if top_limit and top_limit.expression else None
    offset = _sql(top_offset.expression) if top_offset and top_offset.expression else None
    return StructuralFacts(
        relations=_direct_relations(expression),
        projections=projections,
        filters=filters,
        joins=joins,
        aggregations=aggregations,
        grouping=groups,
        windows=windows,
        ordering=ordering,
        limit=limit,
        offset=offset,
    )


def analyze_sql(sql: str) -> SqlAnalysis:
    """Parse one read-only GoogleSQL query and derive deterministic semantics."""
    if not isinstance(sql, str) or not sql.strip():
        raise EvaluationError("GoogleSQL must be non-empty")
    try:
        expression = parse_one(sql, read="bigquery")
    except SqlglotError as exc:
        raise EvaluationError(f"invalid GoogleSQL: {exc}") from exc
    if not isinstance(expression, exp.Query):
        raise EvaluationError("GoogleSQL must be a read-only query")

    canonical = _sql(expression)
    normalized = _normalized_aliases(expression)
    signature = _sql(_replace_literals(normalized))
    result_order = "sequence" if expression.args.get("order") is not None else "multiset"
    return SqlAnalysis(
        canonical_sql=canonical,
        structural_signature=signature,
        result_order=result_order,
        facts=_facts(expression),
    )


def exact_match(predicted_sql: str, gold_sql: str) -> bool:
    """Return whether two queries have identical canonical GoogleSQL renderings."""
    return analyze_sql(predicted_sql).canonical_sql == analyze_sql(gold_sql).canonical_sql


def structural_match(predicted_sql: str, gold_sql: str) -> bool:
    """Return whether two queries share alias-normalized typed-literal structure."""
    return (
        analyze_sql(predicted_sql).structural_signature
        == analyze_sql(gold_sql).structural_signature
    )
