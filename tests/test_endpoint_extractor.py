from graphrag.graph.endpoint_extractor import extract_endpoints
from graphrag.parser.factory import parse_file


def test_fastapi_get_endpoint_detected() -> None:
    parsed = parse_file("tests/fixtures/fastapi_app.py")
    endpoints = extract_endpoints(parsed)
    paths = {endpoint.path for endpoint in endpoints}
    assert "/health" in paths


def test_fastapi_all_methods_detected() -> None:
    parsed = parse_file("tests/fixtures/fastapi_app.py")
    endpoints = extract_endpoints(parsed)
    method_map = {endpoint.path: endpoint.http_method for endpoint in endpoints}
    assert method_map.get("/health") == "GET"
    assert method_map.get("/users") == "POST"


def test_fastapi_router_endpoints_detected() -> None:
    parsed = parse_file("tests/fixtures/fastapi_app.py")
    endpoints = extract_endpoints(parsed)
    paths = {endpoint.path for endpoint in endpoints}
    assert "/users/{user_id}" in paths


def test_fastapi_delete_endpoint_detected() -> None:
    parsed = parse_file("tests/fixtures/fastapi_app.py")
    endpoints = extract_endpoints(parsed)
    method_path_pairs = {(endpoint.http_method, endpoint.path) for endpoint in endpoints}
    assert ("DELETE", "/users/{user_id}") in method_path_pairs


def test_fastapi_handler_fqn_is_correct() -> None:
    parsed = parse_file("tests/fixtures/fastapi_app.py")
    endpoints = extract_endpoints(parsed)
    endpoint_map = {endpoint.path: endpoint for endpoint in endpoints if endpoint.http_method == "GET"}
    assert endpoint_map["/health"].handler_fqn.endswith("health_check")


def test_java_get_mapping_detected() -> None:
    parsed = parse_file("tests/fixtures/UserController.java")
    endpoints = extract_endpoints(parsed)
    paths = {endpoint.path for endpoint in endpoints}
    assert "/api/users" in paths


def test_java_post_mapping_detected() -> None:
    parsed = parse_file("tests/fixtures/UserController.java")
    endpoints = extract_endpoints(parsed)
    method_path_pairs = {(endpoint.http_method, endpoint.path) for endpoint in endpoints}
    assert ("POST", "/api/users") in method_path_pairs


def test_java_handler_fqn_is_correct() -> None:
    parsed = parse_file("tests/fixtures/UserController.java")
    endpoints = extract_endpoints(parsed)
    get_endpoint = next(endpoint for endpoint in endpoints if endpoint.http_method == "GET")
    assert "getUsers" in get_endpoint.handler_fqn


def test_express_get_endpoint_detected() -> None:
    parsed = parse_file("tests/fixtures/express_app.ts")
    endpoints = extract_endpoints(parsed)
    paths = {endpoint.path for endpoint in endpoints}
    assert "/health" in paths


def test_express_post_endpoint_detected() -> None:
    parsed = parse_file("tests/fixtures/express_app.ts")
    endpoints = extract_endpoints(parsed)
    method_path_pairs = {(endpoint.http_method, endpoint.path) for endpoint in endpoints}
    assert ("POST", "/users") in method_path_pairs


def test_express_router_endpoints_detected() -> None:
    parsed = parse_file("tests/fixtures/express_app.ts")
    endpoints = extract_endpoints(parsed)
    paths = {endpoint.path for endpoint in endpoints}
    assert "/users/:id" in paths


def test_all_endpoints_have_valid_http_methods() -> None:
    fixtures = [
        "tests/fixtures/fastapi_app.py",
        "tests/fixtures/UserController.java",
        "tests/fixtures/express_app.ts",
    ]
    for fixture in fixtures:
        parsed = parse_file(fixture)
        endpoints = extract_endpoints(parsed)
        for endpoint in endpoints:
            assert endpoint.http_method in {"GET", "POST", "PUT", "DELETE", "PATCH"}


def test_all_endpoints_have_non_empty_paths() -> None:
    fixtures = [
        "tests/fixtures/fastapi_app.py",
        "tests/fixtures/UserController.java",
        "tests/fixtures/express_app.ts",
    ]
    for fixture in fixtures:
        parsed = parse_file(fixture)
        endpoints = extract_endpoints(parsed)
        for endpoint in endpoints:
            assert endpoint.path.startswith("/")
