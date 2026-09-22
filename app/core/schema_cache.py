"""
TTL-based In-Memory Schema Cache.

Caches database schema introspection results (structured dicts and formatted
markdown) to avoid repeated expensive database reflection queries.

Typical schema introspection costs ~200-800ms for large databases.
With caching, repeated reads drop to ~0.1ms.
"""

import time
import threading
import hashlib
from typing import Any, Dict, Optional, Tuple


class SchemaCache:
    """
    Thread-safe TTL cache for database schema data.
    
    Keys are derived from (db_url, include_samples) tuples.
    Default TTL is 300 seconds (5 minutes).
    """

    def __init__(self, default_ttl: int = 300):
        self._cache: Dict[str, Tuple[Any, float]] = {}  # key -> (value, expiry_timestamp)
        self._lock = threading.Lock()
        self._default_ttl = default_ttl

    def _make_key(self, db_url: str, suffix: str = "") -> str:
        """Generate a cache key from URL + suffix."""
        url_hash = hashlib.md5(db_url.encode()).hexdigest()
        return f"{url_hash}:{suffix}"

    def get(self, db_url: str, suffix: str = "") -> Optional[Any]:
        """Get a cached value if it exists and hasn't expired."""
        key = self._make_key(db_url, suffix)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            value, expiry = entry
            if time.monotonic() > expiry:
                del self._cache[key]
                return None
            return value

    def set(self, db_url: str, value: Any, suffix: str = "", ttl: Optional[int] = None) -> None:
        """Store a value with TTL."""
        key = self._make_key(db_url, suffix)
        expiry = time.monotonic() + (ttl or self._default_ttl)
        with self._lock:
            self._cache[key] = (value, expiry)

    def invalidate(self, db_url: str) -> None:
        """Remove all cached entries for a specific database URL."""
        url_hash = hashlib.md5(db_url.encode()).hexdigest()
        prefix = f"{url_hash}:"
        with self._lock:
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._cache[k]

    def invalidate_all(self) -> None:
        """Clear the entire cache."""
        with self._lock:
            self._cache.clear()

    def stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        with self._lock:
            now = time.monotonic()
            total = len(self._cache)
            alive = sum(1 for _, (_, exp) in self._cache.items() if now <= exp)
            return {"total_entries": total, "alive_entries": alive, "expired_entries": total - alive}


# Module-level singleton
schema_cache = SchemaCache(default_ttl=300)

# Cache key suffixes
CACHE_STRUCTURED_SAMPLES = "structured:samples"
CACHE_STRUCTURED_NO_SAMPLES = "structured:no_samples"
CACHE_MARKDOWN = "markdown"
