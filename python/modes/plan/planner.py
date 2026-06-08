"""
modes/plan/planner.py — Generates a structured JSON plan using OpenAI structured outputs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ai.client import client, to_langchain_messages, to_openai_dict
from config import CODEBASE_PATH, LLM_DEFAULT_MODEL, LLM_API_KEY, LLM_BASE_URL
from modes.agent.executor import ToolExecutor
from modes.agent.tracker import ActionTracker
from modes.plan.web_tools import create_web_tools
from db.rag_service import semantic_search


@dataclass
class PlanStep:
    id: str
    title: str
    description: str
    hints: list[str]
    complexity: str  # "low" | "medium" | "high"


@dataclass
class Plan:
    goal: str
    research_summary: str
    steps: list[PlanStep]


def _build_readonly_tools(executor: ToolExecutor) -> tuple[list[dict], dict]:
    def _fmt_search(results: list[dict]) -> str:
        if not results:
            return "No relevant code snippets found."
        return "\n\n".join(
            f"Match #{i+1}: {r['file_path']} ({r['similarity']*100:.1f}%)\n```\n{r['content']}\n```"
            for i, r in enumerate(results)
        )

    schemas = [
        {"type": "function", "function": {"name": "semantic_search_codebase",
            "description": "Semantic search across the codebase.",
            "parameters": {"type": "object", "properties": {
                "query": {"type": "string"}, "k": {"type": "integer", "default": 5}},
                "required": ["query"]}}},
        {"type": "function", "function": {"name": "read_file",
            "description": "Read a workspace file.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
        {"type": "function", "function": {"name": "list_files",
            "description": "List files under a path.",
            "parameters": {"type": "object", "properties": {
                "path": {"type": "string"}, "recursive": {"type": "boolean", "default": False}},
                "required": ["path"]}}},
        {"type": "function", "function": {"name": "search_files",
            "description": "Glob file search.",
            "parameters": {"type": "object", "properties": {
                "root": {"type": "string"}, "pattern": {"type": "string"},
                "content_contains": {"type": "string"}}, "required": ["root", "pattern"]}}},
        {"type": "function", "function": {"name": "analyze_codebase",
            "description": "Summarise codebase structure.",
            "parameters": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}, "required": []}}},
    ]
    executors = {
        "semantic_search_codebase": lambda query, k=5: _fmt_search(semantic_search(query, k)),
        "read_file": executor.read_file,
        "list_files": executor.list_files,
        "search_files": executor.search_files,
        "analyze_codebase": executor.analyze_codebase,
    }
    return schemas, executors


PLAN_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "plan",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "research_summary": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                            "hints": {"type": "array", "items": {"type": "string"}},
                            "complexity": {"type": "string", "enum": ["low", "medium", "high"]},
                        },
                        "required": ["title", "description", "hints", "complexity"],
                        "additionalProperties": False,
                    },
                    "minItems": 1,
                    "maxItems": 15,
                },
            },
            "required": ["research_summary", "steps"],
            "additionalProperties": False,
        },
    },
}


def generate_plan(goal: str) -> Plan:
    tracker = ActionTracker()
    executor = ToolExecutor(tracker, CODEBASE_PATH)
    ro_schemas, ro_executors = _build_readonly_tools(executor)
    web_schemas, web_executors = create_web_tools()

    all_schemas = ro_schemas + web_schemas
    all_executors = {**ro_executors, **web_executors}

    system = (
        "You are a Plan-Mode planner. You DO NOT modify files. "
        f"Workspace: {CODEBASE_PATH}. "
        "Use read-only and web tools to research, then output a JSON plan matching this schema:\n"
        "{\n"
        "  \"research_summary\": \"string\",\n"
        "  \"steps\": [\n"
        "    {\n"
        "      \"title\": \"string\",\n"
        "      \"description\": \"string\",\n"
        "      \"hints\": [\"string\"],\n"
        "      \"complexity\": \"low\" | \"medium\" | \"high\"\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "Keep steps concise: 1–15 steps."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"User goal:\n{goal}"},
    ]

    # Bind response_format to json_object, and bind tools if defined
    llm = client.bind(response_format={"type": "json_object"})
    if all_schemas:
        llm = llm.bind_tools(all_schemas)

    max_steps = 20
    step = 0
    while step < max_steps:
        step += 1
        
        # Convert history to LangChain message objects
        lc_messages = to_langchain_messages(messages)
        
        # Invoke model
        response = llm.invoke(lc_messages)
        
        # Append assistant turn to history in OpenAI dict format
        msg_dict = to_openai_dict(response)
        messages.append(msg_dict)

        if not response.tool_calls:
            raw = response.content or "{}"
            data = json.loads(raw)
            steps = [
                PlanStep(
                    id=f"step-{i+1}",
                    title=s["title"],
                    description=s["description"],
                    hints=s.get("hints", []),
                    complexity=s.get("complexity", "medium"),
                )
                for i, s in enumerate(data.get("steps", []))
            ]
            return Plan(
                goal=goal,
                research_summary=data.get("research_summary", ""),
                steps=steps,
            )

        for tc in response.tool_calls:
            name = tc.get("name")
            args = tc.get("args") or {}
            tc_id = tc.get("id")
            
            fn = all_executors.get(name)
            result = fn(**args) if fn else f"[Unknown tool: {name}]"
            messages.append({"role": "tool", "tool_call_id": tc_id, "content": str(result)})

    return Plan(goal=goal, research_summary="", steps=[])
