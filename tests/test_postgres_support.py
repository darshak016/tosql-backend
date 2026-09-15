import pytest
import psycopg2
from sqlalchemy.dialects import postgresql
from app.core.security import validate_and_sanitize_sql

def test_psycopg2_driver_ready():
    assert hasattr(psycopg2, "connect")

def test_postgresql_dialect_ast_validation():
    # PostgreSQL specific query with DATE_TRUNC and NOW()
    sql = "SELECT DATE_TRUNC('month', order_date) as month, SUM(total_amount) FROM orders GROUP BY 1"
    is_valid, sanitized, err = validate_and_sanitize_sql(sql, dialect="postgres")
    assert is_valid is True
    assert "LIMIT 200" in sanitized.upper()
    assert err is None

def test_postgresql_dialect_blocks_destructive_query():
    sql = "TRUNCATE TABLE customers RESTART IDENTITY"
    is_valid, sanitized, err = validate_and_sanitize_sql(sql, dialect="postgres")
    assert is_valid is False
    assert "Disallowed operation" in err
