# Skills — Writing Custom Agent Plugins

Skills are Python files you drop into any directory to extend the agent with new tools — no core code changes required.

---

## Quick Start

1. Create a `.py` file anywhere on your machine.
2. Point the agent to it by adding that directory to `SKILLS_DIRS` in your `.env`:

```env
# Semicolon-separated list of directories containing your custom skills
SKILLS_DIRS=/Users/you/my_skills
```

3. Restart the agent — your skill is automatically available.

---

## Skill File Contract

Every skill file must export exactly two things:

```python
# my_skill.py

SKILL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "my_skill_name",          # unique name the agent calls
        "description": "What it does.",   # shown to the LLM — be descriptive
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "What param1 is for.",
                },
                # ... more parameters
            },
            "required": ["param1"],       # which params are mandatory
        },
    },
}


def run(param1: str, **kwargs) -> str:
    """Implementation. Must return a string."""
    return f"You called my_skill with: {param1}"
```

### Rules

| Rule | Detail |
|------|--------|
| File name | Any `.py` file that does **not** start with `_` |
| Required exports | `SKILL_SCHEMA` (dict) + `run` (callable) |
| `run` return type | Must return `str` — the agent reads it as tool output |
| Naming conflicts | Core tool names always win; duplicates are skipped with a warning |
| Load errors | Bad skills are skipped gracefully — they never crash the app |

---

## Full Example — `summarise_text.py`

```python
"""Summarise a block of text using a simple heuristic (no API call needed)."""

SKILL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "summarise_text",
        "description": "Return the first N sentences of a long block of text as a summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text to summarise."},
                "sentences": {
                    "type": "integer",
                    "description": "Number of sentences to keep (default 3).",
                    "default": 3,
                },
            },
            "required": ["text"],
        },
    },
}


def run(text: str, sentences: int = 3) -> str:
    import re
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:sentences])
```

---

## Bundled Skills

The following skills ship with `claws_opened` and are always available:

| Skill | Description |
|-------|-------------|
| `fetch_url` | Fetch the text content of any public web URL |

---

## Tips

- Use `print()` or `logging` inside `run()` freely — output goes to the terminal, not to the agent.
- You can import any installed package inside `run()`. Heavy imports (e.g. `torch`) should be done inside the function, not at module level, so startup stays fast.
- Skills are loaded once at agent startup. Restart the agent after adding/modifying a skill file.
