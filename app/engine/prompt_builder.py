import json
from typing import Dict, Any, Optional

DIALECT_TIPS = {
    "sqlite": """
- Dialect: SQLite
- Use SQLite-compatible functions:
  - String concatenation: `||`
  - Current timestamp: `CURRENT_TIMESTAMP` or `datetime('now')`
  - Date formatting: `strftime('%Y-%m', order_date)` or `strftime('%Y', order_date)`
  - Rounding: `ROUND(value, 2)`
  - Handling divisions: cast as float if dividing integers: `CAST(a AS FLOAT) / b`
""",
    "postgresql": """
- Dialect: PostgreSQL
- Use PostgreSQL-compatible functions:
  - Date truncation: `DATE_TRUNC('month', order_date)`
  - Current timestamp: `NOW()`
  - String concatenation: `||` or `CONCAT()`
  - Limit & Offset: `LIMIT n OFFSET m`
""",
    "mysql": """
- Dialect: MySQL
- Use MySQL-compatible functions:
  - Date formatting: `DATE_FORMAT(order_date, '%Y-%m')`
  - Current timestamp: `NOW()`
  - String concatenation: `CONCAT(a, b)`
"""
}

SYSTEM_INSTRUCTION = """You are an expert Data Engineer and SQL Architect.
Your task is to convert a user's natural language question into a high-performance, accurate, and secure SQL query based solely on the provided database schema.

CRITICAL RULES:
1. ONLY produce valid SELECT queries (or WITH ... SELECT CTEs).
2. NEVER write DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, or schema-modifying statements.
3. Join tables using exact foreign key relationships identified in the schema.
4. Filter values using exact case or sample values provided in the schema where appropriate.
5. Provide a clear, concise plain English explanation of what the query calculates and how it answers the user's question.
6. Suggest the most appropriate data visualization ('bar', 'line', 'pie', or 'table'):
   - 'bar': For comparisons across categories (e.g. sales by product category, top customers)
   - 'line': For time-series trends (e.g. revenue by month, signups over time)
   - 'pie': For proportion of a whole when categories are few (<= 6)
   - 'table': For raw lists, multi-column reports, or non-aggregated records.
7. Return your response ONLY as valid JSON matching this schema:
{
  "sql": "SELECT ...",
  "explanation": "Plain English summary of the query logic and how it answers the prompt.",
  "breakdown": {
    "tables_used": ["table1", "table2"],
    "joins": ["table1.id = table2.foreign_id"],
    "filters": ["status = 'completed'"],
    "aggregations": ["SUM(amount) grouped by category"],
    "assumptions": ["Assumed completed orders represent realized revenue"]
  },
  "suggested_chart": "bar|line|pie|table",
  "chart_config": {
    "x_axis": "column_name_for_labels",
    "y_axis": "column_name_for_values",
    "title": "Descriptive Chart Title"
  },
  "follow_up_suggestions": [
    { "label": "Short label (e.g. Top 3 only)", "prompt": "Complete natural refinement prompt (e.g. Filter to only the top 3)" },
    { "label": "Short label (e.g. Sort descending)", "prompt": "Complete natural refinement prompt (e.g. Sort by total revenue descending)" },
    { "label": "Short label (e.g. Include status)", "prompt": "Complete natural refinement prompt (e.g. Include the order status column as well)" }
  ]
}
8. GREETINGS & NON-DATABASE PROMPTS:
If the user's input is a greeting (e.g. "hello", "hi", "hey", "how are you"), a conversational remark, or unrelated to querying the schema, set "sql" to empty string "", set "breakdown" to null, and in "explanation" provide a friendly response explaining what database tables exist and inviting them to ask a question (e.g. "Hello! I can help you analyze your database. Ask me a question about your customers, orders, or products.").
Do not include markdown code fence formatting around the JSON (such as ```json ... ```) unless specifically required, but ensure raw JSON parsing succeeds.
"""

