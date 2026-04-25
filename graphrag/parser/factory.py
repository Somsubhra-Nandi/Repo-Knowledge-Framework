"""Parser factory and language-specific file parsing."""

from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node, Parser

from graphrag.parser.languages import EXT_MAP, load_language


@dataclass
class ClassInfo:
    """Details for a parsed class definition."""

    name: str
    line: int
    methods: list[str]


@dataclass
class MethodInfo:
    """Details for a parsed function or method definition."""

    name: str
    line: int
    class_name: str | None


@dataclass
class ParsedFile:
    """Top-level parsed output for one source file."""

    path: str
    language: str
    classes: list[ClassInfo]
    methods: list[MethodInfo]
    imports: list[str]


def get_parser(file_path: str) -> Parser:
    """Return a configured parser for the input file extension."""
    extension = Path(file_path).suffix
    language_name = EXT_MAP.get(extension)
    if language_name is None:
        raise ValueError(f"Unsupported file extension: {extension}")

    parser = Parser()
    parser.language = load_language(language_name)
    return parser


def _node_text(source: bytes, node: Node) -> str:
    """Decode source text covered by a tree-sitter node."""
    return source[node.start_byte : node.end_byte].decode("utf-8")


def _find_identifier_text(source: bytes, node: Node) -> str:
    """Return identifier text from a class/function node."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return ""
    return _node_text(source, name_node)


def _collect_python_definitions(
    node: Node,
    source: bytes,
    classes: list[ClassInfo],
    methods: list[MethodInfo],
    imports: list[str],
    class_lookup: dict[str, ClassInfo],
) -> None:
    """Walk a python tree and collect classes, methods, and imports."""
    if node.type in {"import_statement", "import_from_statement"}:
        imports.append(_node_text(source, node).strip())
    elif node.type == "class_definition":
        class_name = _find_identifier_text(source, node)
        class_info = ClassInfo(
            name=class_name,
            line=node.start_point[0] + 1,
            methods=[],
        )
        classes.append(class_info)
        class_lookup[class_name] = class_info
    elif node.type == "function_definition":
        method_name = _find_identifier_text(source, node)
        class_name: str | None = None
        parent = node.parent
        if (
            parent is not None
            and parent.type == "block"
            and parent.parent is not None
            and parent.parent.type == "class_definition"
        ):
            class_name = _find_identifier_text(source, parent.parent)

        method_info = MethodInfo(
            name=method_name,
            line=node.start_point[0] + 1,
            class_name=class_name,
        )
        methods.append(method_info)
        if class_name is not None:
            class_lookup[class_name].methods.append(method_name)

    for child in node.children:
        _collect_python_definitions(
            node=child,
            source=source,
            classes=classes,
            methods=methods,
            imports=imports,
            class_lookup=class_lookup,
        )


def parse_file(file_path: str) -> ParsedFile:
    """Parse a single source file into structured metadata."""
    parser = get_parser(file_path)
    extension = Path(file_path).suffix
    language_name = EXT_MAP[extension]

    source_bytes = Path(file_path).read_bytes()
    tree = parser.parse(source_bytes)

    classes: list[ClassInfo] = []
    methods: list[MethodInfo] = []
    imports: list[str] = []
    class_lookup: dict[str, ClassInfo] = {}

    if language_name == "python":
        _collect_python_definitions(
            node=tree.root_node,
            source=source_bytes,
            classes=classes,
            methods=methods,
            imports=imports,
            class_lookup=class_lookup,
        )

    return ParsedFile(
        path=file_path,
        language=language_name,
        classes=classes,
        methods=methods,
        imports=imports,
    )

