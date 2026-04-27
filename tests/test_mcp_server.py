import os

import pytest
from dotenv import load_dotenv
from neo4j import GraphDatabase

from graphrag.mcp.server import explore_architecture, find_endpoints, get_file_context

load_dotenv()


@pytest.fixture(scope="module", autouse=True)
def ensure_neo4j_available() -> None:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "neo4j_password")
    driver = GraphDatabase.driver(uri, auth=(username, password))
    try:
        driver.verify_connectivity()
    except Exception as exc:  # noqa: BLE001
        driver.close()
        pytest.skip(f"Neo4j is not reachable for MCP server test: {exc}")
    driver.close()


def test_explore_architecture_returns_correct_shape() -> None:
    """explore_architecture returns dict with required keys"""
    result = explore_architecture(repo_root="")
    assert isinstance(result, dict)
    assert "languages" in result
    assert "totals" in result
    assert "top_packages" in result
    assert isinstance(result["languages"], dict)
    assert isinstance(result["totals"], dict)
    assert "files" in result["totals"]
    assert "classes" in result["totals"]
    assert "methods" in result["totals"]
    assert "endpoints" in result["totals"]


def test_explore_architecture_totals_are_integers() -> None:
    result = explore_architecture(repo_root="")
    for key, value in result["totals"].items():
        assert isinstance(value, int), f"totals.{key} should be int, got {type(value)}"


def test_explore_architecture_with_repo_root_filter() -> None:
    """Passing a non-existent repo_root returns zeros, not an error"""
    result = explore_architecture(repo_root="/nonexistent/path")
    assert result["totals"]["files"] == 0


def test_find_endpoints_returns_correct_shape() -> None:
    result = find_endpoints(keyword="")
    assert isinstance(result, dict)
    assert "endpoints" in result
    assert "count" in result
    assert isinstance(result["endpoints"], list)
    assert result["count"] == len(result["endpoints"])


def test_find_endpoints_each_item_has_required_fields() -> None:
    result = find_endpoints(keyword="")
    for endpoint in result["endpoints"]:
        assert "path" in endpoint
        assert "http_method" in endpoint
        assert "handler_fqn" in endpoint
        assert "language" in endpoint


def test_find_endpoints_keyword_filter() -> None:
    """Keyword filter reduces results"""
    all_results = find_endpoints(keyword="")
    filtered = find_endpoints(keyword="xyznonexistent123")
    assert all_results["count"] >= filtered["count"]
    assert filtered["count"] == 0
    assert len(filtered["endpoints"]) == 0


def test_get_file_context_returns_correct_shape() -> None:
    """get_file_context with known file returns correct structure"""
    result = get_file_context(file_path="sample.py")
    assert isinstance(result, dict)
    assert "file" in result or result.get("error") is not None


def test_get_file_context_unknown_file_returns_error() -> None:
    result = get_file_context(file_path="nonexistent_xyz_123.py")
    assert "error" in result


def test_get_file_context_has_required_keys_when_found() -> None:
    result = get_file_context(file_path="sample.py")
    if "error" not in result:
        assert "classes" in result
        assert "methods" in result
        assert "imports" in result
        assert isinstance(result["classes"], list)
        assert isinstance(result["methods"], list)
