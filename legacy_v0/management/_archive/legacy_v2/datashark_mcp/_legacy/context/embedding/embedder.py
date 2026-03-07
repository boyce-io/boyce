"""
Embedder Implementations

Base protocol and implementations for text embedding.
"""

from __future__ import annotations

import hashlib
from typing import Protocol, List
from abc import ABC, abstractmethod


class BaseEmbedder(Protocol):
    """Protocol for embedder implementations."""
    
    def embed_text(self, text: str) -> List[float]:
        """
        Embed text into vector.
        
        Args:
            text: Input text
            
        Returns:
            List of floats (embedding vector)
        """
        ...


class SimpleHashEmbedder:
    """
    Deterministic hash-based embedder (placeholder).
    
    Uses SHA-256 hash to generate fixed-size vector.
    Not semantically meaningful but deterministic.
    """
    
    def __init__(self, dimensions: int = 128):
        """
        Initialize hash embedder.
        
        Args:
            dimensions: Vector dimensions (default: 128)
        """
        self.dimensions = dimensions
    
    def embed_text(self, text: str) -> List[float]:
        """
        Embed text using hash-based approach.
        
        Args:
            text: Input text
            
        Returns:
            List of floats (deterministic)
        """
        # Generate deterministic hash
        sha256 = hashlib.sha256(text.encode("utf-8"))
        hash_bytes = sha256.digest()
        
        # Convert to vector (deterministic)
        vector = []
        for i in range(self.dimensions):
            byte_idx = i % len(hash_bytes)
            # Normalize to [-1, 1] range
            value = (hash_bytes[byte_idx] / 255.0) * 2.0 - 1.0
            vector.append(value)
        
        return vector


class OpenAIEmbedder:
    """
    Placeholder for OpenAI embedding (not implemented yet).
    
    This is an abstract placeholder - no API key logic implemented.
    """
    
    def __init__(self, model: str = "text-embedding-ada-002"):
        """
        Initialize OpenAI embedder (placeholder).
        
        Args:
            model: Model name (not used yet)
        """
        self.model = model
        raise NotImplementedError("OpenAIEmbedder not implemented yet - use SimpleHashEmbedder")


def get_embedder(embedder_type: str = "hash", dimensions: int = 128) -> BaseEmbedder:
    """
    Factory function to get embedder.
    
    Args:
        embedder_type: "hash" or "openai"
        dimensions: Vector dimensions (for hash embedder)
        
    Returns:
        Embedder instance
    """
    if embedder_type == "hash":
        return SimpleHashEmbedder(dimensions=dimensions)
    elif embedder_type == "openai":
        return OpenAIEmbedder()
    else:
        raise ValueError(f"Unknown embedder type: {embedder_type}")

