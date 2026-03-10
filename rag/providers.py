"""
Provider abstractions for embeddings, LLM, and vector store.

Each abstract base class has a concrete implementation for local dev
(OpenAI + ChromaDB). To switch to AWS, add Bedrock/OpenSearch
implementations and update config.RAG_* settings.
"""

from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from typing import Any

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import config  # noqa: E402


# ===================================================================
# Embedding Provider
# ===================================================================

class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return a list of embedding vectors, one per input text."""

    @abstractmethod
    def dimension(self) -> int:
        """Return the dimensionality of the embedding vectors."""


class OpenAIEmbeddings(EmbeddingProvider):
    MAX_CHARS = 28000  # ~8000 tokens safety limit for text-embedding-3-small

    def __init__(self, model: str | None = None, api_key: str | None = None):
        from openai import OpenAI
        self._model = model or config.RAG_EMBEDDING_MODEL
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._dim = 1536 if "small" in self._model else 3072

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        import time
        safe_texts = [t[: self.MAX_CHARS] if len(t) > self.MAX_CHARS else t for t in texts]
        batch_size = 20
        all_embeddings: list[list[float]] = []
        for i in range(0, len(safe_texts), batch_size):
            batch = safe_texts[i : i + batch_size]
            for attempt in range(5):
                try:
                    resp = self._client.embeddings.create(model=self._model, input=batch)
                    all_embeddings.extend([d.embedding for d in resp.data])
                    break
                except Exception as e:
                    if "rate_limit" in str(e).lower() or "429" in str(e):
                        wait = 2 ** attempt
                        print(f"    Rate limited, waiting {wait}s...")
                        time.sleep(wait)
                    else:
                        raise
            time.sleep(0.3)
        return all_embeddings

    def dimension(self) -> int:
        return self._dim


# ===================================================================
# LLM Provider
# ===================================================================

class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Send a list of {role, content} messages and return the response text."""


class OpenAIChat(LLMProvider):
    def __init__(self, model: str | None = None, api_key: str | None = None):
        from openai import OpenAI
        self._model = model or config.LLM_MODEL
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))

    def chat(self, messages: list[dict[str, str]], **kwargs) -> str:
        temperature = kwargs.get("temperature", 0.3)
        max_tokens = kwargs.get("max_tokens", 1000)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()


# ===================================================================
# Vector Store Provider
# ===================================================================

class VectorStoreProvider(ABC):
    @abstractmethod
    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Upsert documents with their embeddings and metadata."""

    @abstractmethod
    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        """Return top-K results as list of {id, document, metadata, distance}."""

    @abstractmethod
    def count(self) -> int:
        """Return total number of stored documents."""

    @abstractmethod
    def delete_by_metadata(self, where: dict) -> None:
        """Delete documents matching the metadata filter."""


class ChromaVectorStore(VectorStoreProvider):
    def __init__(self, collection_name: str = "lazyrices_filings", persist_dir: str | None = None):
        import chromadb
        self._persist_dir = persist_dir or config.RAG_VECTORDB_DIR
        os.makedirs(self._persist_dir, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self._persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        batch_size = 500
        for i in range(0, len(ids), batch_size):
            self._collection.upsert(
                ids=ids[i : i + batch_size],
                embeddings=embeddings[i : i + batch_size],
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )

    def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict | None = None,
    ) -> list[dict]:
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where

        results = self._collection.query(**kwargs)

        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]
        ids = results.get("ids", [[]])[0]

        return [
            {"id": ids[i], "document": docs[i], "metadata": metas[i], "distance": dists[i]}
            for i in range(len(docs))
        ]

    def count(self) -> int:
        return self._collection.count()

    def delete_by_metadata(self, where: dict) -> None:
        try:
            self._collection.delete(where=where)
        except Exception:
            pass


# ===================================================================
# Factory
# ===================================================================

def get_embedding_provider() -> EmbeddingProvider:
    provider = getattr(config, "RAG_EMBEDDING_PROVIDER", "openai")
    if provider == "openai":
        return OpenAIEmbeddings()
    raise ValueError(f"Unknown embedding provider: {provider}")


def get_llm_provider() -> LLMProvider:
    provider = getattr(config, "RAG_LLM_PROVIDER", "openai")
    if provider == "openai":
        return OpenAIChat()
    raise ValueError(f"Unknown LLM provider: {provider}")


def get_vector_store() -> VectorStoreProvider:
    store = getattr(config, "RAG_VECTOR_STORE", "chroma")
    if store == "chroma":
        return ChromaVectorStore()
    raise ValueError(f"Unknown vector store: {store}")
