import pytest
from app.engine.prompt_builder import build_sql_generation_prompt
from app.engine.self_healer import TextToSQLEngine
from app.core.config import settings

@pytest.fixture
def sample_db_url():
    return f"sqlite:///{settings.DEFAULT_DB_PATH}"

def test_prompt_builder_includes_glossary_terms():
    glossary = [
        {"term": "active customer", "definition": "orders placed in last 90 days", "category": "Status"},
        {"term": "VIP customer", "definition": "total_amount > 500", "category": "Loyalty"}
    ]
    prompt = build_sql_generation_prompt(
        user_query="Who are our active customers?",
        schema_markdown="TABLE customers (id, name)",
        dialect="sqlite",
        glossary_terms=glossary
    )
    assert "Domain Glossary & Business Logic Rules:" in prompt
    assert "\"active customer\" [Status]: orders placed in last 90 days" in prompt
    assert "\"VIP customer\" [Loyalty]: total_amount > 500" in prompt

def test_prompt_builder_includes_few_shots():
    few_shots = [
        {
            "prompt": "Show top 3 products by price",
            "sql": "SELECT name, price FROM products ORDER BY price DESC LIMIT 3",
            "explanation": "Retrieves top products"
        }
    ]
    prompt = build_sql_generation_prompt(
        user_query="Which products cost the most?",
        schema_markdown="TABLE products (id, name, price)",
        dialect="sqlite",
        few_shot_examples=few_shots
    )
    assert "Reference Example Queries (Few-Shot):" in prompt
    assert "Show top 3 products by price" in prompt
    assert "SELECT name, price FROM products ORDER BY price DESC LIMIT 3" in prompt

def test_engine_executes_few_shot_matching(sample_db_url):
    engine = TextToSQLEngine(db_url=sample_db_url)
    custom_few_shots = [
        {
            "prompt": "Custom VIP member lookup",
            "sql": "SELECT id, name, email FROM customers WHERE country = 'USA' LIMIT 2",
            "explanation": "Matched custom few shot example."
        }
    ]
    res = engine.process_natural_language_query(
        user_prompt="Custom VIP member lookup",
        few_shot_examples=custom_few_shots
    )
    assert res["success"] is True
    assert "SELECT id, name, email FROM customers WHERE country = 'USA' LIMIT 2" in res["sql"]
    assert res["data"]["row_count"] <= 2
