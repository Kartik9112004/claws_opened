"""
config.py — Loads environment variables and exposes typed constants.
"""
import os
from dotenv import load_dotenv

# Load .env from the project root (one level up from python/)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_ROOT, ".env"))

# ── NVIDIA NIM (Primary LLM provider) ────────────────────────────────────────
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_DEFAULT_MODEL: str = os.getenv("NVIDIA_DEFAULT_MODEL", "meta/llama-3.3-70b-instruct")
NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"

# ── OpenRouter (fallback / used for embeddings) ───────────────────────────────
# OpenRouter is kept for RAG embeddings (openai/text-embedding-3-small, 1536-dim).
# If you migrate the vector DB to a NVIDIA embedding model, you can remove this.
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"

# ── Active LLM config (auto-resolved) ────────────────────────────────────────
# Uses NVIDIA if NVIDIA_API_KEY is set, otherwise falls back to OpenRouter.
if NVIDIA_API_KEY:
    LLM_API_KEY: str = NVIDIA_API_KEY
    LLM_BASE_URL: str = NVIDIA_BASE_URL
    LLM_DEFAULT_MODEL: str = NVIDIA_DEFAULT_MODEL
else:
    LLM_API_KEY = OPENROUTER_API_KEY
    LLM_BASE_URL = OPENROUTER_BASE_URL
    LLM_DEFAULT_MODEL = os.getenv("OPENROUTER_DEFAULT_MODEL", "openai/gpt-oss-120b")

# Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_OWNER_ID: int = int(os.getenv("TELEGRAM_OWNER_ID", "0"))

# Supabase
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# Firecrawl
FIRECRAWL_API_KEY: str = os.getenv("FIRECRAWL_API_KEY", "")

# Workspace
CODEBASE_PATH: str = os.getenv("CODEBASE_PATH") or _ROOT

# Skills
SKILLS_DIRS: list[str] = [
    s.strip()
    for s in os.getenv("SKILLS_DIRS", "").split(";")
    if s.strip()
]
