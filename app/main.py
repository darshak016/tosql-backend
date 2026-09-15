import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.samples.seed_samples import seed_ecommerce_db
from app.api.routes_database import router as db_router
from app.api.routes_query import router as query_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Ensure sample database exists
    if not os.path.exists(settings.DEFAULT_DB_PATH):
        print(f"[*] Initializing sample e-commerce database at {settings.DEFAULT_DB_PATH}...")
        seed_ecommerce_db(settings.DEFAULT_DB_PATH)
        print("[+] Sample database ready.")
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
        "default_db": settings.DEFAULT_DB_PATH
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
