from graphrag.graph.stitch import _normalize_path_params


def test_normalize_fastapi_params() -> None:
    assert _normalize_path_params("/api/users/{user_id}") == "/api/users/{param}"


def test_normalize_express_params() -> None:
    assert _normalize_path_params("/api/users/:id") == "/api/users/{param}"


def test_normalize_nextjs_params() -> None:
    assert _normalize_path_params("/api/users/[id]") == "/api/users/{param}"


def test_normalize_no_params() -> None:
    assert _normalize_path_params("/api/users") == "/api/users"


def test_normalize_multiple_params() -> None:
    result = _normalize_path_params("/api/{org}/users/{user_id}")
    assert result == "/api/{param}/users/{param}"
