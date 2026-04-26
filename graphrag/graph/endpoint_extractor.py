"""Endpoint extraction from parsed files."""

from __future__ import annotations

import re
from pathlib import Path

from graphrag.parser.factory import MethodInfo, ParsedFile
from graphrag.schema.models import EndpointNode, build_fqn

HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "DELETE", "PATCH"}

PYTHON_ROUTE_PATTERN = re.compile(
    r'@[\w\.]+\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
FLASK_ROUTE_PATTERN = re.compile(
    r'@[\w\.]+\.route\s*\(\s*["\']([^"\']+)["\'].*?methods\s*=\s*\[([^\]]+)\]',
    re.IGNORECASE,
)

JAVA_MAPPING_PATTERN = re.compile(
    r'@(Get|Post|Put|Delete|Patch)Mapping\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
JAVA_REQUEST_MAPPING_PATTERN = re.compile(
    r'@RequestMapping\s*\([^)]*value\s*=\s*["\']([^"\']+)["\'][^)]*'
    r'method\s*=\s*RequestMethod\.(\w+)',
    re.IGNORECASE | re.DOTALL,
)
JAVA_CLASS_REQUEST_MAPPING_PATTERN = re.compile(
    r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']',
    re.IGNORECASE,
)

EXPRESS_PATTERN = re.compile(
    r'(?:\bapp\b|\brouter\b)\.(get|post|put|delete|patch)\s*\(\s*["\'`]([^"\'`]+)["\'`]',
    re.IGNORECASE,
)
NESTJS_PATTERN = re.compile(
    r'@(Get|Post|Put|Delete|Patch)\s*\(\s*["\']([^"\']*)["\']',
    re.IGNORECASE,
)


def extract_endpoints(parsed_file: ParsedFile) -> list[EndpointNode]:
    """
    Detect HTTP route handler methods in a parsed file and return endpoint nodes.
    """
    if parsed_file.language == "python":
        return _extract_python_endpoints(parsed_file)
    if parsed_file.language == "java":
        return _extract_java_endpoints(parsed_file)
    if parsed_file.language in {"typescript", "javascript"}:
        return _extract_typescript_endpoints(parsed_file)
    return []


def _normalize_path(path: str) -> str:
    trimmed = path.strip()
    if not trimmed:
        return "/"
    if not trimmed.startswith("/"):
        return f"/{trimmed}"
    return trimmed


def _join_paths(prefix: str, path: str) -> str:
    normalized_prefix = _normalize_path(prefix)
    normalized_path = _normalize_path(path)
    if normalized_prefix == "/":
        return normalized_path
    if normalized_path == "/":
        return normalized_prefix
    return f"{normalized_prefix.rstrip('/')}/{normalized_path.lstrip('/')}"


def _extract_python_endpoints(parsed_file: ParsedFile) -> list[EndpointNode]:
    source_lines = Path(parsed_file.path).read_text(encoding="utf-8").splitlines()
    endpoints: list[EndpointNode] = []
    seen: set[tuple[str, str, str]] = set()

    for method_info in parsed_file.methods:
        start_index = max(0, method_info.line - 6)
        end_index = max(0, method_info.line - 1)
        decorator_lines = source_lines[start_index:end_index]
        decorator_block = "\n".join(line.strip() for line in decorator_lines if line.strip().startswith("@"))
        if not decorator_block:
            continue

        for match in PYTHON_ROUTE_PATTERN.finditer(decorator_block):
            http_method = match.group(1).upper()
            path = _normalize_path(match.group(2))
            key = (path, http_method, method_info.fqn)
            if key in seen:
                continue
            seen.add(key)
            endpoints.append(
                EndpointNode(
                    path=path,
                    http_method=http_method,
                    handler_fqn=method_info.fqn,
                    language="python",
                    file=parsed_file.path,
                    line=method_info.line,
                )
            )

        for match in FLASK_ROUTE_PATTERN.finditer(decorator_block):
            path = _normalize_path(match.group(1))
            methods_text = match.group(2)
            methods = re.findall(r'["\'](GET|POST|PUT|DELETE|PATCH)["\']', methods_text, re.IGNORECASE)
            for method in methods:
                http_method = method.upper()
                key = (path, http_method, method_info.fqn)
                if key in seen:
                    continue
                seen.add(key)
                endpoints.append(
                    EndpointNode(
                        path=path,
                        http_method=http_method,
                        handler_fqn=method_info.fqn,
                        language="python",
                        file=parsed_file.path,
                        line=method_info.line,
                    )
                )

    return endpoints


def _extract_java_class_prefixes(parsed_file: ParsedFile, source_lines: list[str]) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for class_info in parsed_file.classes:
        start_index = max(0, class_info.line - 6)
        end_index = min(len(source_lines), class_info.line + 4)
        annotation_block = "\n".join(source_lines[start_index:end_index])
        match = JAVA_CLASS_REQUEST_MAPPING_PATTERN.search(annotation_block)
        if match is None:
            continue
        prefixes[class_info.name] = _normalize_path(match.group(1))
    return prefixes


def _extract_java_endpoints(parsed_file: ParsedFile) -> list[EndpointNode]:
    source_lines = Path(parsed_file.path).read_text(encoding="utf-8").splitlines()
    class_prefixes = _extract_java_class_prefixes(parsed_file, source_lines)
    endpoints: list[EndpointNode] = []
    seen: set[tuple[str, str, str]] = set()

    for method_info in parsed_file.methods:
        signature = method_info.signature
        class_prefix = class_prefixes.get(method_info.class_name or "", "")

        for match in JAVA_MAPPING_PATTERN.finditer(signature):
            http_method = match.group(1).upper()
            path = _normalize_path(match.group(2))
            full_path = _join_paths(class_prefix, path) if class_prefix else path
            key = (full_path, http_method, method_info.fqn)
            if key in seen:
                continue
            seen.add(key)
            endpoints.append(
                EndpointNode(
                    path=full_path,
                    http_method=http_method,
                    handler_fqn=method_info.fqn,
                    language="java",
                    file=parsed_file.path,
                    line=method_info.line,
                )
            )

        for match in JAVA_REQUEST_MAPPING_PATTERN.finditer(signature):
            path = _normalize_path(match.group(1))
            http_method = match.group(2).upper()
            if http_method not in HTTP_METHODS:
                continue
            full_path = _join_paths(class_prefix, path) if class_prefix else path
            key = (full_path, http_method, method_info.fqn)
            if key in seen:
                continue
            seen.add(key)
            endpoints.append(
                EndpointNode(
                    path=full_path,
                    http_method=http_method,
                    handler_fqn=method_info.fqn,
                    language="java",
                    file=parsed_file.path,
                    line=method_info.line,
                )
            )

    return endpoints


def _nearest_handler_fqn(methods: list[MethodInfo], module_name: str, line: int) -> tuple[str, int]:
    if not methods:
        synthetic = build_fqn(module_name, f"handler_line_{line}")
        return synthetic, line

    nearest = min(methods, key=lambda item: abs(item.line - line))
    return nearest.fqn, nearest.line


def _extract_typescript_endpoints(parsed_file: ParsedFile) -> list[EndpointNode]:
    source_text = Path(parsed_file.path).read_text(encoding="utf-8")
    endpoints: list[EndpointNode] = []
    seen: set[tuple[str, str, str]] = set()

    for method_info in parsed_file.methods:
        for match in NESTJS_PATTERN.finditer(method_info.source_code):
            http_method = match.group(1).upper()
            path = _normalize_path(match.group(2) or "/")
            key = (path, http_method, method_info.fqn)
            if key in seen:
                continue
            seen.add(key)
            endpoints.append(
                EndpointNode(
                    path=path,
                    http_method=http_method,
                    handler_fqn=method_info.fqn,
                    language=parsed_file.language,
                    file=parsed_file.path,
                    line=method_info.line,
                )
            )

    for match in EXPRESS_PATTERN.finditer(source_text):
        http_method = match.group(1).upper()
        path = _normalize_path(match.group(2))
        line = source_text[: match.start()].count("\n") + 1
        handler_fqn, handler_line = _nearest_handler_fqn(parsed_file.methods, parsed_file.module_name, line)
        key = (path, http_method, handler_fqn)
        if key in seen:
            continue
        seen.add(key)
        endpoints.append(
            EndpointNode(
                path=path,
                http_method=http_method,
                handler_fqn=handler_fqn,
                language=parsed_file.language,
                file=parsed_file.path,
                line=handler_line,
            )
        )

    return endpoints
