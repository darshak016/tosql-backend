from typing import Dict, Any, List, Optional
from app.engine.introspector import DatabaseIntrospector
from app.engine.prompt_builder import build_sql_generation_prompt
from app.engine.llm_client import LLMClient
from app.engine.query_runner import QueryRunner

class TextToSQLEngine:
    def __init__(self, db_url: str, llm_client: Optional[LLMClient] = None):
        self.db_url = db_url
        self.introspector = DatabaseIntrospector(db_url)
        self.query_runner = QueryRunner(db_url)
        self.llm_client = llm_client or LLMClient()
        self._cached_schema_md: Optional[str] = None

    def get_schema_markdown(self) -> str:
        if not self._cached_schema_md:
            self._cached_schema_md = self.introspector.get_markdown_schema_for_llm()
        return self._cached_schema_md

    def process_natural_language_query(
        self,
        user_prompt: str,
        max_self_heal_retries: int = 2,
        previous_sql: Optional[str] = None,
        previous_prompt: Optional[str] = None,
        glossary_terms: Optional[list] = None,
        few_shot_examples: Optional[list] = None,
        prune_schema: bool = True,
        max_tables: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Orchestrates:
        1. Introspection & intelligent schema pruning for token optimization
        2. Prompt generation (with conversational context, glossary definitions, and few-shots)
        3. LLM SQL generation
        4. Validation & execution
        5. Autonomous self-healing reflection loop on execution error
        """
        # Sanitize and guard user prompt
        clean_prompt = (user_prompt or "").strip()
        if not clean_prompt:
            return {
                "success": True,
                "prompt": user_prompt,
                "sql": None,
                "explanation": "Please enter a question or query about your database.",
                "suggested_chart": "table",
                "chart_config": {},
                "data": {"columns": [], "rows": [], "row_count": 0, "execution_time_ms": 0},
                "self_healed": False,
                "attempts": [],
                "schema_pruning": {
                    "is_pruned": False,
                    "total_tables": 0,
                    "retained_tables": [],
                    "pruned_tables": [],
                    "estimated_tokens_saved": 0
                }
            }

        # Guard against excessively long prompt overflow (cap at 4,000 chars)
        capped_prompt = clean_prompt[:4000]

        # Fetch pruned or full schema markdown
        if prune_schema:
            schema_md, pruning_meta = self.introspector.get_pruned_markdown_schema(
                user_query=capped_prompt,
                previous_prompt=previous_prompt,
                glossary_terms=glossary_terms,
                max_tables=max_tables
            )
        else:
            schema_md = self.get_schema_markdown()
            structured = self.introspector.get_structured_schema(include_samples=False)
            table_names = [t["name"] for t in structured.get("tables", [])]
            pruning_meta = {
                "is_pruned": False,
                "total_tables": len(table_names),
                "retained_tables": table_names,
                "pruned_tables": [],
                "estimated_tokens_saved": 0
            }

        dialect = self.introspector.dialect_name

        attempts_log: List[Dict[str, Any]] = []
        last_error: Optional[str] = None
        last_failed_sql: Optional[str] = None
        current_ai_result: Optional[Dict[str, Any]] = None

        for attempt in range(max_self_heal_retries + 1):
            prompt = build_sql_generation_prompt(
                user_query=capped_prompt,
                schema_markdown=schema_md,
                dialect=dialect,
                previous_error=last_error,
                previous_failed_sql=last_failed_sql,
                previous_sql=previous_sql,
                previous_prompt=previous_prompt,
                glossary_terms=glossary_terms,
                few_shot_examples=few_shot_examples
            )

            # Generate via LLM
            ai_output = self.llm_client.generate_sql(
                prompt,
                user_query=user_prompt,
                previous_sql=previous_sql,
                glossary_terms=glossary_terms,
                few_shot_examples=few_shot_examples
            )
            current_ai_result = ai_output
            generated_sql = (ai_output.get("sql") or "").strip()


            # If user sent a greeting or conversational prompt (no SQL needed)
            if not generated_sql:
                return {
                    "success": True,
                    "prompt": user_prompt,
                    "sql": None,
                    "explanation": ai_output.get("explanation", "Please ask a question about your database to generate a SQL query."),
                    "suggested_chart": "table",
                    "chart_config": {},
                    "data": {
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "execution_time_ms": 0
                    },
                    "self_healed": False,
                    "attempts": [],
                    "schema_pruning": pruning_meta
                }

            # Execute SQL
            exec_res = self.query_runner.execute_query(generated_sql)
            
            attempts_log.append({
                "attempt": attempt + 1,
                "sql": generated_sql,
                "success": exec_res.get("success", False),
                "error": exec_res.get("error")
            })

            if exec_res.get("success"):
                # Success!
                final_sql = exec_res.get("sanitized_sql", generated_sql)
                breakdown = ai_output.get("breakdown") or self._extract_sql_breakdown(final_sql)

                # Extract follow-up suggestions from AI output with smart default fallback
                follow_ups = ai_output.get("follow_up_suggestions") or [
                    {"label": "Only top 3", "prompt": "Only show the top 3"},
                    {"label": "Sort lowest first", "prompt": "Sort ascending (lowest first)"},
                    {"label": "Include all columns", "prompt": "Show all columns for these records"},
                ]

                return {
                    "success": True,
                    "prompt": user_prompt,
                    "sql": final_sql,
                    "explanation": ai_output.get("explanation", "Query executed successfully."),
                    "breakdown": breakdown,
                    "suggested_chart": ai_output.get("suggested_chart", "table"),
                    "chart_config": ai_output.get("chart_config", {}),
                    "follow_up_suggestions": follow_ups,
                    "data": {
                        "columns": exec_res.get("columns", []),
                        "rows": exec_res.get("rows", []),
                        "row_count": exec_res.get("row_count", 0),
                        "execution_time_ms": exec_res.get("execution_time_ms", 0)
                    },
                    "self_healed": attempt > 0,
                    "attempts": attempts_log,
                    "schema_pruning": pruning_meta
                }
            else:
                # Query failed, prepare for self-healing retry
                last_error = exec_res.get("error")
                last_failed_sql = generated_sql

        # If all retries failed:
        return {
            "success": False,
            "prompt": user_prompt,
            "sql": last_failed_sql,
            "error": f"Failed after {max_self_heal_retries + 1} attempts. Last error: {last_error}",
            "explanation": current_ai_result.get("explanation") if current_ai_result else None,
            "breakdown": (current_ai_result.get("breakdown") if current_ai_result else None) or (self._extract_sql_breakdown(last_failed_sql) if last_failed_sql else None),
            "suggested_chart": "table",
            "chart_config": {},
            "data": {"columns": [], "rows": [], "row_count": 0, "execution_time_ms": 0},
            "self_healed": False,
            "attempts": attempts_log,
            "schema_pruning": pruning_meta
        }

    def _extract_sql_breakdown(self, sql: str) -> Dict[str, List[str]]:
        """
        Extracts structured breakdown components (tables, joins, filters, aggregations)
        from SQL if the LLM output didn't supply them.
        """
        import re

        tables_used = []
        # Find FROM / JOIN table names
        from_joins = re.findall(r'(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)', sql, re.IGNORECASE)
        for t in from_joins:
            tbl = t.strip()
            if tbl.upper() not in ["SELECT", "WHERE", "GROUP", "ORDER"] and tbl not in tables_used:
                tables_used.append(tbl)

        joins = []
        join_matches = re.findall(r'JOIN\s+([a-zA-Z_0-9]+(?:\s+AS\s+[a-zA-Z_0-9]+|\s+[a-zA-Z_0-9]+)?\s+ON\s+[^,\n]+)', sql, re.IGNORECASE)
        for j in join_matches:
            joins.append(j.strip())

        filters = []
        where_match = re.search(r'WHERE\s+(.*?)(?:\s+GROUP\s+BY|\s+ORDER\s+BY|\s+LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
        if where_match:
            raw_where = where_match.group(1).strip()
            # Split by AND
            parts = re.split(r'\s+AND\s+', raw_where, flags=re.IGNORECASE)
            filters = [p.strip() for p in parts if p.strip()]

        aggregations = []
        agg_matches = re.findall(r'\b(COUNT|SUM|AVG|MIN|MAX)\s*\([^)]*\)', sql, re.IGNORECASE)
        for a in agg_matches:
            if a.upper() not in [x.upper() for x in aggregations]:
                aggregations.append(a.strip())

        group_match = re.search(r'GROUP\s+BY\s+(.*?)(?:\s+HAVING|\s+ORDER\s+BY|\s+LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
        if group_match:
            aggregations.append(f"GROUP BY {group_match.group(1).strip()}")

        return {
            "tables_used": tables_used,
            "joins": joins,
            "filters": filters,
            "aggregations": aggregations,
            "assumptions": []
        }
