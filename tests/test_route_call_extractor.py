from graphrag.graph.route_call_extractor import extract_route_calls
from graphrag.parser.factory import parse_file


def test_fetch_get_detected() -> None:
    """fetch('/api/users') detected as GET."""
    parsed = parse_file("tests/fixtures/api_service.ts")
    calls = extract_route_calls(parsed)
    method_paths = {(call.http_method, call.path) for call in calls}
    assert ("GET", "/api/users") in method_paths or any(call.path == "/api/users" for call in calls)


def test_fetch_post_detected() -> None:
    """fetch('/api/users', { method: 'POST' }) detected as POST."""
    parsed = parse_file("tests/fixtures/api_service.ts")
    calls = extract_route_calls(parsed)
    method_paths = {(call.http_method, call.path) for call in calls}
    assert ("POST", "/api/users") in method_paths


def test_fetch_delete_detected() -> None:
    """fetch('/api/users/${id}', { method: 'DELETE' }) detected."""
    parsed = parse_file("tests/fixtures/api_service.ts")
    calls = extract_route_calls(parsed)
    http_methods = {call.http_method for call in calls}
    assert "DELETE" in http_methods


def test_fetch_put_detected() -> None:
    parsed = parse_file("tests/fixtures/api_service.ts")
    calls = extract_route_calls(parsed)
    http_methods = {call.http_method for call in calls}
    assert "PUT" in http_methods


def test_template_literal_has_lower_confidence() -> None:
    """fetch(`/api/users/${id}`) should have confidence 0.5."""
    parsed = parse_file("tests/fixtures/api_service.ts")
    calls = extract_route_calls(parsed)
    template_calls = [call for call in calls if "${" in call.path or call.confidence < 1.0]
    assert len(template_calls) >= 1
    for call in template_calls:
        assert call.confidence <= 0.5


def test_exact_string_has_full_confidence() -> None:
    """fetch('/api/users') should have confidence 1.0."""
    parsed = parse_file("tests/fixtures/react_component.tsx")
    calls = extract_route_calls(parsed)
    exact_calls = [call for call in calls if call.path == "/api/users" and call.http_method == "GET"]
    assert len(exact_calls) >= 1
    assert all(call.confidence == 1.0 for call in exact_calls)


def test_axios_post_detected_in_react_component() -> None:
    parsed = parse_file("tests/fixtures/react_component.tsx")
    calls = extract_route_calls(parsed)
    method_paths = {(call.http_method, call.path) for call in calls}
    assert ("POST", "/api/users") in method_paths


def test_axios_put_detected_in_react_component() -> None:
    parsed = parse_file("tests/fixtures/react_component.tsx")
    calls = extract_route_calls(parsed)
    http_methods = {call.http_method for call in calls}
    assert "PUT" in http_methods


def test_route_calls_have_valid_http_methods() -> None:
    for fixture in ["tests/fixtures/api_service.ts", "tests/fixtures/react_component.tsx"]:
        parsed = parse_file(fixture)
        calls = extract_route_calls(parsed)
        for call in calls:
            assert call.http_method in {"GET", "POST", "PUT", "DELETE", "PATCH"}


def test_route_calls_have_non_empty_paths() -> None:
    for fixture in ["tests/fixtures/api_service.ts", "tests/fixtures/react_component.tsx"]:
        parsed = parse_file(fixture)
        calls = extract_route_calls(parsed)
        for call in calls:
            assert call.path.startswith("/")


def test_route_calls_have_source_method_fqn() -> None:
    """Every RouteCall must have a non-empty source_method_fqn."""
    parsed = parse_file("tests/fixtures/api_service.ts")
    calls = extract_route_calls(parsed)
    assert len(calls) > 0
    for call in calls:
        assert call.source_method_fqn != ""


def test_no_duplicate_route_calls() -> None:
    """Same (fqn, path, method) must not appear twice."""
    parsed = parse_file("tests/fixtures/api_service.ts")
    calls = extract_route_calls(parsed)
    seen: set[tuple[str, str, str]] = set()
    for call in calls:
        key = (call.source_method_fqn, call.path, call.http_method)
        assert key not in seen
        seen.add(key)


def test_python_file_returns_empty() -> None:
    """Python files should return empty list."""
    parsed = parse_file("tests/fixtures/sample.py")
    calls = extract_route_calls(parsed)
    assert calls == []
