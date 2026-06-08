"""
skills/loader.py — Auto-discovers and loads skill plugins.

Discovery order:
  1. python/skills/builtin/   — skills that ship with claws_opened
  2. Directories listed in SKILLS_DIRS (semicolon-separated env var)

Skill contract
--------------
Each skill file must export:
  SKILL_SCHEMA : dict   — OpenAI function tool schema
  run          : callable(**kwargs) -> str   — skill implementation

Skills that fail validation are skipped with a warning; they never crash the app.
Core built-in tool names always win over user skills with the same name.
"""
from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import Callable

from config import SKILLS_DIRS

logger = logging.getLogger(__name__)

# Directory that contains the bundled skills shipped with this project
_BUILTIN_DIR = Path(__file__).parent / "builtin"


def _load_skill_file(path: Path) -> tuple[dict, Callable] | None:
    """
    Import a single skill file and return (schema, run_fn).
    Returns None if the file is invalid.
    """
    try:
        spec = importlib.util.spec_from_file_location(path.stem, path)
        if spec is None or spec.loader is None:
            logger.warning("skills: cannot create spec for %s — skipping", path)
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[attr-defined]

        schema = getattr(module, "SKILL_SCHEMA", None)
        run_fn = getattr(module, "run", None)

        if not isinstance(schema, dict):
            logger.warning("skills: %s missing SKILL_SCHEMA dict — skipping", path.name)
            return None
        if not callable(run_fn):
            logger.warning("skills: %s missing callable 'run' — skipping", path.name)
            return None

        # Validate schema has the minimum required shape
        fn_def = schema.get("function", {})
        if not fn_def.get("name"):
            logger.warning("skills: %s SKILL_SCHEMA missing function.name — skipping", path.name)
            return None

        return schema, run_fn

    except Exception as exc:  # noqa: BLE001
        logger.warning("skills: error loading %s: %s — skipping", path.name, exc)
        return None


def load_skills(
    core_tool_names: set[str] | None = None,
) -> tuple[list[dict], dict[str, Callable]]:
    """
    Discover and load all skills from builtin + user-defined directories.

    Args:
        core_tool_names: Names of existing core tools. Skills with conflicting
                         names are skipped so core tools always win.

    Returns:
        (skill_schemas, skill_executors)
    """
    reserved = core_tool_names or set()
    skill_schemas: list[dict] = []
    skill_executors: dict[str, Callable] = {}
    seen_names: set[str] = set()

    # Walk builtin directory first, then user-defined SKILLS_DIRS
    search_dirs: list[Path] = [_BUILTIN_DIR]
    for d in SKILLS_DIRS:
        p = Path(d)
        if p.is_dir():
            search_dirs.append(p)
        else:
            logger.warning("skills: SKILLS_DIRS entry '%s' is not a directory — skipping", d)

    for directory in search_dirs:
        if not directory.is_dir():
            continue
        for skill_file in sorted(directory.glob("*.py")):
            if skill_file.name.startswith("_"):
                continue  # skip __init__.py and private files

            result = _load_skill_file(skill_file)
            if result is None:
                continue

            schema, run_fn = result
            name: str = schema["function"]["name"]

            if name in reserved:
                logger.warning(
                    "skills: '%s' conflicts with a core tool — skipping %s",
                    name,
                    skill_file.name,
                )
                continue

            if name in seen_names:
                logger.warning(
                    "skills: duplicate skill name '%s' in %s — skipping",
                    name,
                    skill_file.name,
                )
                continue

            skill_schemas.append(schema)
            skill_executors[name] = run_fn
            seen_names.add(name)
            logger.debug("skills: loaded '%s' from %s", name, skill_file)

    if skill_schemas:
        logger.info("skills: loaded %d skill(s): %s", len(skill_schemas), sorted(seen_names))

    return skill_schemas, skill_executors
