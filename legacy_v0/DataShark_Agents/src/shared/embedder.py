"""
Shared embedder: local sentence-transformers model (all-MiniLM-L6-v2, 384-d).
CPU-optimized; no forced CUDA/MPS.
"""
from __future__ import annotations

import re
from sentence_transformers import SentenceTransformer

MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384


def _clean_text(text: str) -> str:
    """Collapse whitespace and strip; avoid empty input for encoder."""
    if not text or not text.strip():
        return " "
    return re.sub(r"\s+", " ", text.strip())


class LocalEmbedder:
    """Local embedder using all-MiniLM-L6-v2. CPU-optimized; uses CUDA/MPS only if auto-detected."""

    def __init__(self) -> None:
        # No device override: use CPU by default; CUDA/MPS only if detected by the library
        self._model = SentenceTransformer(MODEL_ID)

    def embed_text(self, text: str) -> list[float]:
        """
        Encode text to a 384-dimensional vector. Returns a standard Python list.
        Cleans newlines/whitespace before encoding.
        """
        cleaned = _clean_text(text)
        vec = self._model.encode(cleaned, convert_to_numpy=True)
        return vec.tolist()
