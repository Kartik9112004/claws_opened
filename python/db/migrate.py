"""
db/migrate.py — Creates the match_documents SQL function required by LangChain's
SupabaseVectorStore. Run this once before using semantic search.

Usage:
    python python/db/migrate.py
"""
from __future__ import annotations

from db.supabase_client import get_supabase


CREATE_DOCUMENTS_TABLE_SQL = """
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Create the documents table
CREATE TABLE IF NOT EXISTS documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  content text,
  metadata jsonb,
  embedding vector(1536)
);
"""

# LangChain's SupabaseVectorStore expects a match_documents RPC with this signature.
MATCH_DOCUMENTS_SQL = """
CREATE OR REPLACE FUNCTION match_documents (
  query_embedding vector(1536),
  match_count      int DEFAULT 5,
  filter           jsonb DEFAULT '{}'
)
RETURNS TABLE (
  id         uuid,
  content    text,
  metadata   jsonb,
  embedding  vector(1536),
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    d.id,
    d.content,
    d.metadata,
    d.embedding,
    1 - (d.embedding <=> query_embedding) AS similarity
  FROM documents d
  WHERE d.metadata @> filter
  ORDER BY d.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
"""


def run_migration() -> None:
    sb = get_supabase()
    if not sb:
        print("❌ Supabase is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return

    print("🔄 Running migration: creating match_documents function...")
    try:
        # Use rpc to execute raw SQL via the sql() helper
        sb.rpc("query", {"query_text": MATCH_DOCUMENTS_SQL}).execute()
        print("✅ match_documents function created/updated successfully!")
    except Exception:
        # Many Supabase setups expose a pg_execute or raw SQL endpoint.
        # Fallback: print the SQL and instruct manual execution.
        print("\n⚠️  Could not auto-execute migration via RPC.")
        print("Please run the following SQL in your Supabase SQL Editor:\n")
        print(CREATE_DOCUMENTS_TABLE_SQL)
        print(MATCH_DOCUMENTS_SQL)
        print("\n👉 Go to: https://supabase.com/dashboard → SQL Editor → Paste and run.")


if __name__ == "__main__":
    run_migration()
