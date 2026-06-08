"""
tests/test_skill_loader.py — Unit tests for the plugin/skills auto-discovery system.
Uses tmp_path to create real skill files and validates the loader's behaviour.
"""
from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import patch

from skills.loader import load_skills, _load_skill_file


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_skill(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content)
    return path


VALID_SKILL = '''
SKILL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "test_skill",
        "description": "A test skill.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}

def run(**kwargs):
    return "test_skill_result"
'''

SKILL_NO_SCHEMA = '''
def run(**kwargs):
    return "ok"
'''

SKILL_NO_RUN = '''
SKILL_SCHEMA = {
    "type": "function",
    "function": {"name": "broken_skill", "description": "No run."},
}
'''

SKILL_MISSING_NAME = '''
SKILL_SCHEMA = {
    "type": "function",
    "function": {"name": "", "description": "Empty name."},
}

def run(**kwargs):
    return "ok"
'''

SKILL_SYNTAX_ERROR = '''
def run(**kwargs):
    return (  # unclosed paren
'''


# ── _load_skill_file ──────────────────────────────────────────────────────────

class TestLoadSkillFile:
    def test_loads_valid_skill(self, tmp_path):
        path = _write_skill(tmp_path, "valid.py", VALID_SKILL)
        result = _load_skill_file(path)
        assert result is not None
        schema, run_fn = result
        assert schema["function"]["name"] == "test_skill"
        assert run_fn() == "test_skill_result"

    def test_rejects_missing_schema(self, tmp_path):
        path = _write_skill(tmp_path, "no_schema.py", SKILL_NO_SCHEMA)
        assert _load_skill_file(path) is None

    def test_rejects_missing_run(self, tmp_path):
        path = _write_skill(tmp_path, "no_run.py", SKILL_NO_RUN)
        assert _load_skill_file(path) is None

    def test_rejects_empty_skill_name(self, tmp_path):
        path = _write_skill(tmp_path, "no_name.py", SKILL_MISSING_NAME)
        assert _load_skill_file(path) is None

    def test_rejects_syntax_error(self, tmp_path):
        path = _write_skill(tmp_path, "broken.py", SKILL_SYNTAX_ERROR)
        assert _load_skill_file(path) is None


# ── load_skills ───────────────────────────────────────────────────────────────

SKILL_A = '''
SKILL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "skill_a",
        "description": "Skill A",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
def run(**kwargs): return "a"
'''

SKILL_B = '''
SKILL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "skill_b",
        "description": "Skill B",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
def run(**kwargs): return "b"
'''

SKILL_CONFLICT = '''
SKILL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "read_file",   # conflicts with a core tool
        "description": "Would override read_file.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
def run(**kwargs): return "conflict"
'''

SKILL_DUPLICATE = '''
SKILL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "skill_a",   # same name as SKILL_A — second wins
        "description": "Duplicate A",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}
def run(**kwargs): return "a_duplicate"
'''


class TestLoadSkills:
    def _patch_builtin_dir(self, tmp_path):
        """Patch _BUILTIN_DIR so no real builtins are loaded during tests."""
        empty_builtin = tmp_path / "empty_builtin"
        empty_builtin.mkdir()
        return patch("skills.loader._BUILTIN_DIR", empty_builtin)

    def test_loads_skills_from_user_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "skill_a.py", SKILL_A)
        _write_skill(skills_dir, "skill_b.py", SKILL_B)

        with self._patch_builtin_dir(tmp_path):
            with patch("skills.loader.SKILLS_DIRS", [str(skills_dir)]):
                schemas, executors = load_skills()

        names = {s["function"]["name"] for s in schemas}
        assert "skill_a" in names
        assert "skill_b" in names
        assert executors["skill_a"]() == "a"
        assert executors["skill_b"]() == "b"

    def test_skips_private_files(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "_private.py", SKILL_A)  # starts with _

        with self._patch_builtin_dir(tmp_path):
            with patch("skills.loader.SKILLS_DIRS", [str(skills_dir)]):
                schemas, executors = load_skills()

        assert len(schemas) == 0

    def test_skips_conflicting_core_names(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "conflict.py", SKILL_CONFLICT)

        with self._patch_builtin_dir(tmp_path):
            with patch("skills.loader.SKILLS_DIRS", [str(skills_dir)]):
                schemas, executors = load_skills(core_tool_names={"read_file"})

        assert "read_file" not in executors

    def test_skips_duplicate_names(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        _write_skill(skills_dir, "a1_skill_a.py", SKILL_A)
        _write_skill(skills_dir, "a2_skill_a_dup.py", SKILL_DUPLICATE)

        with self._patch_builtin_dir(tmp_path):
            with patch("skills.loader.SKILLS_DIRS", [str(skills_dir)]):
                schemas, executors = load_skills()

        names = [s["function"]["name"] for s in schemas]
        assert names.count("skill_a") == 1  # only loaded once

    def test_ignores_nonexistent_skills_dir(self, tmp_path):
        with self._patch_builtin_dir(tmp_path):
            with patch("skills.loader.SKILLS_DIRS", ["/does/not/exist"]):
                schemas, executors = load_skills()
        assert schemas == []

    def test_returns_empty_when_no_skills(self, tmp_path):
        with self._patch_builtin_dir(tmp_path):
            with patch("skills.loader.SKILLS_DIRS", []):
                schemas, executors = load_skills()
        assert schemas == []
        assert executors == {}
