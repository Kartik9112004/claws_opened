"""
tests/test_session_store.py — Unit tests for Supabase session_store helpers.
Uses pytest-mock to stub the Supabase client — no real DB calls.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


def _make_mock_supabase(data=None, error=None):
    """Build a mock Supabase client whose table/select/insert chain returns data."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = data or []

    # Chain: .table().select().eq().order().execute()
    mock_table = MagicMock()
    mock_table.select.return_value = mock_table
    mock_table.eq.return_value = mock_table
    mock_table.order.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.upsert.return_value = mock_table
    mock_table.execute.return_value = mock_response

    mock_client.table.return_value = mock_table
    return mock_client, mock_table, mock_response


# ── load_chat_history ─────────────────────────────────────────────────────────

class TestLoadChatHistory:
    def test_returns_messages_when_supabase_configured(self):
        mock_data = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]
        mock_client, _, _ = _make_mock_supabase(data=mock_data)

        with patch("db.session_store.get_supabase", return_value=mock_client):
            from db.session_store import load_chat_history
            result = load_chat_history("test-chat-id")

        assert len(result) == 2
        assert result[0] == {"role": "user", "content": "hello"}
        assert result[1] == {"role": "assistant", "content": "hi there"}

    def test_returns_empty_list_when_supabase_not_configured(self):
        with patch("db.session_store.get_supabase", return_value=None):
            from db.session_store import load_chat_history
            result = load_chat_history("any-chat-id")
        assert result == []

    def test_returns_empty_list_on_exception(self):
        mock_client = MagicMock()
        mock_client.table.side_effect = RuntimeError("connection refused")

        with patch("db.session_store.get_supabase", return_value=mock_client):
            from db.session_store import load_chat_history
            result = load_chat_history("chat-id")
        assert result == []


# ── save_message ──────────────────────────────────────────────────────────────

class TestSaveMessage:
    def test_calls_upsert_and_insert(self):
        mock_client, mock_table, _ = _make_mock_supabase()

        with patch("db.session_store.get_supabase", return_value=mock_client):
            from db.session_store import save_message
            save_message("chat-123", "user", "Hello world", "My Chat")

        # Should have called table() at least twice (chats upsert + messages insert)
        assert mock_client.table.call_count >= 2

    def test_does_nothing_when_supabase_not_configured(self):
        with patch("db.session_store.get_supabase", return_value=None):
            from db.session_store import save_message
            # Should not raise
            save_message("chat-id", "user", "hello")

    def test_handles_exception_gracefully(self):
        mock_client = MagicMock()
        mock_client.table.side_effect = Exception("DB error")

        with patch("db.session_store.get_supabase", return_value=mock_client):
            from db.session_store import save_message
            # Should not raise — errors are swallowed with a print
            save_message("chat-id", "user", "hello")


# ── list_chats ────────────────────────────────────────────────────────────────

class TestListChats:
    def test_returns_chat_list(self):
        mock_data = [
            {"id": "uuid-1", "name": "Sprint Planning"},
            {"id": "uuid-2", "name": None},  # name may be None
        ]
        mock_client, _, _ = _make_mock_supabase(data=mock_data)

        with patch("db.session_store.get_supabase", return_value=mock_client):
            from db.session_store import list_chats
            result = list_chats()

        assert len(result) == 2
        assert result[0]["id"] == "uuid-1"
        assert result[0]["name"] == "Sprint Planning"
        # Fallback: name=None should return id as name
        assert result[1]["name"] == "uuid-2"

    def test_returns_empty_when_no_supabase(self):
        with patch("db.session_store.get_supabase", return_value=None):
            from db.session_store import list_chats
            result = list_chats()
        assert result == []


# ── create_chat ───────────────────────────────────────────────────────────────

class TestCreateChat:
    def test_upserts_chat(self):
        mock_client, mock_table, _ = _make_mock_supabase()

        with patch("db.session_store.get_supabase", return_value=mock_client):
            from db.session_store import create_chat
            create_chat("my-uuid", "My Chat")

        mock_client.table.assert_called_with("chats")
        mock_table.upsert.assert_called_once_with({"id": "my-uuid", "name": "My Chat"})

    def test_does_nothing_when_no_supabase(self):
        with patch("db.session_store.get_supabase", return_value=None):
            from db.session_store import create_chat
            create_chat("id", "name")  # Should not raise
