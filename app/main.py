import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes_database import router as db_router
from app.api.routes_query import router as query_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: If DATABASE_URL is configured, test connection on startup
    if settings.DATABASE_URL:
        print(f"[*] Database URL configured: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")
    else:
        print("[*] No default DATABASE_URL configured. Waiting for connection via environment or UI.")
    yield

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="AI-Powered Natural Language to SQL Generation and Execution Engine",
    version="1.0.0",
    lifespan=lifespan
)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(db_router, prefix=settings.API_V1_STR)
app.include_router(query_router, prefix=settings.API_V1_STR)

@app.get("/")
def health_check():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "api_docs": "/docs",
        "has_database": bool(settings.DATABASE_URL)
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
