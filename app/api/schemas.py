from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ConnectRequest(BaseModel):
    db_url: Optional[str] = Field(None, description="SQLAlchemy connection URL (sqlite, postgresql, mysql)")
    use_sample_db: bool = Field(True, description="Connect to bundled sample ecommerce SQLite DB")

class GlossaryTerm(BaseModel):
    term: str = Field(..., min_length=1, description="Domain specific business term or alias")
    definition: str = Field(..., min_length=1, description="Exact SQL filter expression, formula, or meaning")
    category: Optional[str] = Field(None, description="Optional category tag e.g. 'Revenue', 'Status'")

class FewShotExample(BaseModel):
    prompt: str = Field(..., min_length=1, description="Natural language question")
    sql: str = Field(..., min_length=1, description="Target golden SQL statement answering the question")
    explanation: Optional[str] = Field(None, description="Optional explanation or intent note")

class DictionaryConfig(BaseModel):
    terms: List[GlossaryTerm] = Field(default_factory=list)
    few_shots: List[FewShotExample] = Field(default_factory=list)

class NaturalLanguageQueryRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="Natural language question")
    db_url: Optional[str] = Field(None, description="Target database URL")
    api_key: Optional[str] = Field(None, description="Optional custom Gemini or OpenAI API key")
    provider: Optional[str] = Field("gemini", description="LLM provider: 'gemini' or 'openai'")
    model_name: Optional[str] = Field(None, description="Specific model name")
    previous_sql: Optional[str] = Field(None, description="SQL from previous turn for conversational follow-ups")
    previous_prompt: Optional[str] = Field(None, description="User prompt from previous turn")
    glossary_terms: Optional[List[GlossaryTerm]] = Field(default=None, description="Custom domain glossary definitions")
    few_shot_examples: Optional[List[FewShotExample]] = Field(default=None, description="Custom golden question/SQL pairs")

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

class QueryBreakdown(BaseModel):
    tables_used: List[str] = Field(default_factory=list, description="Tables referenced in the query")
    joins: List[str] = Field(default_factory=list, description="Join conditions or relationships used")
    filters: List[str] = Field(default_factory=list, description="WHERE filters applied")
    aggregations: List[str] = Field(default_factory=list, description="Aggregations or group-bys used")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions or business logic caveats")

class QueryResponse(BaseModel):
    success: bool
    prompt: Optional[str] = None
    sql: Optional[str] = None
    explanation: Optional[str] = None
    breakdown: Optional[QueryBreakdown] = None
    suggested_chart: Optional[str] = "table"
    chart_config: Optional[Dict[str, Any]] = None
    data: QueryResultData
    error: Optional[str] = None
    self_healed: bool = False
    attempts: Optional[List[Dict[str, Any]]] = None

class ExplainPlanRequest(BaseModel):
    sql: str = Field(..., min_length=1, description="SQL query to explain")
    db_url: Optional[str] = Field(None, description="Target database URL")

class ExplainPlanResponse(BaseModel):
    success: bool
    dialect: str
    plan_type: str
    raw_plan: List[str] = Field(default_factory=list)
    plan_rows: List[Dict[str, Any]] = Field(default_factory=list)
    has_table_scan: bool = False
    has_index_lookup: bool = False
    execution_time_ms: float = 0.0
    sql: str
    error: Optional[str] = None

