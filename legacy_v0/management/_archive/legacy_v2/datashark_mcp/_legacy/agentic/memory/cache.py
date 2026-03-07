"""
Deterministic Cache

In-memory cache keyed by DSL + parameters with deterministic behavior.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Callable, Optional, TypeVar
from functools import wraps

T = TypeVar("T")


class DeterministicCache:
    """Deterministic in-memory cache."""
    
    def __init__(self, ttl: Optional[float] = None):
        """
        Initialize cache.
        
        Args:
            ttl: Time-to-live in seconds (None = persist for session lifetime)
        """
        self.ttl = ttl
        self._cache: Dict[str, tuple[Any, float]] = {}  # key -> (value, expiry_time)
    
    def _make_key(self, func_name: str, *args, **kwargs) -> str:
        """Generate deterministic cache key."""
        key_data = {
            "func": func_name,
            "args": args,
            "kwargs": kwargs
        }
        key_str = json.dumps(key_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        if key in self._cache:
            value, expiry = self._cache[key]
            if self.ttl is None or time.time() < expiry:
                return value
            else:
                del self._cache[key]
        return None
    
    def set(self, key: str, value: Any) -> None:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
        """
        if self.ttl:
            expiry = time.time() + self.ttl
        else:
            expiry = float("inf")  # Never expire
        
        self._cache[key] = (value, expiry)
    
    def get_or_compute(self, func: Callable[[], T], key: str) -> T:
        """
        Get from cache or compute and cache.
        
        Args:
            func: Function to compute value
            key: Cache key
            
        Returns:
            Cached or computed value
        """
        cached = self.get(key)
        if cached is not None:
            return cached
        
        value = func()
        self.set(key, value)
        return value
    
    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
    
    def size(self) -> int:
        """Get cache size."""
        return len(self._cache)


def cached(cache: DeterministicCache, key_func: Callable = None):
    """
    Decorator for caching function results.
    
    Args:
        cache: DeterministicCache instance
        key_func: Optional function to generate cache key
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            if key_func:
                key = key_func(*args, **kwargs)
            else:
                key = cache._make_key(func.__name__, *args, **kwargs)
            
            return cache.get_or_compute(lambda: func(*args, **kwargs), key)
        
        return wrapper
    return decorator

