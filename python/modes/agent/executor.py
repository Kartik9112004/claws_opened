"""
modes/agent/executor.py — Staged filesystem overlay (ToolExecutor).
All mutations are held in memory until explicitly approved and applied.
Mirrors the TypeScript ToolExecutor class.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from config import CODEBASE_PATH
from modes.agent.tracker import ActionTracker

TEXT_EXTENSIONS = {
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    ".json", ".md", ".mdx", ".css", ".html",
    ".yml", ".yaml", ".toml", ".txt", ".py",
}

EXCLUDE_PATTERNS = {
    "node_modules", ".git", "dist", "build", ".bun",
    "__pycache__", ".venv", "venv",
}


def _is_text(path: str) -> bool:
    return Path(path).suffix.lower() in TEXT_EXTENSIONS


class ToolExecutor:
    def __init__(self, tracker: ActionTracker, codebase_path: str = CODEBASE_PATH) -> None:
        self.tracker = tracker
        self.codebase_path = codebase_path
        self._overlay: dict[str, str] = {}          # rel_path → staged content (inside workspace)
        self._deleted: set[str] = set()              # rel_paths staged for deletion
        self._external_files: dict[str, str] = {}    # abs_path → staged content (outside workspace)
        self._staged_folders: set[str] = set()       # abs_paths already staged for creation

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _norm(self, rel: str) -> str:
        return rel.replace("\\", "/").lstrip("./").strip("/") if rel else rel

    def _resolve_any(self, path: str) -> tuple[str, bool]:
        """
        Resolve a path to an absolute path.
        Returns (abs_path, is_external).
        - is_external=False means path is inside the workspace (use relative key).
        - is_external=True means path is outside the workspace (use abs_path key).
        """
        root = os.path.realpath(self.codebase_path)
        if os.path.isabs(path):
            abs_path = os.path.realpath(path)
        else:
            abs_path = os.path.realpath(os.path.join(self.codebase_path, path))
        is_external = not (abs_path.startswith(root + os.sep) or abs_path == root)
        return abs_path, is_external

    def _resolve_safe(self, rel: str) -> str:
        """Resolve a path that MUST be inside the workspace (for read/list/delete)."""
        abs_path, is_external = self._resolve_any(rel)
        if is_external:
            raise ValueError(
                f"Path is outside workspace: '{rel}'. "
                "Use a relative path for this operation."
            )
        return abs_path

    def _excluded(self, rel: str) -> bool:
        parts = self._norm(rel).split("/")
        return bool(set(parts) & EXCLUDE_PATTERNS)

    def _assert_not_excluded(self, rel: str, op: str) -> None:
        if self._excluded(rel):
            raise ValueError(f"{op}: path is excluded: {rel}")

    def _get_effective_text(self, rel: str) -> str | None:
        key = self._norm(rel)
        if key in self._deleted:
            return None
        if key in self._overlay:
            return self._overlay[key]
        abs_path = self._resolve_safe(rel)
        if os.path.isfile(abs_path):
            return Path(abs_path).read_text(encoding="utf-8", errors="ignore")
        return None

    # ── Tool methods (called by agent tool executors) ─────────────────────────

    def read_file(self, path: str) -> str:
        self._assert_not_excluded(path, "read_file")
        text = self._get_effective_text(path)
        if text is None:
            raise FileNotFoundError(f"File not found: {path}")
        self.tracker.log("code_analysis", self._norm(path), {"after": text, "toolName": "read_file"}, "executed")
        return text

    def create_file(self, path: str, content: str) -> str:
        abs_path, is_external = self._resolve_any(path)
        if is_external:
            # Allow creation of files outside the workspace (e.g. /Users/.../Desktop/file.py)
            if os.path.exists(abs_path):
                raise FileExistsError(f"create_file: already exists: {abs_path}")
            self._external_files[abs_path] = content
            self.tracker.log("file_create", abs_path, {"after": content}, "pending")
            return f"Staged new external file: {abs_path}"
        # Inside workspace — use relative key
        self._assert_not_excluded(path, "create_file")
        key = self._norm(path)
        if os.path.exists(abs_path) and key not in self._deleted:
            raise FileExistsError(f"create_file: already exists: {path}")
        self._deleted.discard(key)
        self._overlay[key] = content
        self.tracker.log("file_create", key, {"after": content}, "pending")
        return f"Staged new file: {key}"

    def modify_file(self, path: str, content: str) -> str:
        self._assert_not_excluded(path, "modify_file")
        before = self._get_effective_text(path)
        if before is None:
            raise FileNotFoundError(f"modify_file: file not found: {path}")
        key = self._norm(path)
        self._overlay[key] = content
        self.tracker.log("file_modify", key, {"before": before, "after": content}, "pending")
        return f"Staged update: {key}"

    def delete_file(self, path: str) -> str:
        self._assert_not_excluded(path, "delete_file")
        before = self._get_effective_text(path)
        if before is None:
            raise FileNotFoundError(f"delete_file: file not found: {path}")
        key = self._norm(path)
        self._overlay.pop(key, None)
        self._deleted.add(key)
        self.tracker.log("file_delete", key, {"before": before}, "pending")
        return f"Staged delete: {key}"

    def create_folder(self, path: str) -> str:
        self._assert_not_excluded(path, "create_folder")
        abs_path, is_external = self._resolve_any(path)
        # Use the absolute path as the key so external paths are not mangled
        key = abs_path if is_external else self._norm(path)
        # Deduplicate — if already staged, tell the model so it stops looping
        if abs_path in self._staged_folders or os.path.isdir(abs_path):
            return f"Folder already exists or is already staged: {abs_path}. No further action needed."
        self._staged_folders.add(abs_path)
        self.tracker.log("folder_create", key, {"after": key, "is_external": is_external}, "pending")
        return f"Staged folder for creation: {abs_path}"

    def list_files(self, path: str, recursive: bool = False) -> str:
        self._assert_not_excluded(path, "list_files")
        abs_path = self._resolve_safe(path)
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"list_files: not found: {path}")
        lines: list[str] = []
        if os.path.isdir(abs_path):
            if recursive:
                for root, dirs, files in os.walk(abs_path):
                    dirs[:] = [d for d in dirs if not self._excluded(
                        os.path.relpath(os.path.join(root, d), self.codebase_path))]
                    for f in files:
                        rel = os.path.relpath(os.path.join(root, f), self.codebase_path)
                        if not self._excluded(rel):
                            lines.append(rel.replace("\\", "/"))
            else:
                for entry in os.scandir(abs_path):
                    rel = os.path.relpath(entry.path, self.codebase_path)
                    if not self._excluded(rel):
                        lines.append(entry.name + ("/" if entry.is_dir() else ""))
        else:
            lines.append(os.path.relpath(abs_path, self.codebase_path))
        out = "\n".join(sorted(lines))
        self.tracker.log("code_analysis", self._norm(path), {"after": out, "toolName": "list_files"}, "executed")
        return out or "(empty)"

    def search_files(self, root: str, pattern: str, content_contains: str | None = None) -> str:
        import fnmatch
        self._assert_not_excluded(root, "search_files")
        root_abs = self._resolve_safe(root)
        results: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root_abs):
            dirnames[:] = [d for d in dirnames if not self._excluded(
                os.path.relpath(os.path.join(dirpath, d), self.codebase_path))]
            for fname in filenames:
                full = os.path.join(dirpath, fname)
                rel = os.path.relpath(full, self.codebase_path).replace("\\", "/")
                if self._excluded(rel):
                    continue
                if fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(fname, pattern):
                    if content_contains and _is_text(full):
                        try:
                            if content_contains not in Path(full).read_text(encoding="utf-8", errors="ignore"):
                                continue
                        except Exception:
                            continue
                    results.append(rel)
        out = "\n".join(sorted(set(results)))
        self.tracker.log("code_analysis", self._norm(root), {"after": out or "(no matches)", "toolName": "search_files"}, "executed")
        return out or "(no matches)"

    def analyze_codebase(self, path: str = ".") -> str:
        root_abs = self._resolve_safe(path)
        files = dirs = 0
        for dirpath, dirnames, filenames in os.walk(root_abs):
            dirnames[:] = [d for d in dirnames if not self._excluded(
                os.path.relpath(os.path.join(dirpath, d), self.codebase_path))]
            dirs += len(dirnames)
            files += len(filenames)
        summary = f"Files: {files} | Directories: {dirs}"
        self.tracker.log("code_analysis", self._norm(path), {"after": summary, "toolName": "analyze_codebase"}, "executed")
        return summary

    def queue_shell(self, command: str) -> str:
        self.tracker.log("tool_execute", "shell", {"command": command, "toolName": "execute_shell"}, "pending")
        return f"Shell queued: {command}"

    # ── Apply approved changes ────────────────────────────────────────────────

    def apply_approved(self) -> list[str]:
        errors: list[str] = []
        actions = self.tracker.get_actions()

        # Folders first
        for a in actions:
            if a.type == "folder_create" and a.status == "approved":
                try:
                    # Use absolute path directly if it is one, otherwise resolve via workspace
                    if os.path.isabs(a.path):
                        os.makedirs(a.path, exist_ok=True)
                    else:
                        os.makedirs(self._resolve_safe(a.path), exist_ok=True)
                except Exception as exc:
                    errors.append(str(exc))

        # File ops — deduplicate, keep last per path
        file_ops = [
            a for a in actions
            if a.type in ("file_create", "file_modify", "file_delete") and a.status == "approved"
        ]
        last_by_path: dict[str, object] = {}
        for a in sorted(file_ops, key=lambda x: x.timestamp):
            # Preserve absolute paths as-is; only normalise relative paths
            key = a.path if os.path.isabs(a.path) else self._norm(a.path)
            last_by_path[key] = a

        for p, a in last_by_path.items():
            try:
                # p could be an absolute path (external) or relative (workspace)
                if os.path.isabs(p):
                    target = p
                else:
                    target = self._resolve_safe(p)
                if a.type == "file_delete":
                    if os.path.exists(target):
                        os.remove(target)
                else:
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    Path(target).write_text(a.details.get("after", ""), encoding="utf-8")
            except Exception as exc:
                errors.append(str(exc))

        # Shell commands
        for a in actions:
            if a.type == "tool_execute" and a.status == "approved":
                cmd = a.details.get("command", "")
                if cmd:
                    result = subprocess.run(cmd, shell=True, cwd=self.codebase_path,
                                            capture_output=True, text=True)
                    if result.returncode != 0:
                        errors.append(f"Shell exit {result.returncode}: {cmd}")

        return errors

    def clear_staging(self) -> None:
        self._overlay.clear()
        self._deleted.clear()
        self._external_files.clear()
        self._staged_folders.clear()
