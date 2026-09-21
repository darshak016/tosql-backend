import pytest
import os
from app.engine.query_runner import QueryRunner
from app.core.security import validate_query_for_explain, strip_explain_prefix
from app.samples.seed_samples import seed_ecommerce_db

@pytest.fixture(scope="module")
def sample_db_url():
    db_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "test_explain_plan.db")
    seed_ecommerce_db(db_path)
    url = f"sqlite:///{db_path.replace(os.sep, '/')}"
    yield url
    try:
        os.remove(db_path)
    except Exception:
        pass

def test_strip_explain_prefix():
    assert strip_explain_prefix("EXPLAIN SELECT * FROM customers") == "SELECT * FROM customers"
    assert strip_explain_prefix("EXPLAIN QUERY PLAN SELECT * FROM customers") == "SELECT * FROM customers"
    assert strip_explain_prefix("explain   analyze  SELECT * FROM customers") == "SELECT * FROM customers"
    assert strip_explain_prefix("SELECT * FROM customers") == "SELECT * FROM customers"

def test_validate_query_for_explain():
    is_valid, sanitized, err = validate_query_for_explain("SELECT * FROM customers WHERE id = 1", dialect="sqlite")
    assert is_valid is True
    assert "customers" in sanitized.lower()
    assert err is None

    # Destructive operations should be rejected even with EXPLAIN
    is_valid, _, err = validate_query_for_explain("EXPLAIN DELETE FROM customers WHERE id = 1", dialect="sqlite")
    assert is_valid is False
    assert "Disallowed" in err or "SELECT" in err

    is_valid, _, err = validate_query_for_explain("EXPLAIN DROP TABLE customers", dialect="sqlite")
    assert is_valid is False

def test_explain_simple_scan_query(sample_db_url):
    runner = QueryRunner(sample_db_url)
    res = runner.explain_query("SELECT * FROM customers")
    
    assert res["success"] is True
    assert res["dialect"] == "sqlite"
    assert "EXPLAIN" in res["plan_type"]
    assert len(res["plan_rows"]) > 0
    assert len(res["raw_plan"]) > 0
    assert any("SCAN" in detail for detail in res["raw_plan"])
    assert res["has_table_scan"] is True
    assert res["execution_time_ms"] >= 0

def test_explain_join_and_index_query(sample_db_url):
    runner = QueryRunner(sample_db_url)
    sql = "SELECT c.name, o.total_amount FROM customers c JOIN orders o ON c.id = o.customer_id WHERE c.id = 5"
    res = runner.explain_query(sql)

    assert res["success"] is True
    assert len(res["plan_rows"]) > 0
    # Customer lookup by primary key uses index / search
    assert res["has_index_lookup"] is True or any("SEARCH" in d or "USING" in d for d in res["raw_plan"])

def test_explain_blocked_on_destructive_sql(sample_db_url):
    runner = QueryRunner(sample_db_url)
    res = runner.explain_query("DROP TABLE customers")
    assert res["success"] is False
    assert "Security / Validation Violation" in res["error"]
