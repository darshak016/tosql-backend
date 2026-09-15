from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ConnectRequest(BaseModel):
    db_url: Optional[str] = Field(None, description="SQLAlchemy connection URL (sqlite, postgresql, mysql)")
    use_sample_db: bool = Field(True, description="Connect to bundled sample ecommerce SQLite DB")

class NaturalLanguageQueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Natural language question")
    db_url: Optional[str] = Field(None, description="Target database URL")
    api_key: Optional[str] = Field(None, description="Optional custom Gemini or OpenAI API key")
    provider: Optional[str] = Field("gemini", description="LLM provider: 'gemini' or 'openai'")
    model_name: Optional[str] = Field(None, description="Specific model name")

class DirectSQLExecuteRequest(BaseModel):
    sql: str = Field(..., min_length=1, description="Raw SQL query to execute safely")
    db_url: Optional[str] = Field(None, description="Target database URL")

class ColumnSchema(BaseModel):
    name: str
    type: str
    nullable: bool
    is_primary_key: bool
    sample_values: List[str]

class ForeignKeySchema(BaseModel):
    constrained_columns: List[str]
    referred_table: Optional[str]
    referred_columns: List[str]

class TableSchema(BaseModel):
    name: str
    row_count: int
    columns: List[ColumnSchema]
    foreign_keys: List[ForeignKeySchema]

class DatabaseSchemaResponse(BaseModel):
    database_type: str
    table_count: int
    tables: List[TableSchema]
    active_db_url: str

class QueryResultData(BaseModel):
    columns: List[str]
    rows: List[List[Any]]
    row_count: int
    execution_time_ms: float

class QueryResponse(BaseModel):
    success: bool
    prompt: Optional[str] = None
    sql: Optional[str] = None
    explanation: Optional[str] = None
    suggested_chart: Optional[str] = "table"
    chart_config: Optional[Dict[str, Any]] = None
    data: QueryResultData
    error: Optional[str] = None
    self_healed: bool = False
    attempts: Optional[List[Dict[str, Any]]] = None
