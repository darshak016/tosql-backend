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
