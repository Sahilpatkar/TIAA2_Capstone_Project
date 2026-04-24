"""LLM advisor and RAG retrieval settings.

To switch to AWS, flip the providers and vector store:
    RAG_EMBEDDING_PROVIDER = "bedrock"
    RAG_LLM_PROVIDER = "bedrock"
    RAG_VECTOR_STORE = "opensearch"
"""

import os

from tiaa.config.paths import DATA_DIR

LLM_MODEL = "gpt-4.1-mini"

RAG_ENABLED = True
RAG_EMBEDDING_PROVIDER = "openai"           # "openai" | "bedrock"
RAG_EMBEDDING_MODEL = "text-embedding-3-small"
RAG_LLM_PROVIDER = "openai"                 # "openai" | "bedrock"
RAG_VECTOR_STORE = "chroma"                 # "chroma" | "opensearch"
RAG_VECTORDB_DIR = os.path.join(DATA_DIR, "vectordb")
RAG_CHUNK_MAX_CHARS = 3000
RAG_CHUNK_OVERLAP = 200
RAG_TOP_K = 5
