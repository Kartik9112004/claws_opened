"""
modes/agent/tools.py — OpenAI tool schemas + executor dispatch for Agent Mode.
"""
from __future__ import annotations

from typing import Callable

from db.rag_service import semantic_search
from modes.agent.executor import ToolExecutor


def _fmt_search(results: list[dict]) -> str:
    if not results:
        return "No relevant code snippets found."
    return "\n\n".join(
        f"Match #{i+1} in File: {r['file_path']} (Similarity: {r['similarity']*100:.1f}%)\n```\n{r['content']}\n```"
        for i, r in enumerate(results)
    )


def create_agent_tools(executor: ToolExecutor) -> tuple[list[dict], dict[str, Callable]]:
    """
    Returns:
        (tool_schemas, tool_executors)
        - tool_schemas: list of OpenAI-format tool dicts.
        - tool_executors: dict mapping tool_name → callable(**args) → str.
    """
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "semantic_search_codebase",
                "description": (
                    "Semantically search the codebase using vector embeddings. "
                    "Use natural language — returns the most relevant code chunks."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Natural language search query"},
                        "k": {"type": "integer", "description": "Number of results (1–10)", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a text file from the workspace (relative path).",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_file",
                "description": "Stage creation of a new file (not written until approved).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "modify_file",
                "description": "Stage a full-file replacement for an existing file (pending approval).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string", "description": "Complete new file contents"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "delete_file",
                "description": "Stage deletion of a file (pending approval).",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "create_folder",
                "description": "Stage creation of a directory (pending approval).",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories under a path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "recursive": {"type": "boolean", "default": False},
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Find files by glob pattern, with optional content substring filter.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "root": {"type": "string"},
                        "pattern": {"type": "string"},
                        "content_contains": {"type": "string"},
                    },
                    "required": ["root", "pattern"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "analyze_codebase",
                "description": "Summarise codebase structure: file/dir counts.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string", "default": "."}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_shell",
                "description": "Queue a shell command to run in the workspace after user approval.",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        },
    ]

    executors: dict[str, Callable] = {
        "semantic_search_codebase": lambda query, k=5: _fmt_search(semantic_search(query, k)),
        "read_file": executor.read_file,
        "create_file": executor.create_file,
        "modify_file": executor.modify_file,
        "delete_file": executor.delete_file,
        "create_folder": executor.create_folder,
        "list_files": executor.list_files,
        "search_files": executor.search_files,
        "analyze_codebase": executor.analyze_codebase,
        "execute_shell": executor.queue_shell,
    }

    return schemas, executors
