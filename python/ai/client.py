"""
ai/client.py — Shared LangChain ChatOpenAI client.
Automatically points at NVIDIA NIM when NVIDIA_API_KEY is set,
otherwise falls back to OpenRouter.
"""
from __future__ import annotations

import json
from typing import Any, Callable

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, ToolMessage, SystemMessage, HumanMessage, BaseMessage

from config import LLM_API_KEY, LLM_BASE_URL, LLM_DEFAULT_MODEL

# Single shared client — wired to NVIDIA or OpenRouter depending on .env
client = ChatOpenAI(
    model=LLM_DEFAULT_MODEL,
    temperature=0.2,
    max_retries=3,
    openai_api_key=LLM_API_KEY,
    openai_api_base=LLM_BASE_URL,
)


def to_langchain_messages(messages: list[dict]) -> list[BaseMessage]:
    """
    Converts standard OpenAI message dictionaries to LangChain message objects.
    """
    lc_messages = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if role == "system":
            lc_messages.append(SystemMessage(content=content))
        elif role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            tc_list = m.get("tool_calls")
            lc_tc = []
            if tc_list:
                for tc in tc_list:
                    tc_id = tc.get("id")
                    fn = tc.get("function", {})
                    name = fn.get("name")
                    raw_args = fn.get("arguments", "{}")
                    try:
                        args = json.loads(raw_args)
                    except Exception:
                        args = {}
                    lc_tc.append({
                        "name": name,
                        "args": args,
                        "id": tc_id,
                        "type": "tool_call"
                    })
            lc_messages.append(AIMessage(content=content or "", tool_calls=lc_tc))
        elif role == "tool":
            lc_messages.append(ToolMessage(content=content or "", tool_call_id=m.get("tool_call_id")))
    return lc_messages


def to_openai_dict(response: AIMessage) -> dict:
    """
    Converts a LangChain AIMessage response back to an OpenAI message dictionary format.
    """
    ai_msg_dict: dict[str, Any] = {
        "role": "assistant",
    }
    if response.content:
        ai_msg_dict["content"] = response.content
    else:
        ai_msg_dict["content"] = None

    if response.tool_calls:
        openai_tc = []
        for tc in response.tool_calls:
            openai_tc.append({
                "id": tc.get("id"),
                "type": "function",
                "function": {
                    "name": tc.get("name"),
                    "arguments": json.dumps(tc.get("args") or {})
                }
            })
        ai_msg_dict["tool_calls"] = openai_tc
    return ai_msg_dict


def run_tool_loop(
    messages: list[dict],
    tools: list[dict],
    tool_executors: dict[str, Callable[..., str]],
    model: str = LLM_DEFAULT_MODEL,
    max_steps: int = 40,
    on_tool_call: Callable[[str, dict], None] | None = None,
) -> tuple[str, list[dict]]:
    """
    Runs the LangChain ChatOpenAI tool calling loop.

    Args:
        messages:       Conversation history to send (as OpenAI dicts).
        tools:          OpenAI tool schema list.
        tool_executors: Dict mapping tool_name → callable(args_dict) → str result.
        model:          Model ID (via OpenRouter).
        max_steps:      Max iterations before forced stop.
        on_tool_call:   Optional callback(tool_name, args) for progress reporting.

    Returns:
        (final_text, updated_messages)
    """
    steps = 0

    # Initialize model instance for this loop run
    llm = ChatOpenAI(
        model=model,
        temperature=0.2,
        max_retries=3,
        openai_api_key=LLM_API_KEY,
        openai_api_base=LLM_BASE_URL,
    )

    if tools:
        llm = llm.bind_tools(tools)

    while steps < max_steps:
        steps += 1

        # Convert history to LangChain message objects
        lc_messages = to_langchain_messages(messages)

        # Invoke model
        response = llm.invoke(lc_messages)

        # Append assistant turn to history in OpenAI dict format
        msg_dict = to_openai_dict(response)
        messages.append(msg_dict)

        if not response.tool_calls:
            # Model is done
            return response.content or "", messages

        # Execute each tool call and collect results
        for tc in response.tool_calls:
            name = tc.get("name")
            args = tc.get("args") or {}
            tc_id = tc.get("id")

            if on_tool_call:
                on_tool_call(name, args)

            executor = tool_executors.get(name)
            if executor:
                try:
                    result = executor(**args)
                except Exception as exc:
                    result = f"[Tool error] {exc}"
            else:
                result = f"[Unknown tool: {name}]"

            messages.append({
                "role": "tool",
                "tool_call_id": tc_id,
                "content": str(result),
            })

    return "", messages
