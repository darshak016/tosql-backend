"""
LRU + TTL Cache for LLM Responses.

Caches SQL generation results from the LLM to avoid redundant API calls
when users ask the same (or identical) question against the same schema.

Key: hash(normalized_prompt_text + dialect)
Saves 1-5 seconds per cache hit (the full LLM round-trip).
"""

import time
import hashlib
import threading
from typing import Any, Dict, Optional
from collections import OrderedDict


class LLMResponseCache:
    """
    Thread-safe LRU cache with TTL for LLM responses.
    
    - Max entries: configurable (default 128)
    - Default TTL: 600 seconds (10 minutes)
    - LRU eviction when capacity is exceeded
    """

    def __init__(self, max_entries: int = 128, default_ttl: int = 600):
        self._cache: OrderedDict[str, tuple] = OrderedDict()  # key -> (value, expiry)
        self._lock = threading.Lock()
        self._max_entries = max_entries
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(prompt: str) -> str:
        """Create a cache key from the full prompt text."""
        normalized = prompt.strip().lower()
        return hashlib.sha256(normalized.encode()).hexdigest()

    def get(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Retrieve a cached LLM response, or None if not found/expired."""
        key = self._make_key(prompt)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            value, expiry = entry
            if time.monotonic() > expiry:
                del self._cache[key]
                self._misses += 1
                return None
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def set(self, prompt: str, value: Dict[str, Any], ttl: Optional[int] = None) -> None:
        """Store an LLM response in cache."""
        key = self._make_key(prompt)
        expiry = time.monotonic() + (ttl or self._default_ttl)
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = (value, expiry)
            # Evict LRU entries if over capacity
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def invalidate_all(self) -> None:
        """Clear the entire LLM response cache."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> Dict[str, int]:
        """Return cache hit/miss statistics."""
        with self._lock:
            return {
                "entries": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_pct": round(
                    self._hits / max(1, self._hits + self._misses) * 100, 1
                ),
            }


# Module-level singleton
llm_cache = LLMResponseCache(max_entries=128, default_ttl=600)