def build_sql_generation_prompt(
    user_query: str,
    schema_markdown: str,
    dialect: str = "sqlite",
    previous_error: Optional[str] = None,
    previous_failed_sql: Optional[str] = None,
    previous_sql: Optional[str] = None,
    previous_prompt: Optional[str] = None,
    glossary_terms: Optional[list] = None,
    few_shot_examples: Optional[list] = None
) -> str:
    dialect_guidance = DIALECT_TIPS.get(dialect.lower(), f"- Dialect: {dialect}\n- Ensure valid {dialect} syntax.")
    
    prompt_parts = [
        f"### Target Database Schema:\n{schema_markdown}",
        f"\n### Dialect Specific Rules:\n{dialect_guidance}",
    ]

    # Domain Glossary & Semantic Business Rules (Plan 1.4 / A.4)
    if glossary_terms and len(glossary_terms) > 0:
        glossary_lines = [
            "\n### Domain Glossary & Business Logic Rules:",
            "Use the following authoritative domain definitions whenever the user prompt mentions these terms or concepts:"
        ]
        for item in glossary_terms:
            if isinstance(item, dict):
                term = item.get("term", "").strip()
                defn = item.get("definition", "").strip()
                cat = item.get("category")
            else:
                term = getattr(item, "term", "").strip()
                defn = getattr(item, "definition", "").strip()
                cat = getattr(item, "category", None)
            if term and defn:
                cat_tag = f" [{cat}]" if cat else ""
                glossary_lines.append(f"- \"{term}\"{cat_tag}: {defn}")
        if len(glossary_lines) > 2:
            prompt_parts.append("\n".join(glossary_lines))

    # Few-Shot Reference Examples (Plan 1.4 / A.4)
    if few_shot_examples and len(few_shot_examples) > 0:
        few_shot_lines = [
            "\n### Reference Example Queries (Few-Shot):",
            "Refer to these golden examples of user questions and approved SQL queries for this database:"
        ]
        for idx, ex in enumerate(few_shot_examples, 1):
            if isinstance(ex, dict):
                ex_prompt = ex.get("prompt", "").strip()
                ex_sql = ex.get("sql", "").strip()
                ex_expl = ex.get("explanation")
            else:
                ex_prompt = getattr(ex, "prompt", "").strip()
                ex_sql = getattr(ex, "sql", "").strip()
                ex_expl = getattr(ex, "explanation", None)
            if ex_prompt and ex_sql:
                expl_str = f" -- {ex_expl}" if ex_expl else ""
                few_shot_lines.append(f"Example {idx}:")
                few_shot_lines.append(f"Q: \"{ex_prompt}\"{expl_str}")
                few_shot_lines.append(f"SQL:\n```sql\n{ex_sql}\n```\n")
        if len(few_shot_lines) > 2:
            prompt_parts.append("\n".join(few_shot_lines))

    # Conversational follow-up context (Phase 2.1)
    if previous_sql:
        refinement_context = ["\n### Conversational Context & Prior Query:"]
        if previous_prompt:
            refinement_context.append(f"Previous User Request: \"{previous_prompt}\"")
        refinement_context.append(f"Previous Generated SQL:\n```sql\n{previous_sql}\n```")
        refinement_context.append(
            "The current question is a conversational follow-up or refinement to the query above. "
            "Update, adjust, filter, sort, or modify the previous SQL query according to the new request, "
            "while maintaining relevant joins, filters, and projections unless the user asks to change or replace them."
        )
        prompt_parts.append("\n".join(refinement_context))

    prompt_parts.append(f"\n### Current User Request:\n\"{user_query}\"")

    if previous_error and previous_failed_sql:
        prompt_parts.append(
            f"\n### PREVIOUS ATTEMPT FAILED:\n"
            f"The previous SQL query failed during execution:\n"
            f"```sql\n{previous_failed_sql}\n```\n"
            f"Database returned the following error:\n"
            f"\"{previous_error}\"\n"
            f"Please diagnose the error with reference to the schema and correct the SQL query."
        )

    prompt_parts.append("\nGenerate the JSON response containing the SQL query, explanation, and visualization recommendation:")
    return "\n".join(prompt_parts)

