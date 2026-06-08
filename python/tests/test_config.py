"""
tests/test_config.py — Tests for config.py environment variable resolution.
Uses monkeypatch to avoid touching the real .env file.
"""
from __future__ import annotations

import importlib
import sys
import pytest


def _reload_config(monkeypatch, env_vars: dict) -> object:
    """
    Re-import config with a fresh environment to test resolution logic.
    We patch os.environ before import so load_dotenv doesn't interfere.
    """
    # Clear any cached config module
    for mod_name in list(sys.modules.keys()):
        if mod_name in ("config",):
            del sys.modules[mod_name]

    # Patch the env
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    # Patch load_dotenv to be a no-op (avoid reading the real .env)
    import unittest.mock as mock
    with mock.patch("dotenv.load_dotenv"):
        config = importlib.import_module("config")

    return config


class TestLLMResolution:
    def test_nvidia_key_selects_nvidia_config(self, monkeypatch):
        config = _reload_config(monkeypatch, {
            "NVIDIA_API_KEY": "nv-test-key",
            "OPENROUTER_API_KEY": "or-test-key",
        })
        assert config.LLM_API_KEY == "nv-test-key"
        assert "nvidia" in config.LLM_BASE_URL
        assert config.LLM_DEFAULT_MODEL == config.NVIDIA_DEFAULT_MODEL

    def test_missing_nvidia_falls_back_to_openrouter(self, monkeypatch):
        config = _reload_config(monkeypatch, {
            "NVIDIA_API_KEY": "",
            "OPENROUTER_API_KEY": "or-test-key",
        })
        assert config.LLM_API_KEY == "or-test-key"
        assert "openrouter" in config.LLM_BASE_URL

    def test_custom_openrouter_model_is_respected(self, monkeypatch):
        config = _reload_config(monkeypatch, {
            "NVIDIA_API_KEY": "",
            "OPENROUTER_API_KEY": "or-key",
            "OPENROUTER_DEFAULT_MODEL": "anthropic/claude-3-haiku",
        })
        assert config.LLM_DEFAULT_MODEL == "anthropic/claude-3-haiku"

    def test_custom_nvidia_model_is_respected(self, monkeypatch):
        config = _reload_config(monkeypatch, {
            "NVIDIA_API_KEY": "nv-key",
            "NVIDIA_DEFAULT_MODEL": "nvidia/llama-3.1-nemotron-70b-instruct",
        })
        assert config.LLM_DEFAULT_MODEL == "nvidia/llama-3.1-nemotron-70b-instruct"


class TestCodebasePath:
    def test_codebase_path_defaults_to_project_root(self, monkeypatch):
        config = _reload_config(monkeypatch, {"CODEBASE_PATH": ""})
        # Should default to the project root (parent of python/)
        assert config.CODEBASE_PATH != ""
        assert "claws_opened" in config.CODEBASE_PATH

    def test_codebase_path_can_be_overridden(self, monkeypatch):
        config = _reload_config(monkeypatch, {"CODEBASE_PATH": "/tmp/my_workspace"})
        assert config.CODEBASE_PATH == "/tmp/my_workspace"


class TestSkillsDirs:
    def test_skills_dirs_empty_by_default(self, monkeypatch):
        config = _reload_config(monkeypatch, {"SKILLS_DIRS": ""})
        assert config.SKILLS_DIRS == []

    def test_skills_dirs_single_path(self, monkeypatch):
        config = _reload_config(monkeypatch, {"SKILLS_DIRS": "/tmp/skills"})
        assert config.SKILLS_DIRS == ["/tmp/skills"]

    def test_skills_dirs_multiple_semicolon_separated(self, monkeypatch):
        config = _reload_config(monkeypatch, {"SKILLS_DIRS": "/a/b;/c/d; /e/f "})
        assert config.SKILLS_DIRS == ["/a/b", "/c/d", "/e/f"]
