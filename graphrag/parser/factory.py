"""Parser factory and language-specific file parsing."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Node, Parser

from graphrag.parser.languages import EXT_MAP, load_language
from graphrag.schema.models import build_fqn


@dataclass
class CallInfo:
    """A function call found inside a method body."""

    callee_name: str
    line: int


@dataclass
class ClassInfo:
    """Details for a parsed class definition."""

    name: str
    line: int
    methods: list[str]
    fqn: str


@dataclass
class MethodInfo:
    """Details for a parsed function or method definition."""

    name: str
    line: int
    class_name: str | None
    fqn: str
    signature: str
    source_code: str
    calls: list[CallInfo]


@dataclass
class FolderNode:
    """Folder information for the parsed source file."""

    path: str
    name: str


@dataclass
class ParsedFile:
    """Top-level parsed output for one source file."""

    path: str
    language: str
    classes: list[ClassInfo]
    methods: list[MethodInfo]
    imports: list[str]
    folder: FolderNode
    module_name: str
    checksum: str


def get_parser(file_path: str) -> Parser:
    """Return a configured parser for the input file extension."""
    extension = Path(file_path).suffix
    language_name = EXT_MAP.get(extension)
    if language_name is None:
        raise ValueError(f"Unsupported file extension: {extension}")

    parser = Parser()
    parser.language = load_language(language_name, extension=extension)
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


def _extract_signature(source: bytes, node: Node) -> str:
    """Build a best-effort Python function signature text ending with ':'."""
    method_name = _find_identifier_text(source, node)
    parameters_node = node.child_by_field_name("parameters")
    parameters = _node_text(source, parameters_node) if parameters_node is not None else "()"
    return_type_node = node.child_by_field_name("return_type")
    return_type = f" -> {_node_text(source, return_type_node)}" if return_type_node is not None else ""
    return f"def {method_name}{parameters}{return_type}:"


def _collect_call_expressions(source: bytes, function_node: Node) -> list[CallInfo]:
    """Collect call expressions contained within a function definition."""
    calls: list[CallInfo] = []
    stack: list[Node] = [function_node]

    while stack:
        current = stack.pop()
        if current.type in {"call_expression", "call"}:
            function_part = current.child_by_field_name("function")
            if function_part is not None:
                calls.append(
                    CallInfo(
                        callee_name=_node_text(source, function_part).strip(),
                        line=current.start_point[0] + 1,
                    )
                )
        for child in current.children:
            stack.append(child)

    return calls


def _extract_ts_like_signature(source: bytes, node: Node, name: str) -> str:
    """Build a signature-like string for TypeScript/JavaScript functions."""
    parameters_node = node.child_by_field_name("parameters")
    parameters = _node_text(source, parameters_node) if parameters_node is not None else "()"
    return_type_node = node.child_by_field_name("return_type")
    return_type = _node_text(source, return_type_node) if return_type_node is not None else ""
    return f"{name}{parameters}{return_type}"


def _collect_python_definitions(
    node: Node,
    source: bytes,
    module_name: str,
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
            fqn=build_fqn(module_name, class_name),
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

        method_fqn = (
            build_fqn(module_name, class_name, method_name)
            if class_name is not None
            else build_fqn(module_name, method_name)
        )
        method_info = MethodInfo(
            name=method_name,
            line=node.start_point[0] + 1,
            class_name=class_name,
            fqn=method_fqn,
            signature=_extract_signature(source, node),
            source_code=_node_text(source, node),
            calls=_collect_call_expressions(source, node),
        )
        methods.append(method_info)
        if class_name is not None:
            class_lookup[class_name].methods.append(method_name)

    for child in node.children:
        _collect_python_definitions(
            node=child,
            source=source,
            module_name=module_name,
            classes=classes,
            methods=methods,
            imports=imports,
            class_lookup=class_lookup,
        )


def _extract_callable_value(source: bytes, node: Node) -> tuple[str, str, list[CallInfo]] | None:
    """Extract signature, source, and calls from arrow/function variable initializer."""
    value_node = node.child_by_field_name("value")
    if value_node is None or value_node.type not in {"arrow_function", "function_expression"}:
        return None

    name = _find_identifier_text(source, node)
    signature = _extract_ts_like_signature(source, value_node, name)
    return signature, _node_text(source, value_node), _collect_call_expressions(source, value_node)


def _collect_typescript_definitions(
    node: Node,
    source: bytes,
    module_name: str,
    classes: list[ClassInfo],
    methods: list[MethodInfo],
    imports: list[str],
    class_lookup: dict[str, ClassInfo],
) -> None:
    """Walk a TypeScript/JavaScript tree and collect classes, methods, and imports."""
    if node.type == "import_statement":
        imports.append(_node_text(source, node).strip())
    elif node.type in {"class_declaration", "interface_declaration"}:
        class_name = _find_identifier_text(source, node)
        class_info = ClassInfo(
            name=class_name,
            line=node.start_point[0] + 1,
            methods=[],
            fqn=build_fqn(module_name, class_name),
        )
        classes.append(class_info)
        class_lookup[class_name] = class_info
    elif node.type == "method_definition":
        method_name = _find_identifier_text(source, node)
        class_name: str | None = None
        parent = node.parent
        if (
            parent is not None
            and parent.type == "class_body"
            and parent.parent is not None
            and parent.parent.type == "class_declaration"
        ):
            class_name = _find_identifier_text(source, parent.parent)

        method_fqn = (
            build_fqn(module_name, class_name, method_name)
            if class_name is not None
            else build_fqn(module_name, method_name)
        )
        methods.append(
            MethodInfo(
                name=method_name,
                line=node.start_point[0] + 1,
                class_name=class_name,
                fqn=method_fqn,
                signature=_extract_ts_like_signature(source, node, method_name),
                source_code=_node_text(source, node),
                calls=_collect_call_expressions(source, node),
            )
        )
        if class_name is not None:
            class_lookup[class_name].methods.append(method_name)
    elif node.type == "function_declaration":
        function_name = _find_identifier_text(source, node)
        methods.append(
            MethodInfo(
                name=function_name,
                line=node.start_point[0] + 1,
                class_name=None,
                fqn=build_fqn(module_name, function_name),
                signature=_extract_ts_like_signature(source, node, function_name),
                source_code=_node_text(source, node),
                calls=_collect_call_expressions(source, node),
            )
        )
    elif node.type == "variable_declarator":
        name = _find_identifier_text(source, node)
        callable_value = _extract_callable_value(source, node)
        if callable_value is not None:
            signature, source_code, calls = callable_value
            methods.append(
                MethodInfo(
                    name=name,
                    line=node.start_point[0] + 1,
                    class_name=None,
                    fqn=build_fqn(module_name, name),
                    signature=signature,
                    source_code=source_code,
                    calls=calls,
                )
            )

    for child in node.children:
        _collect_typescript_definitions(
            node=child,
            source=source,
            module_name=module_name,
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
    file_path_obj = Path(file_path)

    classes: list[ClassInfo] = []
    methods: list[MethodInfo] = []
    imports: list[str] = []
    class_lookup: dict[str, ClassInfo] = {}
    checksum = hashlib.sha256(source_bytes).hexdigest()
    folder_path = file_path_obj.parent.as_posix()
    folder = FolderNode(path=folder_path, name=file_path_obj.parent.name)
    module_name = file_path_obj.with_suffix("").as_posix().replace("/", ".")

    if language_name == "python":
        _collect_python_definitions(
            node=tree.root_node,
            source=source_bytes,
            module_name=module_name,
            classes=classes,
            methods=methods,
            imports=imports,
            class_lookup=class_lookup,
        )
    elif language_name in {"typescript", "javascript"}:
        _collect_typescript_definitions(
            node=tree.root_node,
            source=source_bytes,
            module_name=module_name,
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
        folder=folder,
        module_name=module_name,
        checksum=checksum,
    )

