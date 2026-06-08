"""
modes/plan/web_tools.py — Firecrawl search and crawl tools for Plan Mode.
"""
from __future__ import annotations

from typing import Callable

from config import FIRECRAWL_API_KEY

_client = None


def _get_client():
    global _client
    if _client:
        return _client
    if not FIRECRAWL_API_KEY:
        return None
    from firecrawl import FirecrawlApp
    _client = FirecrawlApp(api_key=FIRECRAWL_API_KEY)
    return _client


def _clip(text: str, n: int = 8000) -> str:
    return text[:n] + "\n…[truncated]" if len(text) > n else text


def create_web_tools() -> tuple[list[dict], dict[str, Callable]]:
    """Returns (schemas, executors) for web tools. Empty if Firecrawl is not configured."""
    if not FIRECRAWL_API_KEY:
        return [], {}

    schemas = [
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web. Returns title/url/snippet list.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer", "default": 5},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "web_crawl",
                "description": "Scrape a URL and return its content as markdown.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
    ]

    def web_search(query: str, limit: int = 5) -> str:
        fc = _get_client()
        if not fc:
            return "(Firecrawl not configured)"
        res = fc.search(query, limit=limit)
        items = getattr(res, "data", res) or []
        lines = [
            f"{i+1}. {item.get('title','(untitled)')}\n   {item.get('url','')}\n   {item.get('snippet','')}"
            for i, item in enumerate(items[:limit])
        ]
        return _clip("\n\n".join(lines) or "(no results)")

    def web_crawl(url: str) -> str:
        fc = _get_client()
        if not fc:
            return "(Firecrawl not configured)"
        doc = fc.scrape_url(url, params={"formats": ["markdown"]})
        md = doc.get("markdown", "") if isinstance(doc, dict) else getattr(doc, "markdown", "")
        return _clip(md or "(empty)")

    executors = {"web_search": web_search, "web_crawl": web_crawl}
    return schemas, executors
