import os
import pytest
from app.engine.schema_pruner import SchemaPruner
from app.engine.introspector import DatabaseIntrospector
from app.engine.self_healer import TextToSQLEngine
from app.engine.llm_client import LLMClient
from sqlalchemy import create_engine, text

@pytest.fixture(scope="module")
def large_db_url():
    """Create an in-memory or temp SQLite DB with 12 distinct tables and foreign keys."""
    db_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "test_large_pruning.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path.replace(os.sep, '/')}")
    with engine.connect() as conn:
        # Core Ecommerce
        conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, full_name TEXT, email TEXT, country TEXT)"))
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, order_date TEXT, status TEXT, total_amount REAL, FOREIGN KEY(customer_id) REFERENCES customers(id))"))
        conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL, stock_quantity INTEGER)"))
        conn.execute(text("CREATE TABLE order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, price REAL, FOREIGN KEY(order_id) REFERENCES orders(id), FOREIGN KEY(product_id) REFERENCES products(id))"))
        
        # Supporting & Unrelated Tables
        conn.execute(text("CREATE TABLE warehouses (id INTEGER PRIMARY KEY, location_name TEXT, capacity INTEGER)"))
        conn.execute(text("CREATE TABLE suppliers (id INTEGER PRIMARY KEY, company_name TEXT, contact_phone TEXT)"))
        conn.execute(text("CREATE TABLE shipping_rates (id INTEGER PRIMARY KEY, zone_code TEXT, base_cost REAL)"))
        conn.execute(text("CREATE TABLE tax_jurisdictions (id INTEGER PRIMARY KEY, region_code TEXT, tax_rate REAL)"))
        conn.execute(text("CREATE TABLE marketing_campaigns (id INTEGER PRIMARY KEY, campaign_title TEXT, spend REAL, channel TEXT)"))
        conn.execute(text("CREATE TABLE employee_shifts (id INTEGER PRIMARY KEY, staff_name TEXT, shift_hours REAL)"))
        conn.execute(text("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, action TEXT, performed_by TEXT, logged_at TEXT)"))
        conn.execute(text("CREATE TABLE app_settings (id INTEGER PRIMARY KEY, setting_key TEXT, setting_value TEXT)"))

        # Seed minimal rows
        conn.execute(text("INSERT INTO customers VALUES (1, 'Alice Smith', 'alice@test.com', 'USA')"))
        conn.execute(text("INSERT INTO orders VALUES (1, 1, '2026-03-01', 'completed', 150.0)"))
        conn.execute(text("INSERT INTO products VALUES (1, 'Ergonomic Desk', 'Furniture', 299.99, 12)"))
        conn.execute(text("INSERT INTO order_items VALUES (1, 1, 1, 1, 299.99)"))
        conn.commit()

    url = f"sqlite:///{db_path.replace(os.sep, '/')}"
    yield url
    try:
        os.remove(db_path)
    except Exception:
        pass

def test_schema_pruning_table_selection(large_db_url):
    introspector = DatabaseIntrospector(large_db_url)
    pruned_md, meta = introspector.get_pruned_markdown_schema(
        user_query="Which customers placed orders with high total amounts?",
        max_tables=4
    )

    assert meta["is_pruned"] is True
    assert meta["total_tables"] == 12
    # Retained tables should clearly feature customers and orders
    assert "customers" in meta["retained_tables"]
    assert "orders" in meta["retained_tables"]
    # Irrelevant tables should be pruned out
    assert "audit_logs" in meta["pruned_tables"]
    assert "tax_jurisdictions" in meta["pruned_tables"]
    assert "employee_shifts" in meta["pruned_tables"]
    assert meta["estimated_tokens_saved"] > 0

    # Pruned markdown should contain customers definition but not tax_jurisdictions
    assert "Table: `customers`" in pruned_md
    assert "Table: `orders`" in pruned_md
    assert "Table: `tax_jurisdictions`" not in pruned_md

def test_foreign_key_bridge_retention(large_db_url):
    """When asking about customers and products, order_items and orders must be preserved to bridge the join."""
    introspector = DatabaseIntrospector(large_db_url)
    pruned_md, meta = introspector.get_pruned_markdown_schema(
        user_query="Show what products customer Alice purchased",
        max_tables=3
    )

    assert meta["is_pruned"] is True
    assert "customers" in meta["retained_tables"]
    assert "products" in meta["retained_tables"]
    # order_items or orders bridging relationships should be kept
    assert ("orders" in meta["retained_tables"]) or ("order_items" in meta["retained_tables"])

def test_small_schema_bypass():
    """Databases with small number of tables should not be pruned by default."""
    pruner = SchemaPruner(min_tables_to_prune=7)
    sample_schema = {
        "database_type": "sqlite",
        "table_count": 3,
        "tables": [
            {"name": "users", "columns": [{"name": "id"}], "foreign_keys": []},
            {"name": "posts", "columns": [{"name": "id"}], "foreign_keys": []},
            {"name": "comments", "columns": [{"name": "id"}], "foreign_keys": []}
        ]
    }
    _, meta = pruner.prune(sample_schema, user_query="Show all users", force_prune=False)
    assert meta["is_pruned"] is False
    assert len(meta["retained_tables"]) == 3
    assert meta["estimated_tokens_saved"] == 0

def test_engine_returns_pruning_metadata(large_db_url):
    client = LLMClient(api_key=None, provider="gemini")
    engine = TextToSQLEngine(db_url=large_db_url, llm_client=client)

    result = engine.process_natural_language_query(
        user_prompt="List all customers and their email addresses",
        prune_schema=True,
        max_tables=4
    )

    assert result["success"] is True
    assert "schema_pruning" in result
    pruning = result["schema_pruning"]
    assert pruning["is_pruned"] is True
    assert "customers" in pruning["retained_tables"]
    assert "audit_logs" in pruning["pruned_tables"]
    assert pruning["estimated_tokens_saved"] > 0
