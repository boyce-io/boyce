"""
DataShark Brain — Context Retrieval Engine for the Safety Protocol.

The Brain is a "Context Retrieval Engine," not a SQL generator. It returns
DDL/documentation from ChromaDB for the Planner. All SQL must come from
SQLBuilder.build_final_sql via process_request().

Uses OpenAI only for embeddings (via ChromaDB's OpenAIEmbeddingFunction).
No chat completions; no SQL generation.
"""

__import__('pysqlite3')
import sys
sys.modules['sqlite3'] = sys.modules.pop('pysqlite3')

import hashlib
import os
from typing import Any

import chromadb
from chromadb.utils import embedding_functions


class DataSharkBrain:
    """
    Context retrieval for the DataShark Safety Protocol.

    - train(ddl): Ingest DDL into ChromaDB. Preserved.
    - retrieve_context(question, n_results): Return combined DDL/docs string for the Planner.
    No OpenAI chat completion; no SQL generation.
    """

    def __init__(self, api_key: str = None):
        """
        Initialize the Brain.

        Args:
            api_key: OpenAI API Key for embeddings only (used by ChromaDB embedding function).
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API Key is required for embeddings")

        self.chroma_client = chromadb.PersistentClient(path="storage/brain_vectors")
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=self.api_key,
            model_name="text-embedding-3-small"
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name="datashark_v2",
            embedding_function=openai_ef
        )

    def train(self, ddl: str) -> None:
        """
        Add DDL to the vector store.

        Preserved for ingestion. retrieve_context() returns this for the Planner.
        """
        if not ddl or not ddl.strip():
            return
        doc_id = hashlib.sha256(ddl.encode()).hexdigest()
        self.collection.upsert(
            documents=[ddl],
            ids=[doc_id],
            metadatas=[{"type": "ddl"}]
        )

    def retrieve_context(self, question: str, n_results: int = 5) -> str:
        """
        Retrieve relevant DDL/documentation from ChromaDB and return a combined context string.

        Does NOT call any LLM for chat completion. Does NOT generate SQL.
        Use the returned string in the Planner prompt so StructuredFilter is produced
        and SQL comes only from SQLBuilder.

        Args:
            question: Natural language question (used for similarity search).
            n_results: Maximum number of chunks to include (default 5).

        Returns:
            Combined context string (chunks joined by newlines). Empty string if none.
        """
        results: Any = self.collection.query(
            query_texts=[question],
            n_results=min(n_results, 20)
        )
        if not results or not results.get("documents") or not results["documents"][0]:
            return ""
        chunks = list(results["documents"][0])
        return "\n\n".join(chunks) if chunks else ""
