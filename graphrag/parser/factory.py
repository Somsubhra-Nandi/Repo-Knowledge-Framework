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
        if current.type in {"call_expression", "call", "method_invocation"}:
            callee_name = ""
            function_part = current.child_by_field_name("function")
            if function_part is not None:
                callee_name = _node_text(source, function_part).strip()
            elif current.type == "method_invocation":
                object_part = current.child_by_field_name("object")
                name_part = current.child_by_field_name("name")
                if object_part is not None and name_part is not None:
                    callee_name = f"{_node_text(source, object_part).strip()}.{_node_text(source, name_part).strip()}"
                elif name_part is not None:
                    callee_name = _node_text(source, name_part).strip()

            if callee_name:
                calls.append(
                    CallInfo(
                        callee_name=callee_name,
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


def _extract_java_package(root_node: Node, source: bytes) -> str:
    """Extract the Java package name from the root AST node."""
    for child in root_node.children:
        if child.type == "package_declaration":
            declaration = _node_text(source, child).strip()
            if declaration.startswith("package "):
                declaration = declaration[len("package ") :]
            if declaration.endswith(";"):
                declaration = declaration[:-1]
            return declaration.strip()
    return ""


def _extract_go_package(root_node: Node, source: bytes) -> str:
    """Extract the Go package name from the root AST node."""
    for child in root_node.children:
        if child.type == "package_clause":
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                return _node_text(source, name_node).strip()
            declaration = _node_text(source, child).strip()
            if declaration.startswith("package "):
                return declaration[len("package ") :].strip()
    return ""


def _extract_go_receiver_type(source: bytes, receiver_node: Node | None) -> str | None:
    """Extract receiver type name from a Go method receiver declaration."""
    if receiver_node is None:
        return None

    for child in receiver_node.children:
        if child.type != "parameter_declaration":
            continue
        type_node = child.child_by_field_name("type")
        if type_node is None:
            continue
        receiver_type = _node_text(source, type_node).strip().replace("*", "").strip()
        if "." in receiver_type:
            receiver_type = receiver_type.split(".")[-1]
        if receiver_type:
            return receiver_type

    candidates: list[str] = []
    for child in receiver_node.children:
        if child.type in {"identifier", "type_identifier", "qualified_type"}:
            candidates.append(_node_text(source, child).strip())
        if child.type == "parameter_declaration":
            for parameter_child in child.children:
                if parameter_child.type in {"identifier", "type_identifier", "qualified_type"}:
                    candidates.append(_node_text(source, parameter_child).strip())

    if len(candidates) >= 2:
        receiver_type = candidates[1]
    elif candidates:
        receiver_type = candidates[-1]
    else:
        receiver_type = _node_text(source, receiver_node).strip()

    receiver_type = receiver_type.replace("*", "").strip()
    if "." in receiver_type:
        receiver_type = receiver_type.split(".")[-1]
    if receiver_type.startswith("(") and receiver_type.endswith(")"):
        receiver_type = receiver_type[1:-1].strip()
    return receiver_type or None


def _extract_go_signature(source: bytes, node: Node, method_name: str) -> str:
    """Build a signature-like string for Go functions and methods."""
    parameters_node = node.child_by_field_name("parameters")
    parameters = _node_text(source, parameters_node) if parameters_node is not None else "()"
    result_node = node.child_by_field_name("result")
    result = f" {_node_text(source, result_node).strip()}" if result_node is not None else ""
    receiver_node = node.child_by_field_name("receiver")
    if receiver_node is not None:
        receiver = _node_text(source, receiver_node).strip()
        return f"func {receiver} {method_name}{parameters}{result}"
    return f"func {method_name}{parameters}{result}"


def _collect_go_definitions(
    node: Node,
    source: bytes,
    module_name: str,
    classes: list[ClassInfo],
    methods: list[MethodInfo],
    imports: list[str],
    class_lookup: dict[str, ClassInfo],
) -> None:
    """Walk a Go tree and collect structs, interfaces, functions, methods, and imports."""
    if node.type == "import_declaration":
        imports.append(_node_text(source, node).strip())
    elif node.type == "import_spec":
        imports.append(_node_text(source, node).strip())
    elif node.type == "type_spec":
        value_node = node.child_by_field_name("type")
        if value_node is not None and value_node.type in {"struct_type", "interface_type"}:
            class_name = _find_identifier_text(source, node)
            class_info = ClassInfo(
                name=class_name,
                line=node.start_point[0] + 1,
                methods=[],
                fqn=build_fqn(module_name, class_name),
            )
            classes.append(class_info)
            class_lookup[class_name] = class_info
    elif node.type == "function_declaration":
        method_name = _find_identifier_text(source, node)
        methods.append(
            MethodInfo(
                name=method_name,
                line=node.start_point[0] + 1,
                class_name=None,
                fqn=build_fqn(module_name, method_name),
                signature=_extract_go_signature(source, node, method_name),
                source_code=_node_text(source, node),
                calls=_collect_call_expressions(source, node),
            )
        )
    elif node.type == "method_declaration":
        method_name = _find_identifier_text(source, node)
        class_name = _extract_go_receiver_type(source, node.child_by_field_name("receiver"))
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
                signature=_extract_go_signature(source, node, method_name),
                source_code=_node_text(source, node),
                calls=_collect_call_expressions(source, node),
            )
        )
        if class_name is not None and class_name in class_lookup:
            class_lookup[class_name].methods.append(method_name)

    for child in node.children:
        _collect_go_definitions(
            node=child,
            source=source,
            module_name=module_name,
            classes=classes,
            methods=methods,
            imports=imports,
            class_lookup=class_lookup,
        )


