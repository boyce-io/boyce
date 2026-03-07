"""
Context Bridge

Interface between Agent and Context API with rate limiting and caching.
"""

from __future__ import annotations

import time
import hashlib
import json
from typing import Dict, Any, Optional, Callable
from datashark_mcp.context.api import ContextAPI
from datashark_mcp.context.enrichment.concept_catalog import ConceptCatalog
from datashark_mcp.context.enrichment.semantic_enricher import SemanticEnricher


class ContextBridge:
    """Bridge between agent and context layer with caching and rate limiting."""
    
    def __init__(
        self,
        api: ContextAPI,
        catalog: ConceptCatalog = None,
        cache_ttl: float = 3600.0
    ):
        """
        Initialize context bridge.
        
        Args:
            api: ContextAPI instance
            catalog: ConceptCatalog instance (optional)
            cache_ttl: Cache TTL in seconds (default: 1 hour)
        """
        self.api = api
        self.catalog = catalog or ConceptCatalog()
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, tuple[Any, float]] = {}  # key -> (value, expiry_time)
        self._rate_limit_calls = 0
        self._rate_limit_window_start = time.time()
    
    def _cache_key(self, operation: str, params: Dict[str, Any]) -> str:
        """Generate deterministic cache key."""
        key_data = {"op": operation, "params": params}
        key_str = json.dumps(key_data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(key_str.encode("utf-8")).hexdigest()
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, expiry = self._cache[key]
            if time.time() < expiry:
                return value
            else:
                del self._cache[key]
        return None
    
    def _set_cache(self, key: str, value: Any) -> None:
        """Set value in cache."""
        expiry = time.time() + self.cache_ttl
        self._cache[key] = (value, expiry)
    
    def _check_rate_limit(self) -> bool:
        """Check rate limit (simple: max 100 calls per second)."""
        now = time.time()
        if now - self._rate_limit_window_start > 1.0:
            self._rate_limit_calls = 0
            self._rate_limit_window_start = now
        
        if self._rate_limit_calls >= 100:
            return False
        
        self._rate_limit_calls += 1
        return True
    
    def query(self, operation: str, **params) -> Any:
        """
        Execute query with caching and rate limiting.
        
        Args:
            operation: Operation name (e.g., "find_entities_by_system")
            **params: Operation parameters
            
        Returns:
            Query result
        """
        if not self._check_rate_limit():
            raise RuntimeError("Rate limit exceeded")
        
        # Check cache
        cache_key = self._cache_key(operation, params)
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            return cached
        
        # Execute query
        if operation == "find_entities_by_system":
            result = self.api.find_entities_by_system(params["system"])
        elif operation == "find_entities_by_repo":
            result = self.api.find_entities_by_repo(params["repo"])
        elif operation == "search":
            result = self.api.search(params.get("term", ""), params.get("filters"))
        elif operation == "find_join_path":
            result = self.api.find_join_path(params["src_id"], params["dst_id"])
        elif operation == "find_join_paths_from":
            result = self.api.find_join_paths_from(params["node_id"], params.get("max_depth", 5))
        else:
            raise ValueError(f"Unknown operation: {operation}")
        
        # Cache result
        self._set_cache(cache_key, result)
        
        return result
    
    def get_concept(self, name: str) -> Optional[Any]:
        """Get concept from catalog."""
        return self.catalog.get_concept(name)
    
    def search_concepts(self, term: str) -> list:
        """Search concepts in catalog."""
        return self.catalog.search(term)
    
    def clear_cache(self) -> None:
        """Clear all cached results."""
        self._cache.clear()

