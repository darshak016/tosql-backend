import os
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from app.core.connection_pool import get_engine
from app.core.schema_cache import (
    schema_cache,
    CACHE_STRUCTURED_SAMPLES,
    CACHE_STRUCTURED_NO_SAMPLES,
    CACHE_MARKDOWN,
)

class DatabaseIntrospector:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine: Engine = get_engine(db_url)
        self.dialect_name = self.engine.dialect.name

    def get_structured_schema(self, include_samples: bool = True) -> Dict[str, Any]:
        """
        Inspects the database and returns a structured dictionary of tables, columns,
        foreign keys, and distinct sample values.
        Results are cached with a 5-minute TTL to avoid repeated expensive introspection.
        """
        # Check cache first
        cache_suffix = CACHE_STRUCTURED_SAMPLES if include_samples else CACHE_STRUCTURED_NO_SAMPLES
        cached = schema_cache.get(self.db_url, suffix=cache_suffix)
        if cached is not None:
            return cached

        inspector = inspect(self.engine)
        if self.dialect_name == "postgresql":
            table_names = inspector.get_table_names(schema="public")
        else:
            table_names = inspector.get_table_names()
        
        schema = {
            "database_type": self.dialect_name,
            "table_count": len(table_names),
            "tables": []
        }

        # For PostgreSQL, use pg_stat_user_tables for fast approximate row counts
        pg_row_counts: Dict[str, int] = {}
        if self.dialect_name == "postgresql":
            try:
                with self.engine.connect() as conn:
                    stat_res = conn.execute(text(
                        "SELECT relname, n_live_tup FROM pg_stat_user_tables WHERE schemaname = 'public'"
                    ))
                    for row in stat_res.fetchall():
                        pg_row_counts[row[0]] = int(row[1])
            except Exception:
                pass

        with self.engine.connect() as conn:
            for table_name in table_names:
                columns_meta = inspector.get_columns(table_name)
                fks = inspector.get_foreign_keys(table_name)
                pk_constraint = inspector.get_pk_constraint(table_name)
                pk_cols = pk_constraint.get("constrained_columns", []) if pk_constraint else []

                # Count rows: use pg_stat for PostgreSQL, COUNT(*) otherwise
                row_count = 0
                sample_rows_by_col = {}
                if table_name in pg_row_counts:
                    row_count = pg_row_counts[table_name]
                else:
                    try:
                        count_res = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
                        row_count = count_res or 0
                    except Exception:
                        pass

                if include_samples and row_count > 0:
                    try:
                        # Single query for up to 5 sample rows across all columns
                        sample_res = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT 5'))
                        sample_keys = list(sample_res.keys())
                        sample_data = sample_res.fetchall()
                        for col_idx, col_k in enumerate(sample_keys):
                            distinct_vals = []
                            for row in sample_data:
                                val = row[col_idx]
                                if val is not None:
                                    s_val = str(val)
                                    if s_val not in distinct_vals:
                                        distinct_vals.append(s_val)
                            sample_rows_by_col[col_k] = distinct_vals[:4]
                    except Exception:
                        pass

                columns = []
                for col in columns_meta:
                    col_name = col["name"]
                    col_type = str(col["type"])
                    is_pk = col_name in pk_cols
                    sample_values = sample_rows_by_col.get(col_name, [])

                    columns.append({
                        "name": col_name,
                        "type": col_type,
                        "nullable": col.get("nullable", True),
                        "is_primary_key": is_pk,
                        "sample_values": sample_values
                    })

                formatted_fks = []
                for fk in fks:
                    formatted_fks.append({
                        "constrained_columns": fk.get("constrained_columns", []),
                        "referred_table": fk.get("referred_table"),
                        "referred_columns": fk.get("referred_columns", [])
                    })

                schema["tables"].append({
                    "name": table_name,
                    "row_count": row_count,
                    "columns": columns,
                    "foreign_keys": formatted_fks
                })

        # Store in cache
        schema_cache.set(self.db_url, schema, suffix=cache_suffix)
        return schema

    def format_schema_as_markdown(self, schema: Dict[str, Any]) -> str:
        """
        Formats structured schema dictionary into compact Markdown tailored for LLM prompt.
        """
        lines = [f"### Database Engine: {schema.get('database_type', self.dialect_name).upper()}"]
        lines.append(f"### Tables and Columns Definition ({len(schema.get('tables', []))} tables):\n")

        for table in schema.get("tables", []):
            lines.append(f"#### Table: `{table['name']}` (approx {table.get('row_count', 0)} rows)")
            col_lines = []
            for col in table.get("columns", []):
                pk_flag = " [PK]" if col.get("is_primary_key") else ""
                samples = col.get("sample_values", [])
                samples_str = f" (Sample values: {', '.join([repr(v) for v in samples])})" if samples else ""
                col_lines.append(f"  - `{col['name']}` ({col.get('type', 'TEXT')}){pk_flag}{samples_str}")
            lines.extend(col_lines)

            if table.get("foreign_keys"):
                fk_strs = []
                for fk in table["foreign_keys"]:
                    fk_strs.append(f"`{', '.join(fk['constrained_columns'])}` -> `{fk['referred_table']}({', '.join(fk['referred_columns'])})`")
                lines.append(f"  - Relationships: {', '.join(fk_strs)}")
            lines.append("")

        return "\n".join(lines)

    def get_markdown_schema_for_llm(self) -> str:
        """
        Converts the database schema into a compact, token-efficient Markdown specification
        tailored for LLM reasoning and schema linking. Result is cached.
        """
        cached_md = schema_cache.get(self.db_url, suffix=CACHE_MARKDOWN)
        if cached_md is not None:
            return cached_md

        schema = self.get_structured_schema(include_samples=True)
        md = self.format_schema_as_markdown(schema)
        schema_cache.set(self.db_url, md, suffix=CACHE_MARKDOWN)
        return md

    def get_pruned_markdown_schema(
        self,
        user_query: str,
        previous_prompt: Optional[str] = None,
        glossary_terms: Optional[List[Any]] = None,
        max_tables: Optional[int] = None,
        force_prune: bool = False
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Intelligently filters the schema based on query relevance and FK connectivity,
        returning token-optimized markdown and pruning metrics.
        """
        from app.engine.schema_pruner import SchemaPruner
        full_schema = self.get_structured_schema(include_samples=True)
        pruner = SchemaPruner()
        pruned_schema, metadata = pruner.prune(
            schema=full_schema,
            user_query=user_query,
            previous_prompt=previous_prompt,
            glossary_terms=glossary_terms,
            max_tables=max_tables,
            force_prune=force_prune
        )
        md = self.format_schema_as_markdown(pruned_schema)
        return md, metadata

    def get_table_preview(self, table_name: str, limit: int = 5) -> Dict[str, Any]:
        """
        Fetches a quick preview of rows for the schema sidebar.
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(f'SELECT * FROM "{table_name}" LIMIT {limit}'))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]
            return {"columns": columns, "rows": rows}
