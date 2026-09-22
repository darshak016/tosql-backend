"""
Singleton Connection Pool Manager.

Provides a global registry of SQLAlchemy engines keyed by database URL.
Engines are created once with optimal pooling configuration and reused
across all requests, eliminating the ~50-150ms overhead of creating a
new engine per request.
"""

import threading
from typing import Dict, Optional
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine


class ConnectionPoolManager:
    """
    Thread-safe singleton that manages one SQLAlchemy Engine per unique database URL.
    
    Features:
        - Connection pooling with configurable pool_size and max_overflow
        - pool_pre_ping=True for automatic stale connection detection
        - pool_recycle=1800 to prevent stale long-lived connections
        - Thread-safe engine creation via double-checked locking
    """

    _instance: Optional["ConnectionPoolManager"] = None
    _init_lock = threading.Lock()

    def __new__(cls) -> "ConnectionPoolManager":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._engines: Dict[str, Engine] = {}
                    cls._instance._lock = threading.Lock()
        return cls._instance

    def get_engine(self, db_url: str) -> Engine:
        """
        Returns a cached Engine for the given URL, creating one if it doesn't exist.
        
        SQLite URLs get NullPool (no pooling) since SQLite doesn't support
        concurrent connections well. All other dialects get QueuePool with
        optimal settings.
        """
        if db_url in self._engines:
            return self._engines[db_url]

        with self._lock:
            # Double-checked locking
            if db_url in self._engines:
                return self._engines[db_url]

            is_sqlite = db_url.startswith("sqlite")

            if is_sqlite:
                from sqlalchemy.pool import StaticPool
                engine = create_engine(
                    db_url,
                    connect_args={"check_same_thread": False},
                    poolclass=StaticPool,
                )
            else:
                engine = create_engine(
                    db_url,
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    pool_recycle=1800,
                    pool_timeout=30,
                )

            self._engines[db_url] = engine
            return engine

    def dispose_engine(self, db_url: str) -> None:
        """Disposes and removes a cached engine (e.g. on reconnection)."""
        with self._lock:
            engine = self._engines.pop(db_url, None)
            if engine:
                engine.dispose()

    def dispose_all(self) -> None:
        """Disposes all cached engines (e.g. on shutdown)."""
        with self._lock:
            for engine in self._engines.values():
                engine.dispose()
            self._engines.clear()


# Module-level singleton accessor
_pool_manager = ConnectionPoolManager()


def get_engine(db_url: str) -> Engine:
    """
    Module-level convenience function.
    Returns a pooled, cached SQLAlchemy Engine for the given database URL.
    """
    return _pool_manager.get_engine(db_url)


def dispose_engine(db_url: str) -> None:
    """Dispose and remove a specific engine from the pool."""
    _pool_manager.dispose_engine(db_url)


def dispose_all_engines() -> None:
    """Dispose all pooled engines."""
    _pool_manager.dispose_all()
