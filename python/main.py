#!/usr/bin/env python3
"""
main.py — Claws Opened CLI entrypoint.

Usage:
    python main.py wakeup           # Banner + interactive mode picker
    python main.py agent            # Run Agent Mode directly
    python main.py plan             # Run Plan Mode directly
    python main.py ask              # Run Ask Mode directly
    python main.py telegram         # Start Telegram bot directly
    python main.py index            # Index codebase into vector database
    python main.py search <query>   # Semantic search query
    python main.py migrate          # Create match_documents DB function
"""
import argparse
import sys
import os

# Ensure the python/ directory is on sys.path so all imports resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="claws_opened",
        description="Claws Opened — Agentic coding assistant",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("wakeup", help="Show banner and interactive mode picker")
    subparsers.add_parser("agent", help="Run Agent Mode directly")
    subparsers.add_parser("plan", help="Run Plan Mode directly")
    subparsers.add_parser("ask", help="Run Ask Mode directly")
    subparsers.add_parser("telegram", help="Start Telegram bot directly")
    subparsers.add_parser("index", help="Index codebase into vector database")
    subparsers.add_parser("migrate", help="Run database migration (match_documents function)")

    search_parser = subparsers.add_parser("search", help="Semantic search query")
    search_parser.add_argument("query", nargs="+", help="Search query text")

    args = parser.parse_args()

    if args.command == "wakeup":
        from tui.wakeup import run_wakeup
        run_wakeup()

    elif args.command == "agent":
        from modes.agent.orchestrator import run_agent_mode
        run_agent_mode()

    elif args.command == "plan":
        from modes.plan.orchestrator import run_plan_mode
        run_plan_mode()

    elif args.command == "ask":
        from modes.ask.orchestrator import run_ask_mode
        run_ask_mode()

    elif args.command == "telegram":
        from modes.telegram_bot.bot import run_telegram_mode
        run_telegram_mode()

    elif args.command == "index":
        from config import CODEBASE_PATH
        from db.rag_indexer import index_codebase
        index_codebase(CODEBASE_PATH)

    elif args.command == "migrate":
        from db.migrate import run_migration
        run_migration()

    elif args.command == "search":
        query = " ".join(args.query)
        print(f'\n🔍 Searching for: "{query}"...\n')
        from db.rag_service import semantic_search
        results = semantic_search(query)
        if not results:
            print("❌ No relevant code chunks found.")
        else:
            for i, r in enumerate(results, 1):
                print(f"\033[32m[Match #{i}] File: {r['file_path']} (Similarity: {r['similarity']*100:.1f}%)\033[0m")
                print("-" * 60)
                print(r["content"])
                print("-" * 60 + "\n")


if __name__ == "__main__":
    main()
