from fastapi import APIRouter, HTTPException
from app.api.schemas import (
    NaturalLanguageQueryRequest, 
    DirectSQLExecuteRequest, 
    QueryResponse,
    ExplainPlanRequest,
    ExplainPlanResponse
)
from app.api.routes_database import get_current_db_url
from app.engine.llm_client import LLMClient
from app.engine.self_healer import TextToSQLEngine
from app.engine.query_runner import QueryRunner

router = APIRouter(prefix="/query", tags=["Query"])


# In-memory query history for the session
query_history = []

@router.post("/generate-and-run", response_model=QueryResponse)
def generate_and_run(req: NaturalLanguageQueryRequest):
    target_url = get_current_db_url(req.db_url)
    
    llm_client = LLMClient(
        api_key=req.api_key,
        provider=req.provider or "gemini",
        model_name=req.model_name
    )

    engine = TextToSQLEngine(db_url=target_url, llm_client=llm_client)

    try:
        result = engine.process_natural_language_query(
            user_prompt=req.prompt,
            max_self_heal_retries=2,
            previous_sql=req.previous_sql,
            previous_prompt=req.previous_prompt,
            glossary_terms=req.glossary_terms,
            few_shot_examples=req.few_shot_examples,
            prune_schema=req.prune_schema if req.prune_schema is not None else True,
            max_tables=req.max_tables
        )

        
        # Save to history
        query_history.insert(0, {
            "prompt": req.prompt,
            "sql": result.get("sql"),
            "success": result.get("success"),
            "explanation": result.get("explanation"),
            "row_count": result.get("data", {}).get("row_count", 0),
            "execution_time_ms": result.get("data", {}).get("execution_time_ms", 0)
        })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text-to-SQL processing error: {str(e)}")

@router.post("/execute-sql")
def execute_sql(req: DirectSQLExecuteRequest):
    target_url = get_current_db_url(req.db_url)
    runner = QueryRunner(target_url)

    exec_res = runner.execute_query(req.sql)
    if not exec_res.get("success"):
        return {
            "success": False,
            "error": exec_res.get("error"),
            "sql": req.sql,
            "data": {"columns": [], "rows": [], "row_count": 0, "execution_time_ms": exec_res.get("execution_time_ms", 0)}
        }

    return {
        "success": True,
        "sql": exec_res.get("sanitized_sql", req.sql),
        "data": {
            "columns": exec_res.get("columns", []),
            "rows": exec_res.get("rows", []),
            "row_count": exec_res.get("row_count", 0),
            "execution_time_ms": exec_res.get("execution_time_ms", 0)
        }
    }

@router.post("/explain-sql", response_model=ExplainPlanResponse)
def explain_sql(req: ExplainPlanRequest):
    target_url = get_current_db_url(req.db_url)
    runner = QueryRunner(target_url)
    return runner.explain_query(req.sql)

@router.get("/history")
def get_history():
    return {"history": query_history[:30]}

