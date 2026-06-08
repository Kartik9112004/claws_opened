# Claws Opened

A coding agent that runs in your terminal (or Telegram). You give it a task, it reads your codebase, proposes file changes, and you approve or reject them before anything gets written to disk.

Built in Python using LangChain. Uses OpenRouter or NVIDIA NIM as the LLM backend and Supabase for vector search and chat history.

---

## What it can do

- **Agent mode** — give it a task, it figures out what files to change and shows you a diff before applying
- **Ask mode** — ask questions about your codebase, it reads the actual files to answer
- **Plan mode** — give it a goal, it breaks it into steps and executes them one at a time
- **Telegram bot** — same agent and ask modes but over Telegram, so you can use it from your phone
- **RAG / semantic search** — indexes your codebase into Supabase so the agent can search by meaning, not just file names
- **Plugin system** — drop a `.py` file into a folder, the agent picks it up as a new tool automatically

---

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/Kartik9112004/claws_opened.git
cd claws_opened
```

### 2. Create a Python environment

```bash
conda create -n claws python=3.11
conda activate claws
pip install -r python/requirements.txt
```

### 3. Set up your `.env`

```bash
cp .env.example .env
```

Then fill in the values. At minimum you need:
- `OPENROUTER_API_KEY` — get one from [openrouter.ai](https://openrouter.ai)
- `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` — for RAG and chat history

If you have an NVIDIA API key, set `NVIDIA_API_KEY` and the agent will use that instead of OpenRouter.

### 4. Run it

```bash
cd python
python main.py wakeup     # interactive mode picker
python main.py agent      # jump straight to agent mode
python main.py ask        # jump straight to ask mode
python main.py telegram   # start the Telegram bot
```

### 5. Index your codebase (for semantic search)

```bash
python main.py index
```

This runs once and chunks your code into Supabase. After that, the agent can search your codebase by meaning.

---

## Adding custom tools (skills)

Create a `.py` file anywhere, add its directory to `SKILLS_DIRS` in your `.env`, and the agent will load it automatically on next start.

See [python/skills/README.md](python/skills/README.md) for the full guide and an example.

---

## Running tests

```bash
cd python
pytest tests/ -v
```

54 tests covering the file executor, skill loader, config resolution, and Supabase session store.

---

## Running with Docker

```bash
docker compose up --build
```

This starts the Telegram bot inside a container. Mount your workspace directory in `docker-compose.yml` if you want the agent to manage files outside the repo.

---

## LangSmith tracing (optional)

If you want to see every LLM call traced (latency, tokens, tool calls), sign up at [smith.langchain.com](https://smith.langchain.com) and add to your `.env`:

```env
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_key_here
LANGCHAIN_PROJECT=claws_opened
```

---

## Project layout

```
python/
  main.py           # CLI entrypoint
  config.py         # env var loading
  ai/client.py      # LangChain LLM client and tool loop
  db/               # Supabase client, RAG indexer, session store
  modes/
    agent/          # agent mode — executor, tracker, tools, approval flow
    ask/            # ask mode — read-only multi-turn chat
    plan/           # plan mode — goal → steps → execute
    telegram_bot/   # Telegram bot handlers and callbacks
  skills/           # plugin system — drop a .py file to add a tool
    builtin/        # bundled skills (fetch_url)
  tests/            # pytest tests
  tui/              # terminal rendering helpers
```

---

## Stack

- Python 3.11
- LangChain + LangChain-OpenAI
- OpenRouter / NVIDIA NIM (LLM)
- Supabase (vector store + chat history)
- python-telegram-bot
- Firecrawl (web scraping tool)
- Docker + GitHub Actions (CI/CD)