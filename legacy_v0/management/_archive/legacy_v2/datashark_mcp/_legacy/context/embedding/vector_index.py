"""
Vector Index

In-memory cosine-similarity index for semantic search.
"""

from __future__ import annotations

import math
from typing import List, Tuple, Iterable
from datashark_mcp.context.models import Node
from datashark_mcp.context.embedding.embedder import BaseEmbedder, SimpleHashEmbedder


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Compute cosine similarity between two vectors.
    
    Args:
        vec1: First vector
        vec2: Second vector
        
    Returns:
        Cosine similarity (0.0-1.0)
    """
    if len(vec1) != len(vec2):
        raise ValueError("Vectors must have same length")
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)


class VectorIndex:
    """In-memory vector index with cosine similarity search."""
    
    def __init__(self, embedder: BaseEmbedder = None):
        """
        Initialize vector index.
        
        Args:
            embedder: Embedder instance (defaults to SimpleHashEmbedder)
        """
        self.embedder = embedder or SimpleHashEmbedder()
        self._vectors: List[Tuple[Node, List[float]]] = []
    
    def build_index(self, nodes: Iterable[Node]) -> None:
        """
        Build index from nodes.
        
        Args:
            nodes: Iterable of nodes to index
        """
        self._vectors = []
        
        for node in nodes:
            # Create embedding from node name and attributes
            text = f"{node.name} {str(node.attributes)}"
            vector = self.embedder.embed_text(text)
            self._vectors.append((node, vector))
        
        # Sort by node ID for deterministic ordering
        self._vectors.sort(key=lambda x: x[0].id)
    
    def query_vector(self, query_vec: List[float], top_k: int = 10) -> List[Tuple[Node, float]]:
        """
        Query index with vector and return top-k similar nodes.
        
        Args:
            query_vec: Query vector
            top_k: Number of results to return
            
        Returns:
            List of (node, similarity_score) tuples, sorted by similarity descending
        """
        results = []
        
        for node, vec in self._vectors:
            similarity = cosine_similarity(query_vec, vec)
            results.append((node, similarity))
        
        # Sort by similarity descending, then by node ID for tie-breaking (deterministic)
        results.sort(key=lambda x: (-x[1], x[0].id))
        
        return results[:top_k]
    
    def query_text(self, text: str, top_k: int = 10) -> List[Tuple[Node, float]]:
        """
        Query index with text (embeds text first).
        
        Args:
            text: Query text
            top_k: Number of results to return
            
        Returns:
            List of (node, similarity_score) tuples
        """
        query_vec = self.embedder.embed_text(text)
        return self.query_vector(query_vec, top_k)

