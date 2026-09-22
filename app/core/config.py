import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "Natural Language to SQL Engine"
    API_V1_STR: str = "/api"
    
    # AI Providers
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: Optional[str] = None
    DEFAULT_MODEL: str = "gemini-2.5-flash"
    
    # Database Connection
    DATABASE_URL: Optional[str] = None
    
    # Security
    MAX_QUERY_ROWS: int = 200
    EXECUTION_TIMEOUT_SECONDS: int = 15

    # Performance
    WORKERS: int = 4
    IS_DEV: bool = True
    POOL_SIZE: int = 10
    SCHEMA_CACHE_TTL: int = 300
    LLM_CACHE_TTL: int = 600

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
