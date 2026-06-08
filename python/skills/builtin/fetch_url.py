"""
skills/builtin/fetch_url.py — Fetch the text content of a web URL.

This is a bundled example skill that ships with claws_opened.
The agent can call it to retrieve documentation, web pages, or raw files
from the internet without leaving the conversation.

Dependencies: requests (install via: pip install requests)
"""
from __future__ import annotations

SKILL_SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "fetch_url",
        "description": (
            "Fetch the text content of a web URL. "
            "Useful for reading documentation, GitHub raw files, or any public web page. "
            "Returns the plain-text body (HTML stripped when possible)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to fetch (must start with http:// or https://).",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default 4000).",
                    "default": 4000,
                },
            },
            "required": ["url"],
        },
    },
}


def run(url: str, max_chars: int = 4000) -> str:
    """Fetch a URL and return up to max_chars of its text content."""
    try:
        import requests  # soft dependency — only required when this skill is actually called
    except ImportError:
        return "[fetch_url] 'requests' is not installed. Run: pip install requests"

    if not url.startswith(("http://", "https://")):
        return f"[fetch_url] Invalid URL — must start with http:// or https://: {url}"

    try:
        response = requests.get(url, timeout=15, headers={"User-Agent": "claws_opened/1.0"})
        response.raise_for_status()
    except requests.exceptions.Timeout:
        return f"[fetch_url] Request timed out: {url}"
    except requests.exceptions.HTTPError as exc:
        return f"[fetch_url] HTTP error {exc.response.status_code}: {url}"
    except Exception as exc:  # noqa: BLE001
        return f"[fetch_url] Failed to fetch {url}: {exc}"

    content_type = response.headers.get("content-type", "")
    text = response.text

    # Strip HTML tags for cleaner output when the response is HTML
    if "html" in content_type:
        try:
            from html.parser import HTMLParser

            class _Stripper(HTMLParser):
                def __init__(self) -> None:
                    super().__init__()
                    self._parts: list[str] = []
                    self._skip = False

                def handle_starttag(self, tag: str, attrs: list) -> None:
                    if tag in ("script", "style", "head"):
                        self._skip = True

                def handle_endtag(self, tag: str) -> None:
                    if tag in ("script", "style", "head"):
                        self._skip = False

                def handle_data(self, data: str) -> None:
                    if not self._skip:
                        stripped = data.strip()
                        if stripped:
                            self._parts.append(stripped)

                def get_text(self) -> str:
                    return "\n".join(self._parts)

            stripper = _Stripper()
            stripper.feed(text)
            text = stripper.get_text()
        except Exception:  # noqa: BLE001
            pass  # fall back to raw text if parsing fails

    text = text[:max_chars]
    if len(response.text) > max_chars:
        text += f"\n\n... [truncated at {max_chars} chars]"

    return text
