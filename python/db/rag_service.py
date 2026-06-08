"""
db/rag_service.py — LangChain SupabaseVectorStore wrapper.
Provides get_vector_store() and semantic_search().
"""
from __future__ import annotations

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore

from config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL
from db.supabase_client import get_supabase

_embeddings: OpenAIEmbeddings | None = None
_vector_store: SupabaseVectorStore | None = None


def get_embeddings() -> OpenAIEmbeddings:
    global _embeddings
    if not _embeddings:
        _embeddings = OpenAIEmbeddings(
            model="openai/text-embedding-3-small",
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base=OPENROUTER_BASE_URL,
        )
    return _embeddings


def get_vector_store() -> SupabaseVectorStore | None:
    """Returns the shared SupabaseVectorStore, or None if Supabase is not configured."""
    global _vector_store
    if _vector_store:
        return _vector_store
    sb = get_supabase()
    if not sb:
        return None
    _vector_store = SupabaseVectorStore(
        client=sb,
        embedding=get_embeddings(),
        table_name="documents",
        query_name="match_documents",
    )
    return _vector_store


def semantic_search(query: str, k: int = 5) -> list[dict]:
    """
    Search the vector store for the most relevant code chunks.

    Returns a list of dicts with keys: file_path, content, similarity.
    """
    vs = get_vector_store()
    if not vs:
        return []

    try:
        results = vs.similarity_search_with_relevance_scores(query, k=k)
        output = []
        for doc, score in results:
            output.append({
                "file_path": doc.metadata.get("file_path", "unknown"),
                "content": doc.page_content,
                "similarity": round(score, 4),
            })
        return output
    except Exception as exc:
        print(f"[rag_service] semantic_search error: {exc}")
        return []
