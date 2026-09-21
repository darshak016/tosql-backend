import pytest
from app.engine.prompt_builder import build_sql_generation_prompt
from app.engine.self_healer import TextToSQLEngine
import os
from app.samples.seed_samples import seed_ecommerce_db

@pytest.fixture(scope="module")
def sample_db_url():
    db_dir = os.path.join(os.path.dirname(__file__), "temp")
    os.makedirs(db_dir, exist_ok=True)
    db_path = os.path.join(db_dir, "test_dict_ecommerce.db")
    seed_ecommerce_db(db_path)
    url = f"sqlite:///{db_path.replace(os.sep, '/')}"
    yield url
    try:
        os.remove(db_path)
    except Exception:
        pass

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
