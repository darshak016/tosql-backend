import os
import pytest
from app.engine.self_healer import TextToSQLEngine
from app.engine.llm_client import LLMClient
from app.samples.seed_samples import seed_ecommerce_db

@pytest.fixture(scope="module")
def seeded_db_url():
    db_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "test_pipeline.db")
    seed_ecommerce_db(db_path)
    url = f"sqlite:///{db_path.replace(os.sep, '/')}"
    yield url
    try:
        os.remove(db_path)
    except Exception:
        pass

def test_mock_fallback_query_pipeline(seeded_db_url):
    # LLMClient without API keys triggers the intelligent offline fallback
    client = LLMClient(api_key=None, provider="gemini")
    engine = TextToSQLEngine(db_url=seeded_db_url, llm_client=client)

    result = engine.process_natural_language_query("Show top 5 customers who spent the most")
    assert result["success"] is True
    assert "SELECT" in result["sql"]
    assert "customers" in result["sql"].lower()
    assert result["data"]["row_count"] > 0
    assert result["suggested_chart"] == "bar"
    assert "total_spent" in result["data"]["columns"]

def test_low_stock_query_pipeline(seeded_db_url):
    client = LLMClient(api_key=None, provider="gemini")
    engine = TextToSQLEngine(db_url=seeded_db_url, llm_client=client)

    result = engine.process_natural_language_query("Which products are low on stock?")
    assert result["success"] is True
    assert result["data"]["row_count"] > 0
    assert "products" in result["sql"].lower()

def test_greeting_does_not_execute_sql(seeded_db_url):
    client = LLMClient(api_key=None, provider="gemini")
    engine = TextToSQLEngine(db_url=seeded_db_url, llm_client=client)

    result = engine.process_natural_language_query("Hello")
    assert result["success"] is True
    assert result["sql"] is None
    assert "Hello!" in result["explanation"]
    assert result["data"]["row_count"] == 0

def test_conversational_follow_up(seeded_db_url):
    client = LLMClient(api_key=None, provider="gemini")
    engine = TextToSQLEngine(db_url=seeded_db_url, llm_client=client)

    # Initial query
    res1 = engine.process_natural_language_query("Show top 5 customers who spent the most")
    assert res1["success"] is True
    assert "LIMIT 5" in res1["sql"]

    # Follow-up query: refine limit to 2
    res2 = engine.process_natural_language_query(
        user_prompt="Only show top 2 instead",
        previous_sql=res1["sql"],
        previous_prompt="Show top 5 customers who spent the most"
    )
    assert res2["success"] is True
    assert "LIMIT 2" in res2["sql"]
    assert res2["data"]["row_count"] == 2

def test_structured_query_breakdown(seeded_db_url):
    client = LLMClient(api_key=None, provider="gemini")
    engine = TextToSQLEngine(db_url=seeded_db_url, llm_client=client)

    result = engine.process_natural_language_query("Show top 5 customers who spent the most")
    assert result["success"] is True
    assert "breakdown" in result
    breakdown = result["breakdown"]
    assert isinstance(breakdown, dict)
    assert "customers" in [t.lower() for t in breakdown.get("tables_used", [])]
    assert len(breakdown.get("joins", [])) > 0
    assert len(breakdown.get("aggregations", [])) > 0
