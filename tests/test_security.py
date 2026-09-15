import pytest
from app.core.security import validate_and_sanitize_sql

def test_safe_select_query():
    sql = "SELECT id, name FROM customers WHERE country = 'USA'"
    is_valid, sanitized, err = validate_and_sanitize_sql(sql, dialect="sqlite")
    assert is_valid is True
    assert "LIMIT 200" in sanitized or "limit 200" in sanitized.lower()
    assert err is None

def test_block_drop_table():
    sql = "DROP TABLE customers"
    is_valid, sanitized, err = validate_and_sanitize_sql(sql, dialect="sqlite")
    assert is_valid is False
    assert "Disallowed operation" in err or "DROP" in err

def test_block_delete_statement():
    sql = "DELETE FROM orders WHERE id = 1"
    is_valid, sanitized, err = validate_and_sanitize_sql(sql, dialect="sqlite")
    assert is_valid is False
    assert "Disallowed operation" in err or "DELETE" in err

def test_block_update_statement():
    sql = "UPDATE products SET price = 0 WHERE id = 1"
    is_valid, sanitized, err = validate_and_sanitize_sql(sql, dialect="sqlite")
    assert is_valid is False
    assert "Disallowed operation" in err or "UPDATE" in err

def test_block_nested_injection_or_multi_statement():
    sql = "SELECT * FROM products; DROP TABLE products;"
    is_valid, sanitized, err = validate_and_sanitize_sql(sql, dialect="sqlite")
    assert is_valid is False
    assert "denied" in err.lower() or "disallowed" in err.lower() or "DROP" in err

def test_respect_lower_custom_limit():
    sql = "SELECT * FROM products LIMIT 5"
    is_valid, sanitized, err = validate_and_sanitize_sql(sql, dialect="sqlite", max_rows=100)
    assert is_valid is True
    assert "5" in sanitized
