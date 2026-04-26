"""Route call extraction from frontend source files."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from graphrag.parser.factory import MethodInfo, ParsedFile
from graphrag.schema.models import build_fqn

FETCH_PATTERN = re.compile(
    r'\bfetch\s*\(\s*(["\'])(\/[^"\']+)\1'
    r'(?:\s*,\s*\{[^}]*method\s*:\s*["\'](\w+)["\'])?',
    re.IGNORECASE | re.DOTALL,
)
FETCH_TEMPLATE_PATTERN = re.compile(
    r'\bfetch\s*\(\s*`(\/[^`]+)`'
    r'(?:\s*,\s*\{[^}]*method\s*:\s*["\'](\w+)["\'])?',
    re.IGNORECASE | re.DOTALL,
)
AXIOS_METHOD_PATTERN = re.compile(
    r'\baxios\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)
AXIOS_CONFIG_PATTERN = re.compile(
    r'\baxios\s*\(\s*\{[^}]*method\s*:\s*["\'](\w+)["\'][^}]*url\s*:\s*["\']([^"\']+)["\']',
    re.IGNORECASE | re.DOTALL,
)
TEMPLATE_PATH_PATTERN = re.compile(
    r'\b(?:axios\.(get|post|put|delete|patch)|fetch)\s*\(\s*`(\/[^`]+)`',
    re.IGNORECASE,
)
HTTP_CLIENT_PATTERN = re.compile(
    r'\b(?:api|http|apiClient|client|request|httpClient)\.'
    r'(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

VALID_HTTP_METHODS: set[str] = {"GET", "POST", "PUT", "DELETE", "PATCH"}


@dataclass
class RouteCall:
    """An outgoing HTTP API call detected in frontend source code."""

    source_method_fqn: str
    path: str
    http_method: str
    confidence: float
    line: int
    source_file: str


def _normalize_path(path: str) -> str:
    cleaned = path.strip()
    if not cleaned.startswith("/"):
        return f"/{cleaned}"
    return cleaned


def _line_from_offset(text: str, base_line: int, match_offset: int) -> int:
    return base_line + text[:match_offset].count("\n")


def _add_call(
    calls: list[RouteCall],
    seen: set[tuple[str, str, str]],
    source_method_fqn: str,
    path: str,
    http_method: str,
    confidence: float,
    line: int,
    source_file: str,
) -> None:
    method = http_method.upper()
    if method not in VALID_HTTP_METHODS:
        return
    normalized_path = _normalize_path(path)
    key = (source_method_fqn, normalized_path, method)
    if key in seen:
        return
    seen.add(key)
    calls.append(
        RouteCall(
            source_method_fqn=source_method_fqn,
            path=normalized_path,
            http_method=method,
            confidence=confidence,
            line=line,
            source_file=source_file,
        )
    )


def _extract_from_text(
    text: str,
    source_method_fqn: str,
    base_line: int,
    source_file: str,
    calls: list[RouteCall],
    seen: set[tuple[str, str, str]],
) -> None:
    for match in FETCH_PATTERN.finditer(text):
        path = match.group(2)
        method = match.group(3) or "GET"
        line = _line_from_offset(text, base_line, match.start())
        _add_call(calls, seen, source_method_fqn, path, method, 1.0, line, source_file)

    for match in FETCH_TEMPLATE_PATTERN.finditer(text):
        path = match.group(1)
        method = match.group(2) or "GET"
        line = _line_from_offset(text, base_line, match.start())
        _add_call(calls, seen, source_method_fqn, path, method, 0.5, line, source_file)

    for match in AXIOS_METHOD_PATTERN.finditer(text):
        method = match.group(1)
        path = match.group(2)
        line = _line_from_offset(text, base_line, match.start())
        _add_call(calls, seen, source_method_fqn, path, method, 1.0, line, source_file)

    for match in AXIOS_CONFIG_PATTERN.finditer(text):
        method = match.group(1)
        path = match.group(2)
        line = _line_from_offset(text, base_line, match.start())
        _add_call(calls, seen, source_method_fqn, path, method, 1.0, line, source_file)

    for match in TEMPLATE_PATH_PATTERN.finditer(text):
        raw_method = match.group(1)
        if raw_method is None:
            continue
        method = raw_method
        path = match.group(2)
        line = _line_from_offset(text, base_line, match.start())
        _add_call(calls, seen, source_method_fqn, path, method, 0.5, line, source_file)

    for match in HTTP_CLIENT_PATTERN.finditer(text):
        method = match.group(1)
        path = match.group(2)
        line = _line_from_offset(text, base_line, match.start())
        _add_call(calls, seen, source_method_fqn, path, method, 1.0, line, source_file)


def _extract_for_method(
    method_info: MethodInfo,
    source_file: str,
    calls: list[RouteCall],
    seen: set[tuple[str, str, str]],
) -> None:
    _extract_from_text(
        text=method_info.source_code,
        source_method_fqn=method_info.fqn,
        base_line=method_info.line,
        source_file=source_file,
        calls=calls,
        seen=seen,
    )


def extract_route_calls(parsed_file: ParsedFile) -> list[RouteCall]:
    """
    Detect outgoing HTTP API calls in a frontend source file.
    Supports TypeScript and JavaScript files only.
    """
    if parsed_file.language not in {"typescript", "javascript"}:
        return []

    calls: list[RouteCall] = []
    seen: set[tuple[str, str, str]] = set()

    for method_info in parsed_file.methods:
        _extract_for_method(method_info, parsed_file.path, calls, seen)

    source_text = Path(parsed_file.path).read_text(encoding="utf-8")
    module_level_fqn = build_fqn(parsed_file.module_name, "module_level")
    _extract_from_text(
        text=source_text,
        source_method_fqn=module_level_fqn,
        base_line=1,
        source_file=parsed_file.path,
        calls=calls,
        seen=seen,
    )

    return calls
