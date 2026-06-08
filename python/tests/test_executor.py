"""
tests/test_executor.py — Unit tests for the staged filesystem ToolExecutor.
Tests run entirely in memory using tmp_path; no real Supabase or LLM calls.
"""
from __future__ import annotations

import os
import pytest

from modes.agent.tracker import ActionTracker
from modes.agent.executor import ToolExecutor


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def workspace(tmp_path):
    """Creates a temporary workspace directory with some seed files."""
    (tmp_path / "hello.py").write_text("print('hello')")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "utils.py").write_text("# utils")
    return tmp_path


@pytest.fixture()
def executor(workspace):
    tracker = ActionTracker()
    return ToolExecutor(tracker, str(workspace))


# ── read_file ─────────────────────────────────────────────────────────────────

class TestReadFile:
    def test_reads_existing_file(self, executor):
        content = executor.read_file("hello.py")
        assert "print('hello')" in content

    def test_reads_nested_file(self, executor):
        content = executor.read_file("src/utils.py")
        assert "# utils" in content

    def test_raises_for_missing_file(self, executor):
        with pytest.raises(FileNotFoundError):
            executor.read_file("does_not_exist.py")

    def test_raises_for_excluded_path(self, executor, workspace):
        (workspace / "__pycache__").mkdir()
        (workspace / "__pycache__" / "mod.pyc").write_text("bytecode")
        with pytest.raises(ValueError, match="excluded"):
            executor.read_file("__pycache__/mod.pyc")


# ── create_file ───────────────────────────────────────────────────────────────

class TestCreateFile:
    def test_stages_new_file(self, executor):
        result = executor.create_file("new.py", "x = 1")
        assert "Staged" in result
        # File not on disk yet
        assert not os.path.exists(os.path.join(executor.codebase_path, "new.py"))

    def test_staged_content_readable_via_overlay(self, executor):
        executor.create_file("staged.py", "y = 2")
        # read_file should see the staged overlay
        assert executor.read_file("staged.py") == "y = 2"

    def test_raises_if_file_already_exists(self, executor):
        with pytest.raises(FileExistsError):
            executor.create_file("hello.py", "duplicate")

    def test_external_absolute_path_is_staged(self, executor, tmp_path):
        external = str(tmp_path.parent / "external_file.py")
        result = executor.create_file(external, "# external")
        assert "external" in result.lower()


# ── modify_file ───────────────────────────────────────────────────────────────

class TestModifyFile:
    def test_stages_modification(self, executor):
        result = executor.modify_file("hello.py", "# replaced")
        assert "Staged" in result

    def test_overlay_reflects_modification(self, executor):
        executor.modify_file("hello.py", "# replaced")
        assert executor.read_file("hello.py") == "# replaced"

    def test_raises_for_nonexistent_file(self, executor):
        with pytest.raises(FileNotFoundError):
            executor.modify_file("ghost.py", "content")


# ── delete_file ───────────────────────────────────────────────────────────────

class TestDeleteFile:
    def test_stages_deletion(self, executor):
        result = executor.delete_file("hello.py")
        assert "Staged" in result

    def test_deleted_file_not_readable(self, executor):
        executor.delete_file("hello.py")
        with pytest.raises(FileNotFoundError):
            executor.read_file("hello.py")

    def test_raises_for_nonexistent_file(self, executor):
        with pytest.raises(FileNotFoundError):
            executor.delete_file("ghost.py")


# ── create_folder ─────────────────────────────────────────────────────────────

class TestCreateFolder:
    def test_stages_new_folder(self, executor, workspace):
        result = executor.create_folder("new_dir")
        assert "Staged" in result

    def test_deduplication_returns_message(self, executor, workspace):
        executor.create_folder("new_dir")
        result2 = executor.create_folder("new_dir")
        assert "already" in result2.lower()

    def test_existing_dir_returns_already_exists_message(self, executor):
        result = executor.create_folder("src")
        assert "already" in result.lower()


# ── list_files ────────────────────────────────────────────────────────────────

class TestListFiles:
    def test_lists_root(self, executor):
        listing = executor.list_files(".")
        assert "hello.py" in listing

    def test_recursive_lists_nested(self, executor):
        listing = executor.list_files(".", recursive=True)
        assert "src/utils.py" in listing

    def test_raises_for_missing_path(self, executor):
        with pytest.raises(FileNotFoundError):
            executor.list_files("nonexistent_dir")


# ── clear_staging ─────────────────────────────────────────────────────────────

class TestClearStaging:
    def test_clears_overlay_and_folders(self, executor):
        executor.create_file("temp.py", "data")
        executor.create_folder("temp_dir")
        executor.clear_staging()
        # After clearing, staged file should no longer be in the overlay
        with pytest.raises(FileNotFoundError):
            executor.read_file("temp.py")


# ── apply_approved ────────────────────────────────────────────────────────────

class TestApplyApproved:
    def test_applies_file_creation(self, executor, workspace):
        executor.create_file("applied.py", "# applied")
        # Approve all pending actions
        for action in executor.tracker.get_actions():
            action.status = "approved"
        errors = executor.apply_approved()
        assert errors == []
        assert (workspace / "applied.py").read_text() == "# applied"

    def test_applies_file_deletion(self, executor, workspace):
        executor.delete_file("hello.py")
        for action in executor.tracker.get_actions():
            action.status = "approved"
        errors = executor.apply_approved()
        assert errors == []
        assert not (workspace / "hello.py").exists()

    def test_applies_folder_creation(self, executor, workspace):
        executor.create_folder("brand_new_dir")
        for action in executor.tracker.get_actions():
            action.status = "approved"
        errors = executor.apply_approved()
        assert errors == []
        assert (workspace / "brand_new_dir").is_dir()
