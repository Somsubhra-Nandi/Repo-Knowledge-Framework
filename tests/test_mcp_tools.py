import importlib
from unittest.mock import MagicMock, patch

from graphrag.mcp.tools.discovery import (
    explore_architecture,
    find_by_fqn,
    find_endpoints,
    get_file_context,
    search_ontology,
)


def test_discovery_tools_are_importable() -> None:
    assert callable(explore_architecture)
    assert callable(get_file_context)
    assert callable(find_endpoints)
    assert callable(find_by_fqn)
    assert callable(search_ontology)


def test_server_import_does_not_create_driver() -> None:
    with patch("neo4j.GraphDatabase.driver") as mock_driver:
        server = importlib.reload(importlib.import_module("graphrag.mcp.server"))

    assert server._driver is None
    mock_driver.assert_not_called()


def test_get_driver_is_lazy_and_cached() -> None:
    fake_driver = MagicMock()

    with patch("neo4j.GraphDatabase.driver", return_value=fake_driver) as mock_driver:
        server = importlib.reload(importlib.import_module("graphrag.mcp.server"))
        first = server._get_driver()
        second = server._get_driver()

    assert first is fake_driver
    assert second is fake_driver
    mock_driver.assert_called_once()


def test_find_by_fqn_returns_expected_shape() -> None:
    server = importlib.import_module("graphrag.mcp.server")
    with (
        patch.object(
            server,
            "_run_single",
            return_value={
                "node_type": "Method",
                "fqn": "pkg.module.fn",
                "name": "fn",
                "file": "pkg/module.py",
                "line": 12,
                "signature": "def fn()",
            },
        ),
        patch.object(
            server,
            "_run_records",
            side_effect=[
                [{"fqn": "pkg.caller", "name": "caller", "file": "x.py", "line": 8}],
                [{"fqn": "pkg.callee", "name": "callee", "file": "y.py", "line": 20}],
            ],
        ),
    ):
        result = server.find_by_fqn("pkg.module.fn")

    assert result["query"] == "pkg.module.fn"
    assert result["match"]["node_type"] == "Method"
    assert isinstance(result["callers"], list)
    assert isinstance(result["callees"], list)


def test_search_ontology_returns_expected_shape() -> None:
    server = importlib.import_module("graphrag.mcp.server")
    with patch.object(
        server,
        "_run_records",
        return_value=[
            {
                "node_type": "Class",
                "identifier": "pkg.Service",
                "name": "Service",
                "path": None,
                "file": "pkg/service.py",
                "line": 10,
            }
        ],
    ):
        result = server.search_ontology("Service")

    assert result["keyword"] == "Service"
    assert result["count"] == 1
    assert result["results"][0]["node_type"] == "Class"
