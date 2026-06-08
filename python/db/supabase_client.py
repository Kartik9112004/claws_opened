"""
db/supabase_client.py — Shared Supabase client singleton.
"""
from __future__ import annotations

from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY

_client: Client | None = None


def get_supabase() -> Client | None:
    """Returns the shared Supabase client, or None if credentials are missing."""
    global _client
    if _client:
        return _client
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return None
    _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _client
