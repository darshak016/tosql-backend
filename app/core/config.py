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
    
    # Default Database Path
    DEFAULT_DB_PATH: str = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "samples", "ecommerce.db")
    )
    
    # Security
    MAX_QUERY_ROWS: int = 200
    EXECUTION_TIMEOUT_SECONDS: int = 15

    model_config = {"env_file": ".env", "extra": "ignore"}

settings = Settings()
