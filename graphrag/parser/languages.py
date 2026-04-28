"""Tree-sitter language loading utilities."""

from tree_sitter import Language
from tree_sitter_bash import language as bash_language
from tree_sitter_c import language as c_language
from tree_sitter_cpp import language as cpp_language
from tree_sitter_css import language as css_language
from tree_sitter_go import language as go_language
from tree_sitter_html import language as html_language
from tree_sitter_javascript import language as javascript_language
from tree_sitter_java import language as java_language
from tree_sitter_kotlin import language as kotlin_language
from tree_sitter_php import language_php
from tree_sitter_python import language as python_language
from tree_sitter_ruby import language as ruby_language
from tree_sitter_rust import language as rust_language
from tree_sitter_sql import language as sql_language
from tree_sitter_swift import language as swift_language
from tree_sitter_typescript import language_tsx, language_typescript

EXT_MAP: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
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
    if lang_name == "go":
        return Language(go_language())
    if lang_name == "rust":
        return Language(rust_language())
    if lang_name == "ruby":
        return Language(ruby_language())
    if lang_name == "php":
        return Language(language_php())
    if lang_name == "swift":
        return Language(swift_language())
    if lang_name == "kotlin":
        return Language(kotlin_language())
    if lang_name == "shell":
        return Language(bash_language())
    if lang_name == "sql":
        return Language(sql_language())
    if lang_name == "html":
        return Language(html_language())
    if lang_name == "css":
        return Language(css_language())
    if lang_name == "c":
        return Language(c_language())
    if lang_name == "cpp":
        return Language(cpp_language())

    raise ValueError(f"Unsupported language: {lang_name}")

