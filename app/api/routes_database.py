import os
from fastapi import APIRouter, HTTPException
from app.api.schemas import ConnectRequest, DatabaseSchemaResponse, DictionaryConfig

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
def get_dictionary():
    """
    Returns the active dictionary containing domain glossary definitions and few-shot reference examples.
    """
    return _sample_dictionary

@router.post("/dictionary", response_model=DictionaryConfig)
def update_dictionary(config: DictionaryConfig):
    """
    Updates the active domain glossary definitions and few-shot examples.
    """
    _sample_dictionary["terms"] = [t.model_dump() for t in config.terms]
    _sample_dictionary["few_shots"] = [f.model_dump() for f in config.few_shots]
    return _sample_dictionary

