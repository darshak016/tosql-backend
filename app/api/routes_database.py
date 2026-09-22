import os
import asyncio
from fastapi import APIRouter, HTTPException
from app.api.schemas import ConnectRequest, DatabaseSchemaResponse, DictionaryConfig

from app.engine.introspector import DatabaseIntrospector
from app.engine.llm_client import LLMClient
from app.core.config import settings
from app.core.schema_cache import schema_cache
from app.core.connection_pool import dispose_engine

router = APIRouter(prefix="/database", tags=["Database"])

# In-memory current connection state initialized from DATABASE_URL if configured
current_db = {
    "url": settings.DATABASE_URL or os.environ.get("DATABASE_URL") or None
}

def get_current_db_url(override_url: str = None) -> str:
    if override_url and override_url.strip():
        return override_url.strip()
    if current_db["url"]:
        return current_db["url"]
    raise HTTPException(
        status_code=400,
        detail="No database connected. Please configure DATABASE_URL in your environment or connect via the database modal."
    )

@router.post("/connect")
async def connect_database(req: ConnectRequest):
    try:
        if req.db_url and req.db_url.strip():
            db_url = req.db_url.strip()
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
        elif settings.DATABASE_URL or os.environ.get("DATABASE_URL"):
            db_url = settings.DATABASE_URL or os.environ.get("DATABASE_URL")
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
        else:
            raise ValueError("No database URL provided and DATABASE_URL is not set in environment.")

        # Test introspection
        introspector = DatabaseIntrospector(db_url)

        # Invalidate caches for this URL on reconnection
        schema_cache.invalidate(db_url)

        schema = await asyncio.to_thread(introspector.get_structured_schema, True)
        
        # Update current active URL
        current_db["url"] = db_url

        return {
            "success": True,
            "message": f"Successfully connected to {schema['database_type']} database.",
            "database_type": schema["database_type"],
            "table_count": schema["table_count"],
            "tables": schema["tables"],
            "active_db_url": db_url
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to connect to database: {str(e)}")

@router.get("/schema", response_model=DatabaseSchemaResponse)
async def get_schema(db_url: str = None):
    target_url = get_current_db_url(db_url)
    try:
        introspector = DatabaseIntrospector(target_url)
        schema = await asyncio.to_thread(introspector.get_structured_schema, True)
        return {
            "database_type": schema["database_type"],
            "table_count": schema["table_count"],
            "tables": schema["tables"],
            "active_db_url": target_url
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to inspect schema: {str(e)}")

@router.get("/table-preview/{table_name}")
async def get_table_preview(table_name: str, db_url: str = None, limit: int = 5):
    target_url = get_current_db_url(db_url)
    try:
        introspector = DatabaseIntrospector(target_url)
        preview = await asyncio.to_thread(introspector.get_table_preview, table_name, limit)
        return preview
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to preview table {table_name}: {str(e)}")

def generate_dynamic_samples_for_schema(schema: dict) -> list:
    """
    Intelligently generates natural-language starter query suggestions
    directly tailored to the tables, columns, and foreign keys of the active database.
    """
    tables = schema.get("tables", [])
    if not tables:
        return []

    samples = []
    
    # 1. Multi-table join suggestion if foreign keys exist
    join_candidate = None
    for tbl in tables:
        fks = tbl.get("foreign_keys", [])
        if fks:
            fk = fks[0]
            ref_tbl = fk.get("referred_table")
            if ref_tbl:
                join_candidate = (tbl["name"], ref_tbl)
                break
    
    if join_candidate:
        child_tbl, parent_tbl = join_candidate
        samples.append({
            "title": f"{child_tbl.capitalize()} with {parent_tbl.capitalize()}",
            "prompt": f"List the top 10 {child_tbl} along with their associated {parent_tbl} details",
            "tag": "Relationship Join"
        })

    # 2. Aggregation / Top records on table with numeric or amount column
    for tbl in tables:
        num_cols = [
            c["name"] for c in tbl.get("columns", [])
            if any(t in c["type"].lower() for t in ["int", "float", "numeric", "decimal", "double", "real"])
            and not c.get("is_primary_key") and not c["name"].endswith("_id")
        ]
        cat_cols = [
            c["name"] for c in tbl.get("columns", [])
            if any(t in c["type"].lower() for t in ["char", "text", "str", "varchar"])
            and not c["name"].endswith("_id")
        ]
        
        if num_cols and cat_cols:
            n_col = num_cols[0]
            c_col = cat_cols[0]
            samples.append({
                "title": f"Top {tbl['name'].capitalize()} by {n_col.replace('_', ' ').capitalize()}",
                "prompt": f"Show total and average {n_col.replace('_', ' ')} grouped by {c_col.replace('_', ' ')} in {tbl['name']}",
                "tag": "Aggregation"
            })
            break

    # 3. Categorical distribution / Group By query
    for tbl in tables:
        cat_cols = [
            c["name"] for c in tbl.get("columns", [])
            if any(t in c["type"].lower() for t in ["char", "text", "varchar"])
            and not c.get("is_primary_key") and not c["name"].endswith("_id")
        ]
        if cat_cols:
            c_col = cat_cols[0]
            samples.append({
                "title": f"{tbl['name'].capitalize()} Breakdown by {c_col.capitalize()}",
                "prompt": f"What is the distribution and count of {tbl['name']} broken down by {c_col.replace('_', ' ')}?",
                "tag": "Grouping & Count"
            })
            break

    # 4. Recent / Date-based or Latest records if timestamp/date exists
    for tbl in tables:
        date_cols = [
            c["name"] for c in tbl.get("columns", [])
            if any(t in c["type"].lower() for t in ["date", "time"])
        ]
        if date_cols:
            d_col = date_cols[0]
            samples.append({
                "title": f"Latest {tbl['name'].capitalize()}",
                "prompt": f"Show the most recent 10 records from {tbl['name']} ordered by {d_col} descending",
                "tag": "Time Filter"
            })
            break

    # 5. Fallback general query on largest or first table
    if len(samples) < 3 and tables:
        first_tbl = tables[0]["name"]
        samples.append({
            "title": f"Explore {first_tbl.capitalize()}",
            "prompt": f"Show the first 10 records from {first_tbl}",
            "tag": "Exploration"
        })

    return samples[:6]

# In-memory cache for dynamic LLM/schema suggestions per DB URL
_suggestions_cache = {}

@router.get("/sample-queries")
async def get_sample_queries(
    db_url: str = None, 
    api_key: str = None, 
    provider: str = "gemini", 
    model_name: str = None
):
    try:
        target_url = get_current_db_url(db_url)
    except HTTPException:
        return {"samples": []}
    
    # Check cache first for target database
    if target_url in _suggestions_cache:
        return {"samples": _suggestions_cache[target_url]}

    try:
        introspector = DatabaseIntrospector(target_url)
        schema = await asyncio.to_thread(introspector.get_structured_schema, False)
        schema_markdown = introspector.format_schema_as_markdown(schema)

        # 1. Attempt LLM-based suggestion generation
        llm = LLMClient(api_key=api_key, provider=provider, model_name=model_name)
        llm_samples = await asyncio.to_thread(llm.generate_suggestions, schema_markdown)

        if llm_samples and isinstance(llm_samples, list) and len(llm_samples) > 0:
            _suggestions_cache[target_url] = llm_samples
            return {"samples": llm_samples}

        # 2. Heuristic fallback if LLM has no key or fails
        fallback_samples = generate_dynamic_samples_for_schema(schema)
        _suggestions_cache[target_url] = fallback_samples
        return {"samples": fallback_samples}
    except Exception as e:
        print(f"[!] Error generating sample queries: {e}")
        return {"samples": []}

# Default bundled glossary terms and few-shot examples for sample ecommerce DB
_sample_dictionary = {
    "terms": [
        {
            "term": "active customer",
            "definition": "c.id IN (SELECT DISTINCT customer_id FROM orders WHERE order_date >= date('now', '-90 days'))",
            "category": "Customer Status"
        },
        {
            "term": "high value order",
            "definition": "o.total_amount >= 150.00 AND o.status = 'completed'",
            "category": "Revenue"
        },
        {
            "term": "low stock",
            "definition": "p.stock_quantity < 50",
            "category": "Inventory"
        },
        {
            "term": "realized revenue",
            "definition": "SUM(o.total_amount) WHERE o.status = 'completed'",
            "category": "Accounting"
        }
    ],
    "few_shots": [
        {
            "prompt": "Show top 5 customers by spend",
            "sql": "SELECT c.name, ROUND(SUM(o.total_amount), 2) AS total_spent FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.status = 'completed' GROUP BY c.id, c.name ORDER BY total_spent DESC LIMIT 5",
            "explanation": "Calculates completed order spending per customer and orders descending with a limit of 5."
        },
        {
            "prompt": "Monthly sales trend",
            "sql": "SELECT strftime('%Y-%m', order_date) AS month, ROUND(SUM(total_amount), 2) AS monthly_revenue, COUNT(id) AS order_count FROM orders WHERE status = 'completed' GROUP BY strftime('%Y-%m', order_date) ORDER BY month ASC",
            "explanation": "Aggregates revenue and volume per month for completed orders formatted YYYY-MM."
        }
    ]
}

@router.get("/dictionary", response_model=DictionaryConfig)
async def get_dictionary():
    """
    Returns the active dictionary containing domain glossary definitions and few-shot reference examples.
    """
    return _sample_dictionary

@router.post("/dictionary", response_model=DictionaryConfig)
async def update_dictionary(config: DictionaryConfig):
    """
    Updates the active domain glossary definitions and few-shot examples.
    """
    _sample_dictionary["terms"] = [t.model_dump() for t in config.terms]
    _sample_dictionary["few_shots"] = [f.model_dump() for f in config.few_shots]
    return _sample_dictionary

