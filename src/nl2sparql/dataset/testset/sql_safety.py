"""Pure GoogleSQL parsing and relation allowlist validation."""

from __future__ import annotations

from sqlglot import Dialect, exp, parse
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.scope import traverse_scope
from sqlglot.tokens import TokenType

from nl2sparql.dataset.testset.contracts import TestSetError

MANAGED_RELATIONS = frozenset(
    {
        "nl2sparql-thesis.nl2sparql_analytics.block_facts",
        "nl2sparql-thesis.nl2sparql_analytics.contract_dimension",
        "nl2sparql-thesis.nl2sparql_analytics.entity_labels_v1",
        "nl2sparql-thesis.nl2sparql_analytics.labeled_token_transfers",
        "nl2sparql-thesis.nl2sparql_analytics.labeled_transactions",
        "nl2sparql-thesis.nl2sparql_analytics.token_dimension",
        "nl2sparql-thesis.nl2sparql_analytics.token_transfer_facts",
        "nl2sparql-thesis.nl2sparql_analytics.transaction_facts",
    }
)


def _relation_name(table: exp.Table) -> str:
    """Return a normalized relation name for tables and table-valued functions."""
    parts = [table.catalog, table.db]
    if isinstance(table.this, exp.Anonymous):
        parts.append(table.this.name)
    else:
        parts.append(table.name)
    return ".".join(part for part in parts if part).casefold()


def _is_cte_reference(table: exp.Table, cte_names: frozenset[str]) -> bool:
    return (
        isinstance(table.this, exp.Identifier)
        and not table.catalog
        and not table.db
        and table.name.casefold() in cte_names
    )


def _has_projected_wildcard(expression: exp.Expression) -> bool:
    for select in expression.find_all(exp.Select):
        for projection in select.expressions:
            unaliased = projection.this if isinstance(projection, exp.Alias) else projection
            if isinstance(unaliased, exp.Star) or (
                isinstance(unaliased, exp.Column) and isinstance(unaliased.this, exp.Star)
            ):
                return True
    return False


def validate_sql_text(sql: str) -> None:
    """Validate one read-only GoogleSQL query against the analytical allowlist.

    The BigQuery tokenizer distinguishes comments from markers inside literals, and
    SQLGlot's BigQuery AST exposes every direct table/table-function reference.
    CTE aliases are resolved per lexical scope and are not mistaken for relations.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise TestSetError("SQL must not be empty")
    try:
        tokenizer = Dialect.get_or_raise("bigquery").tokenizer_class()
        tokens = tokenizer.tokenize(sql)
        if any(token.comments for token in tokens):
            raise TestSetError("SQL must be one statement without comments")
        if any(token.token_type is TokenType.SEMICOLON for token in tokens):
            raise TestSetError("SQL must be one statement without semicolons")
        expressions = parse(sql, read="bigquery")
    except SqlglotError as exc:
        raise TestSetError(f"invalid GoogleSQL: {exc}") from exc
    if len(expressions) != 1 or expressions[0] is None:
        raise TestSetError("SQL must contain exactly one statement")
    expression = expressions[0]
    if not isinstance(expression, exp.Query):
        raise TestSetError("SQL must be a read-only query")
    if _has_projected_wildcard(expression):
        raise TestSetError("SQL must project explicit columns")

    relation_count = 0
    for scope in traverse_scope(expression):
        cte_names = frozenset(name.casefold() for name in scope.cte_sources)
        for table in scope.tables:
            if _is_cte_reference(table, cte_names):
                continue
            relation_count += 1
            relation = _relation_name(table)
            if relation not in MANAGED_RELATIONS:
                raise TestSetError(f"SQL must use managed analytical objects, got {relation!r}")
    if relation_count == 0:
        raise TestSetError("SQL must use at least one managed analytical object")