def _extract_rust_signature(source: bytes, node: Node, function_name: str) -> str:
    """Build a signature-like string for Rust functions and methods."""
    parameters_node = node.child_by_field_name("parameters")
    parameters = _node_text(source, parameters_node) if parameters_node is not None else "()"
    return_type_node = node.child_by_field_name("return_type")
    if return_type_node is not None:
        return f"fn {function_name}{parameters} {_node_text(source, return_type_node).strip()}"
    return f"fn {function_name}{parameters}"


def _extract_rust_impl_type(source: bytes, impl_node: Node) -> str | None:
    """Extract concrete impl type name from a Rust impl block."""
    type_node = impl_node.child_by_field_name("type")
    if type_node is None:
        return None
    type_text = _node_text(source, type_node).strip()
    if "<" in type_text:
        type_text = type_text.split("<", maxsplit=1)[0].strip()
    if "::" in type_text:
        type_text = type_text.split("::")[-1].strip()
    return type_text or None


def _collect_rust_definitions(
    node: Node,
    source: bytes,
    module_name: str,
    classes: list[ClassInfo],
    methods: list[MethodInfo],
    imports: list[str],
    class_lookup: dict[str, ClassInfo],
) -> None:
    """Walk a Rust tree and collect structs, traits, enums, functions, methods, and imports."""
    if node.type == "use_declaration":
        imports.append(_node_text(source, node).strip())
    elif node.type in {"struct_item", "trait_item", "enum_item"}:
        class_name = _find_identifier_text(source, node)
        class_info = ClassInfo(
            name=class_name,
            line=node.start_point[0] + 1,
            methods=[],
            fqn=build_fqn(module_name, class_name),
        )
        classes.append(class_info)
        class_lookup[class_name] = class_info
    elif node.type == "function_item":
        function_name = _find_identifier_text(source, node)
        class_name: str | None = None
        parent = node.parent
        if (
            parent is not None
            and parent.type == "declaration_list"
            and parent.parent is not None
            and parent.parent.type == "impl_item"
        ):
            class_name = _extract_rust_impl_type(source, parent.parent)

        method_fqn = (
            build_fqn(module_name, class_name, function_name)
            if class_name is not None
            else build_fqn(module_name, function_name)
        )
        methods.append(
            MethodInfo(
                name=function_name,
                line=node.start_point[0] + 1,
                class_name=class_name,
                fqn=method_fqn,
                signature=_extract_rust_signature(source, node, function_name),
                source_code=_node_text(source, node),
                calls=_collect_call_expressions(source, node),
            )
        )
        if class_name is not None and class_name in class_lookup:
            class_lookup[class_name].methods.append(function_name)

    for child in node.children:
        _collect_rust_definitions(
            node=child,
            source=source,
            module_name=module_name,
            classes=classes,
            methods=methods,
            imports=imports,
            class_lookup=class_lookup,
        )


