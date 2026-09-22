"""
Server-Sent Events (SSE) streaming endpoint for /generate-and-run.

Streams progress updates phase-by-phase to the frontend, reducing
perceived latency from 3-6s to ~500ms (time-to-first-byte).

Phases emitted:
  1. schema  - Schema introspection/pruning complete
  2. llm     - LLM SQL generation complete (includes sql + explanation)
  3. execution - Query execution complete (includes data)
  4. complete - Full QueryResponse payload
"""

import json
import asyncio
from typing import AsyncGenerator
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.api.schemas import NaturalLanguageQueryRequest
from app.api.routes_database import get_current_db_url
from app.engine.llm_client import LLMClient
from app.engine.introspector import DatabaseIntrospector
from app.engine.prompt_builder import build_sql_generation_prompt
from app.engine.query_runner import QueryRunner

router = APIRouter(prefix="/query", tags=["Query Streaming"])


def _sse_event(data: dict, event: str = "message") -> str:
    """Format a dict as an SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def _stream_generate_and_run(req: NaturalLanguageQueryRequest) -> AsyncGenerator[str, None]:
    """
    Generator that yields SSE events for each phase of the text-to-SQL pipeline.
    """
    target_url = get_current_db_url(req.db_url)

    llm_client = LLMClient(
        api_key=req.api_key,
        provider=req.provider or "gemini",
        model_name=req.model_name
    )

    introspector = DatabaseIntrospector(target_url)
    query_runner = QueryRunner(target_url)

    clean_prompt = (req.prompt or "").strip()[:4000]
    prune_schema = req.prune_schema if req.prune_schema is not None else True

    # ── Phase 1: Schema ─────────────────────────────────────────────
    yield _sse_event({"phase": "schema", "status": "started"})

    try:
        if prune_schema:
            schema_md, pruning_meta = await asyncio.to_thread(
                introspector.get_pruned_markdown_schema,
                clean_prompt, req.previous_prompt, req.glossary_terms, req.max_tables
            )
        else:
            schema_md = await asyncio.to_thread(introspector.get_markdown_schema_for_llm)
            structured = await asyncio.to_thread(introspector.get_structured_schema, False)
            table_names = [t["name"] for t in structured.get("tables", [])]
            pruning_meta = {
                "is_pruned": False,
                "total_tables": len(table_names),
                "retained_tables": table_names,
                "pruned_tables": [],
                "estimated_tokens_saved": 0
            }

        yield _sse_event({
            "phase": "schema",
            "status": "done",
            "pruning": pruning_meta
        })
    except Exception as e:
        yield _sse_event({"phase": "schema", "status": "error", "error": str(e)})
        return

    dialect = introspector.dialect_name

    # ── Phase 2: LLM Generation ─────────────────────────────────────
    yield _sse_event({"phase": "llm", "status": "started"})

    prompt = build_sql_generation_prompt(
        user_query=clean_prompt,
        schema_markdown=schema_md,
        dialect=dialect,
        previous_sql=req.previous_sql,
        previous_prompt=req.previous_prompt,
        glossary_terms=req.glossary_terms,
        few_shot_examples=req.few_shot_examples
    )

    try:
        ai_output = await llm_client.generate_sql_async(
            prompt,
            user_query=req.prompt,
            previous_sql=req.previous_sql,
            glossary_terms=req.glossary_terms,
            few_shot_examples=req.few_shot_examples
        )
    except Exception as e:
        yield _sse_event({"phase": "llm", "status": "error", "error": str(e)})
        return

    generated_sql = (ai_output.get("sql") or "").strip()

    yield _sse_event({
        "phase": "llm",
        "status": "done",
        "sql": generated_sql,
        "explanation": ai_output.get("explanation", ""),
        "suggested_chart": ai_output.get("suggested_chart", "table")
    })

    # If no SQL generated (greeting/conversational), emit complete
    if not generated_sql:
        yield _sse_event({
            "phase": "complete",
            "result": {
                "success": True,
                "prompt": req.prompt,
                "sql": None,
                "explanation": ai_output.get("explanation", ""),
                "suggested_chart": "table",
                "chart_config": {},
                "data": {"columns": [], "rows": [], "row_count": 0, "execution_time_ms": 0},
                "self_healed": False,
                "attempts": [],
                "schema_pruning": pruning_meta
            }
        })
        return

    # ── Phase 3: Execution ──────────────────────────────────────────
    yield _sse_event({"phase": "execution", "status": "started"})

    try:
        exec_res = await asyncio.to_thread(query_runner.execute_query, generated_sql)
    except Exception as e:
        yield _sse_event({"phase": "execution", "status": "error", "error": str(e)})
        return

    yield _sse_event({
        "phase": "execution",
        "status": "done",
        "success": exec_res.get("success", False),
        "row_count": exec_res.get("row_count", 0),
        "execution_time_ms": exec_res.get("execution_time_ms", 0)
    })

    # ── Phase 4: Complete ───────────────────────────────────────────
    follow_ups = ai_output.get("follow_up_suggestions") or [
        {"label": "Only top 3", "prompt": "Only show the top 3"},
        {"label": "Sort lowest first", "prompt": "Sort ascending (lowest first)"},
        {"label": "Include all columns", "prompt": "Show all columns for these records"},
    ]

    result = {
        "success": exec_res.get("success", False),
        "prompt": req.prompt,
        "sql": exec_res.get("sanitized_sql", generated_sql),
        "explanation": ai_output.get("explanation", "Query executed successfully."),
        "breakdown": ai_output.get("breakdown"),
        "suggested_chart": ai_output.get("suggested_chart", "table"),
        "chart_config": ai_output.get("chart_config", {}),
        "follow_up_suggestions": follow_ups,
        "data": {
            "columns": exec_res.get("columns", []),
            "rows": exec_res.get("rows", []),
            "row_count": exec_res.get("row_count", 0),
            "execution_time_ms": exec_res.get("execution_time_ms", 0)
        },
        "self_healed": False,
        "attempts": [{"attempt": 1, "sql": generated_sql, "success": exec_res.get("success", False), "error": exec_res.get("error")}],
        "schema_pruning": pruning_meta
    }

    if not exec_res.get("success"):
        result["error"] = exec_res.get("error", "Query execution failed.")

    yield _sse_event({"phase": "complete", "result": result})


@router.post("/generate-and-run-stream")
async def generate_and_run_stream(req: NaturalLanguageQueryRequest):
    """
    SSE streaming version of /generate-and-run.
    Streams phase-by-phase progress events for lower perceived latency.
    """
    return StreamingResponse(
        _stream_generate_and_run(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
