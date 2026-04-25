"""Tree-sitter language loading utilities."""

from tree_sitter import Language
from tree_sitter_python import language as python_language

EXT_MAP: dict[str, str] = {
    ".py": "python",
}


def load_language(lang_name: str) -> Language:
    """Return a loaded Tree-sitter language for a known language name."""
    if lang_name == "python":
        return Language(python_language())

    raise ValueError(f"Unsupported language: {lang_name}")

