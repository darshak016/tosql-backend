import os
from fastapi import APIRouter, HTTPException
from app.api.schemas import ConnectRequest, DatabaseSchemaResponse
from app.engine.introspector import DatabaseIntrospector
from app.samples.seed_samples import seed_ecommerce_db
from app.core.config import settings

router = APIRouter(prefix="/database", tags=["Database"])

# In-memory current connection state
current_db = {
    "url": f"sqlite:///{settings.DEFAULT_DB_PATH.replace(os.sep, '/')}"
}

def get_current_db_url(override_url: str = None) -> str:
    if override_url and override_url.strip():
        return override_url.strip()
    return current_db["url"]

@router.post("/connect")
def connect_database(req: ConnectRequest):
    try:
        if req.db_url and req.db_url.strip():
            db_url = req.db_url.strip()
            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
        else:
            # Ensure sample db exists
            if not os.path.exists(settings.DEFAULT_DB_PATH):
                seed_ecommerce_db(settings.DEFAULT_DB_PATH)
            db_url = f"sqlite:///{settings.DEFAULT_DB_PATH.replace(os.sep, '/')}"

        # Test introspection
        introspector = DatabaseIntrospector(db_url)
        schema = introspector.get_structured_schema(include_samples=True)
        
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
def get_schema(db_url: str = None):
    target_url = get_current_db_url(db_url)
    try:
        introspector = DatabaseIntrospector(target_url)
        schema = introspector.get_structured_schema(include_samples=True)
        return {
            "database_type": schema["database_type"],
            "table_count": schema["table_count"],
            "tables": schema["tables"],
            "active_db_url": target_url
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to inspect schema: {str(e)}")

@router.get("/table-preview/{table_name}")
def get_table_preview(table_name: str, db_url: str = None, limit: int = 5):
    target_url = get_current_db_url(db_url)
    try:
        introspector = DatabaseIntrospector(target_url)
        preview = introspector.get_table_preview(table_name, limit=limit)
        return preview
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to preview table {table_name}: {str(e)}")

@router.get("/sample-queries")
def get_sample_queries():
    return {
        "samples": [
            {
                "title": "Top Customers by Spend",
                "prompt": "Show top 5 customers who spent the most on completed orders",
                "tag": "Aggregation & Join"
            },
            {
                "title": "Monthly Sales Trend",
                "prompt": "Show monthly total sales revenue and order count over time",
                "tag": "Time-Series"
            },
            {
                "title": "Department Payroll & Budget",
                "prompt": "List each department with their annual budget and total employee salary payroll",
                "tag": "Human Resources"
            },
            {
                "title": "Marketing Campaign ROI",
                "prompt": "Which marketing campaigns generated the highest revenue compared to their spend?",
                "tag": "Marketing Analytics"
            },
            {
                "title": "Product Ratings by Category",
                "prompt": "What is the average product review rating and review count by category?",
                "tag": "Reviews & Sentiment"
            },
            {
                "title": "Critical Low Stock Products",
                "prompt": "Which products have less than 50 units in stock?",
                "tag": "Inventory"
            },
            {
                "title": "Revenue by Product Category",
                "prompt": "What is the total revenue and units sold per product category?",
                "tag": "Multi-Table Join"
            },
            {
                "title": "Carrier Shipment Volume",
                "prompt": "How many shipments were handled by each carrier and their delivery status?",
                "tag": "Logistics"
            }
        ]
    }
