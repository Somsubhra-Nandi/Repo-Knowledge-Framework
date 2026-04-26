"""Repository walker for discovering parseable files."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path

from graphrag.parser.languages import EXT_MAP


class RepoWalker:
    """
    Discovers all parseable source files in a repository root.
    Respects .gitignore patterns and skips common noise directories.
    """

    DEFAULT_SKIP_DIRS: frozenset[str] = frozenset(
        {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".ruff_cache",
            "dist",
            "build",
            "target",
            ".idea",
            ".vscode",
            "egg-info",
        }
    )

    def __init__(self, repo_root: str, skip_dirs: frozenset[str] | None = None) -> None:
        self._repo_root = Path(repo_root).resolve()
        self._skip_dirs = skip_dirs or self.DEFAULT_SKIP_DIRS

    def discover(self) -> list[str]:
        """
        Walk the repo root recursively and return absolute paths of all parseable files.
        Skip default skip dirs and gitignore patterns if present.
        Returns paths as forward-slash strings for cross-platform consistency.
        """
        patterns = self._load_gitignore_patterns()
        discovered: list[str] = []

        for root, dirs, files in os.walk(self._repo_root):
            dirs[:] = [directory for directory in dirs if directory not in self._skip_dirs]

            root_path = Path(root)
            for filename in files:
                suffix = Path(filename).suffix
                if suffix not in EXT_MAP:
                    continue

                absolute_path = root_path / filename
                relative_path = absolute_path.relative_to(self._repo_root).as_posix()
                if self._is_ignored(relative_path, patterns):
                    continue

                discovered.append(absolute_path.resolve().as_posix())

        return sorted(discovered)

    def _load_gitignore_patterns(self) -> list[str]:
        """Load patterns from .gitignore at repo root if it exists."""
        gitignore_path = self._repo_root / ".gitignore"
        if not gitignore_path.exists():
            return []

        patterns: list[str] = []
        for line in gitignore_path.read_text(encoding="utf-8").splitlines():
            pattern = line.strip()
            if not pattern or pattern.startswith("#"):
                continue
            patterns.append(pattern)
        return patterns

    def _is_ignored(self, rel_path: str, patterns: list[str]) -> bool:
        """
        Return True if the relative path matches any gitignore pattern.
        Uses fnmatch with path and filename checks.
        """
        file_name = Path(rel_path).name
        for pattern in patterns:
            normalized = pattern.replace("\\", "/")
            if fnmatch.fnmatch(rel_path, normalized) or fnmatch.fnmatch(file_name, normalized):
                return True
            if normalized.endswith("/") and rel_path.startswith(normalized.rstrip("/") + "/"):
                return True
        return False
