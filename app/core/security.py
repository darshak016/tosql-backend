import sqlglot
from sqlglot import exp
from typing import Tuple, Optional

DISALLOWED_EXPRESSIONS = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Alter,
    exp.Create,
    exp.TruncateTable,
    exp.Command,
    exp.Grant,
    exp.Revoke,
    exp.Pragma,
    exp.SetProperty,
)

class SQLSecurityError(Exception):
    pass

def normalize_dialect(dialect: str) -> str:
    d = (dialect or "sqlite").lower()
    if d in ("postgresql", "psycopg2"):
        return "postgres"
    return d

def validate_and_sanitize_sql(sql: str, dialect: str = "sqlite", max_rows: int = 200) -> Tuple[bool, str, Optional[str]]:
    """
    Validates that a SQL query is strictly read-only and adds a LIMIT clause if absent.
    Returns: (is_valid, sanitized_sql, error_message)
    """
    cleaned_sql = sql.strip().rstrip(";")
    if not cleaned_sql:
        return False, "", "Empty SQL query."

    glot_dialect = normalize_dialect(dialect)

    # Parse with sqlglot
    try:
        parsed_statements = sqlglot.parse(cleaned_sql, read=glot_dialect)
    except Exception as e:
        return False, cleaned_sql, f"SQL syntax parsing error: {str(e)}"

    if not parsed_statements:
        return False, cleaned_sql, "No valid SQL statements found."

    if len(parsed_statements) > 1:
        # Multi-statement queries are dangerous - only allow if all are strictly Select
        for stmt in parsed_statements:
            if not isinstance(stmt, (exp.Select, exp.Union)):
                return False, cleaned_sql, "Multiple statements detected with non-SELECT statement. Execution denied."

    # Check each expression in AST for disallowed operations
    for stmt in parsed_statements:
        if stmt is None:
            continue
        # If the root isn't Select or Union
        if not isinstance(stmt, (exp.Select, exp.Union)):
            return False, cleaned_sql, f"Disallowed operation: Statement must be a SELECT query, but found {stmt.key.upper()}."

        # Recursively search for any dangerous AST nodes inside subqueries or CTEs
        for disallowed in DISALLOWED_EXPRESSIONS:
            if list(stmt.find_all(disallowed)):
                return False, cleaned_sql, f"Disallowed modification operation detected ({disallowed.__name__}). Only read-only queries are permitted."

    # Enforce or inject LIMIT on the primary statement if it's a SELECT
    primary_stmt = parsed_statements[0]
    if isinstance(primary_stmt, exp.Select):
        existing_limit = primary_stmt.args.get("limit")
        if existing_limit:
            try:
                limit_val = int(existing_limit.expression.this)
                if limit_val > max_rows:
                    primary_stmt.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))
            except Exception:
                pass
        else:
            primary_stmt.set("limit", exp.Limit(expression=exp.Literal.number(max_rows)))

    sanitized_sql = primary_stmt.sql(dialect=glot_dialect)
    return True, sanitized_sql, None

def strip_explain_prefix(sql: str) -> str:
    """
    Strips leading EXPLAIN / EXPLAIN QUERY PLAN / EXPLAIN ANALYZE keywords from SQL query string.
    """
    cleaned = sql.strip().lstrip(";").strip()
    # Case-insensitive removal of leading EXPLAIN forms
    import re
    cleaned = re.sub(r'^(EXPLAIN\s+(QUERY\s+PLAN\s+|ANALYZE\s+|FORMAT\s*=\s*\w+\s+|\([^\)]*\)\s+)?)+', '', cleaned, flags=re.IGNORECASE).strip()
    return cleaned

def validate_query_for_explain(sql: str, dialect: str = "sqlite") -> Tuple[bool, str, Optional[str]]:
    """
    Validates that the target query to be explained is strictly read-only and free of destructive AST operations.
    Returns: (is_valid, sanitized_target_sql, error_message)
    """
    stripped_sql = strip_explain_prefix(sql)
    if not stripped_sql:
        return False, "", "No executable SELECT statement found in explain request."
    return validate_and_sanitize_sql(stripped_sql, dialect=dialect, max_rows=1000)

