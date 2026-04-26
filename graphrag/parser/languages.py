"""Tree-sitter language loading utilities."""

from tree_sitter import Language
from tree_sitter_javascript import language as javascript_language
from tree_sitter_java import language as java_language
from tree_sitter_python import language as python_language
from tree_sitter_typescript import language_tsx, language_typescript

EXT_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
}


def load_language(lang_name: str, extension: str | None = None) -> Language:
    """Return a loaded Tree-sitter language for a known language name."""
    if lang_name == "python":
        return Language(python_language())
    if lang_name == "typescript":
        if extension == ".tsx":
            return Language(language_tsx())
        return Language(language_typescript())
    if lang_name == "javascript":
        return Language(javascript_language())
    if lang_name == "java":
        return Language(java_language())

    raise ValueError(f"Unsupported language: {lang_name}")

