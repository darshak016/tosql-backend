import time
from typing import Dict, Any, Optional
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from app.core.security import validate_and_sanitize_sql
from app.core.config import settings

class QueryRunner:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine: Engine = create_engine(db_url)
        self.dialect = self.engine.dialect.name

    def execute_query(self, raw_sql: str, bypass_validation: bool = False) -> Dict[str, Any]:
        """
        Validates, sanitizes, and executes a read-only SQL query against the database.
        Returns execution metrics, column definitions, and row data.
        """
        start_time = time.perf_counter()
        
        # Security validation
        if not bypass_validation:
            is_valid, sanitized_sql, error_msg = validate_and_sanitize_sql(
                raw_sql, dialect=self.dialect, max_rows=settings.MAX_QUERY_ROWS
            )
            if not is_valid:
                return {
                    "success": False,
                    "error": f"Security / Validation Violation: {error_msg}",
                    "sql": raw_sql,
                    "execution_time_ms": 0
                }
        else:
            sanitized_sql = raw_sql

        try:
            with self.engine.connect() as conn:
                # Set statement execution timeout if supported or execute query
                result = conn.execute(text(sanitized_sql))
                columns = list(result.keys()) if result.returns_rows else []
                raw_rows = result.fetchall() if result.returns_rows else []
                
                # Normalize values for JSON serialization
                rows = []
                for row in raw_rows:
                    formatted_row = []
                    for val in row:
                        if isinstance(val, (date, datetime)):
                            formatted_row.append(val.isoformat())
                        elif isinstance(val, Decimal):
                            formatted_row.append(float(val))
                        elif isinstance(val, bytes):
                            formatted_row.append(str(val))
                        else:
                            formatted_row.append(val)
                    rows.append(formatted_row)

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            
            return {
                "success": True,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "execution_time_ms": duration_ms,
                "sanitized_sql": sanitized_sql
            }

        except Exception as db_err:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": False,
                "error": str(db_err),
                "sql": sanitized_sql,
                "execution_time_ms": duration_ms
            }

    def explain_query(self, raw_sql: str) -> Dict[str, Any]:
        """
        Validates target query for safety and generates an execution plan
        (EXPLAIN QUERY PLAN for SQLite, EXPLAIN for PostgreSQL/MySQL).
        Returns raw plan output lines and structured step dictionaries.
        """
        from app.core.security import validate_query_for_explain
        start_time = time.perf_counter()

        is_valid, sanitized_sql, error_msg = validate_query_for_explain(raw_sql, dialect=self.dialect)
        if not is_valid:
            return {
                "success": False,
                "error": f"Security / Validation Violation: {error_msg}",
                "dialect": self.dialect,
                "plan_type": "EXPLAIN",
                "raw_plan": [],
                "plan_rows": [],
                "sql": raw_sql,
                "execution_time_ms": 0.0
            }

        # Format dialect-appropriate explain statement
        plan_type = "EXPLAIN QUERY PLAN"
        if self.dialect in ("postgresql", "postgres"):
            explain_statement = f"EXPLAIN (VERBOSE, COSTS, BUFFERS FALSE) {sanitized_sql}"
            plan_type = "EXPLAIN (VERBOSE, COSTS)"
        elif self.dialect in ("mysql", "mariadb"):
            explain_statement = f"EXPLAIN {sanitized_sql}"
            plan_type = "EXPLAIN"
        else:
            # Default to SQLite
            explain_statement = f"EXPLAIN QUERY PLAN {sanitized_sql}"
            plan_type = "EXPLAIN QUERY PLAN"

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(explain_statement))
                col_keys = list(result.keys()) if result.returns_rows else []
                raw_rows = result.fetchall() if result.returns_rows else []

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            raw_plan = []
            plan_rows = []
            has_table_scan = False
            has_index_lookup = False

            if self.dialect == "sqlite":
                # SQLite columns: (id, parent, notused, detail)
                for r in raw_rows:
                    row_dict = dict(zip(col_keys, [str(v) if v is not None else "" for v in r]))
                    detail = row_dict.get("detail", "")
                    detail_lower = detail.lower()
                    if "scan" in detail_lower:
                        has_table_scan = True
                    if "search" in detail_lower or "index" in detail_lower or "covering" in detail_lower:
                        has_index_lookup = True

                    plan_rows.append(row_dict)
                    raw_plan.append(detail)
            else:
                for r in raw_rows:
                    line = str(r[0]) if r else ""
                    line_lower = line.lower()
                    if "seq scan" in line_lower or "table scan" in line_lower or "all" in line_lower:
                        has_table_scan = True
                    if "index" in line_lower:
                        has_index_lookup = True
                    raw_plan.append(line)
                    plan_rows.append(dict(zip(col_keys, [str(v) for v in r])))

            return {
                "success": True,
                "dialect": self.dialect,
                "plan_type": plan_type,
                "raw_plan": raw_plan,
                "plan_rows": plan_rows,
                "has_table_scan": has_table_scan,
                "has_index_lookup": has_index_lookup,
                "sql": sanitized_sql,
                "execution_time_ms": duration_ms,
                "error": None
            }

        except Exception as db_err:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return {
                "success": False,
                "error": str(db_err),
                "dialect": self.dialect,
                "plan_type": plan_type,
                "raw_plan": [],
                "plan_rows": [],
                "has_table_scan": False,
                "has_index_lookup": False,
                "sql": sanitized_sql,
                "execution_time_ms": duration_ms
            }

