import os
import pytest
from app.samples.seed_samples import seed_ecommerce_db
from app.engine.introspector import DatabaseIntrospector
from app.engine.query_runner import QueryRunner

@pytest.fixture(scope="module")
def sample_db():
    db_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "test_ecommerce.db")
    seed_ecommerce_db(db_path)
    url = f"sqlite:///{db_path.replace(os.sep, '/')}"
    yield url
    try:
        os.remove(db_path)
    except Exception:
        pass

def test_schema_introspection(sample_db):
    introspector = DatabaseIntrospector(sample_db)
    schema = introspector.get_structured_schema()
    
    assert schema["database_type"] == "sqlite"
    assert schema["table_count"] == 4
    
    table_names = [t["name"] for t in schema["tables"]]
    assert "customers" in table_names
    assert "products" in table_names
    assert "orders" in table_names
    assert "order_items" in table_names

def test_markdown_schema_generation(sample_db):
    introspector = DatabaseIntrospector(sample_db)
    md = introspector.get_markdown_schema_for_llm()
    assert "### Database Engine: SQLITE" in md
    assert "customers" in md
    assert "Relationships:" in md

def test_query_execution_runner(sample_db):
    runner = QueryRunner(sample_db)
    res = runner.execute_query("SELECT id, name, category, price FROM products LIMIT 3")
    assert res["success"] is True
    assert len(res["rows"]) == 3
    assert "name" in res["columns"]
    assert res["execution_time_ms"] >= 0
