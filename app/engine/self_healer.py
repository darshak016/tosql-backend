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
        max_self_heal_retries: int = 2
    ) -> Dict[str, Any]:
        """
        Orchestrates:
        1. Introspection & schema markdown context
        2. Prompt generation
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
                "attempts": []
            }

        # Guard against excessively long prompt overflow (cap at 4,000 chars)
        capped_prompt = clean_prompt[:4000]

        schema_md = self.get_schema_markdown()
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
                previous_failed_sql=last_failed_sql
            )

            # Generate via LLM
            ai_output = self.llm_client.generate_sql(prompt, user_query=user_prompt)
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
                    "attempts": []
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
                return {
                    "success": True,
                    "prompt": user_prompt,
                    "sql": exec_res.get("sanitized_sql", generated_sql),
                    "explanation": ai_output.get("explanation", "Query executed successfully."),
                    "suggested_chart": ai_output.get("suggested_chart", "table"),
                    "chart_config": ai_output.get("chart_config", {}),
                    "data": {
                        "columns": exec_res.get("columns", []),
                        "rows": exec_res.get("rows", []),
                        "row_count": exec_res.get("row_count", 0),
                        "execution_time_ms": exec_res.get("execution_time_ms", 0)
                    },
                    "self_healed": attempt > 0,
                    "attempts": attempts_log
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
            "suggested_chart": "table",
            "chart_config": {},
            "data": {"columns": [], "rows": [], "row_count": 0, "execution_time_ms": 0},
            "self_healed": False,
            "attempts": attempts_log
        }