def _extract_java_annotations(source: bytes, node: Node) -> str:
    """Collect annotation text directly attached to a Java declaration node."""
    annotations: list[str] = []
    for child in node.children:
        if child.type in {"marker_annotation", "annotation"}:
            annotations.append(_node_text(source, child).strip())
        elif child.type == "modifiers":
            for modifier_child in child.children:
                if modifier_child.type in {"marker_annotation", "annotation"}:
                    annotations.append(_node_text(source, modifier_child).strip())
    return " ".join(annotations)


def _extract_java_method_signature(source: bytes, node: Node, name: str) -> str:
    """Build a method signature string for Java methods and constructors."""
    annotations = _extract_java_annotations(source, node)
    parameters_node = node.child_by_field_name("parameters")
    parameters = _node_text(source, parameters_node) if parameters_node is not None else "()"

    if node.type == "constructor_declaration":
        base_signature = f"{name}{parameters}"
    else:
        return_type_node = node.child_by_field_name("type")
        return_type = _node_text(source, return_type_node).strip() if return_type_node is not None else ""
        base_signature = f"{name}{parameters}"
        if return_type:
            base_signature = f"{base_signature}: {return_type}"

    if annotations:
        return f"{annotations} {base_signature}"
    return base_signature


def _get_enclosing_java_class(source: bytes, node: Node) -> str | None:
    """Return enclosing Java class/interface/enum name if present."""
    current = node.parent
    while current is not None:
        if current.type in {"class_declaration", "interface_declaration", "enum_declaration"}:
            return _find_identifier_text(source, current)
        current = current.parent
    return None


def _collect_java_definitions(
    node: Node,
    source: bytes,
    module_name: str,
    classes: list[ClassInfo],
    methods: list[MethodInfo],
    imports: list[str],
    class_lookup: dict[str, ClassInfo],
) -> None:
    """Walk a Java tree and collect classes, methods, constructors, and imports."""
    if node.type == "import_declaration":
        imports.append(_node_text(source, node).strip())
    elif node.type in {"class_declaration", "interface_declaration", "enum_declaration"}:
        class_name = _find_identifier_text(source, node)
        class_info = ClassInfo(
            name=class_name,
            line=node.start_point[0] + 1,
            methods=[],
            fqn=build_fqn(module_name, class_name),
        )
        classes.append(class_info)
        class_lookup[class_name] = class_info
    elif node.type in {"method_declaration", "constructor_declaration"}:
        method_name = _find_identifier_text(source, node)
        class_name = _get_enclosing_java_class(source, node)
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
                signature=_extract_java_method_signature(source, node, method_name),
                source_code=_node_text(source, node),
                calls=_collect_call_expressions(source, node),
            )
        )
        if class_name is not None and class_name in class_lookup:
            class_lookup[class_name].methods.append(method_name)

    for child in node.children:
        _collect_java_definitions(
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
    elif language_name == "java":
        java_package = _extract_java_package(tree.root_node, source_bytes)
        effective_module = java_package if java_package else module_name
        _collect_java_definitions(
            node=tree.root_node,
            source=source_bytes,
            module_name=effective_module,
            classes=classes,
            methods=methods,
            imports=imports,
            class_lookup=class_lookup,
        )
    elif language_name == "go":
        go_package = _extract_go_package(tree.root_node, source_bytes)
        effective_module = go_package if go_package else module_name
        _collect_go_definitions(
            node=tree.root_node,
            source=source_bytes,
            module_name=effective_module,
            classes=classes,
            methods=methods,
            imports=imports,
            class_lookup=class_lookup,
        )
    elif language_name == "rust":
        _collect_rust_definitions(
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

