"""
db/rag_indexer.py — Incremental codebase indexer using LangChain + SHA-256 hashing.

Usage:
    python python/main.py index
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from config import CODEBASE_PATH
from db.rag_service import get_vector_store
from db.supabase_client import get_supabase

# Directories to skip during crawl
EXCLUDE_DIRS = {
    "node_modules", ".git", "dist", "build", ".bun",
    "todo-app", "todo-list-app", "__pycache__", ".mypy_cache",
    ".venv", "venv", "env",
}

# Source file extensions to index
INCLUDE_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".json", ".md",
    ".css", ".html", ".yaml", ".yml", ".py", ".toml",
}

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
BATCH_SIZE = 40


def _compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).digest().hex()


def _walk_codebase(root: str) -> list[Path]:
    """Recursively collect indexable source files."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune excluded directories in-place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            if Path(fname).suffix.lower() in INCLUDE_EXTENSIONS:
                files.append(Path(dirpath) / fname)
    return files


def index_codebase(codebase_path: str = CODEBASE_PATH) -> None:
    vs = get_vector_store()
    sb = get_supabase()

    if not vs or not sb:
        print("❌ Vector store or Supabase client is not initialised.")
        return

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )

    print(f"\n🔍 Scanning codebase: {codebase_path}")
    all_files = _walk_codebase(codebase_path)
    print(f"📂 Found {len(all_files)} source files to check.\n")

    pending_docs: list[Document] = []
    skipped = 0
    updated = 0

    for fp in all_files:
        rel_path = str(fp.relative_to(codebase_path))
        try:
            content = fp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        file_hash = _compute_hash(content)

        # Incremental check: skip if file hash already exists in documents table
        try:
            existing = (
                sb.table("documents")
                .select("id")
                .eq("metadata->>file_path", rel_path)
                .eq("metadata->>file_hash", file_hash)
                .limit(1)
                .execute()
            )
            if existing.data:
                skipped += 1
                continue
        except Exception:
            pass  # If check fails, reindex anyway

        # Delete old chunks for this file before reinserting
        try:
            sb.table("documents").delete().eq("metadata->>file_path", rel_path).execute()
        except Exception:
            pass

        updated += 1
        chunks = splitter.split_text(content)
        for idx, chunk in enumerate(chunks):
            pending_docs.append(
                Document(
                    page_content=chunk,
                    metadata={"file_path": rel_path, "chunk_index": idx, "file_hash": file_hash},
                )
            )

    print(f"⏭️  Unchanged files skipped: {skipped}")
    print(f"📝 Files to index/update: {updated} ({len(pending_docs)} total chunks)")

    if not pending_docs:
        print("✨ Codebase is already up to date. No indexing required.")
        return

    print(f"🚀 Starting batch embedding (batch size: {BATCH_SIZE})...")
    for i in range(0, len(pending_docs), BATCH_SIZE):
        batch = pending_docs[i : i + BATCH_SIZE]
        end_idx = min(i + BATCH_SIZE, len(pending_docs))
        print(f"  ⚡ Embedding chunks {i + 1}–{end_idx}...")
        try:
            vs.add_documents(batch)
            print(f"  💾 Inserted {len(batch)} chunks.")
        except Exception as exc:
            print(f"  ❌ Batch failed: {exc}")

    print(f"\n🎉 Indexing done! Processed {len(pending_docs)} chunks across {updated} files.")
    print(f"   Skipped {skipped} unchanged files.")
