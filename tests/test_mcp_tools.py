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


def test_trace_execution_flow_returns_correct_shape() -> None:
    """trace_execution_flow returns dict with call_tree key"""
    from graphrag.mcp.server import trace_execution_flow

    mock_records = [
        {
            "callee_fqn": "a.b.c",
            "callee_name": "c",
            "callee_file": "a/b.py",
            "callee_line": 10,
            "depth": 1,
            "path_confidence": 0.9,
        }
    ]
    with patch("graphrag.mcp.server._run_records", return_value=mock_records):
        result = trace_execution_flow("some.fqn", max_depth=3)
    assert "call_tree" in result
    assert "root_fqn" in result
    assert result["root_fqn"] == "some.fqn"


def test_analyze_blast_radius_returns_correct_shape() -> None:
    from graphrag.mcp.server import analyze_blast_radius

    with patch("graphrag.mcp.server._run_records", return_value=[]):
        result = analyze_blast_radius("some.fqn")
    assert "affected_methods" in result
    assert "frontend_callers" in result
    assert result["target_fqn"] == "some.fqn"


def test_trace_network_boundary_returns_correct_shape() -> None:
    from graphrag.mcp.server import trace_network_boundary

    with patch("graphrag.mcp.server._run_records", return_value=[]):
        result = trace_network_boundary("/api/users")
    assert "chains" in result
    assert "query" in result


def test_find_data_lineage_returns_correct_shape() -> None:
    from graphrag.mcp.server import find_data_lineage

    mock_records = [
        {
            "fqn": "a.b",
            "name": "b",
            "file": "a.py",
            "language": "python",
            "source_code": "SELECT * FROM users",
            "depth": 1,
            "path_confidence": 1.0,
        }
    ]
    with patch("graphrag.mcp.server._run_records", return_value=mock_records):
        result = find_data_lineage("some.fqn")
    assert "lineage" in result
    assert result["lineage"][0]["is_db_interaction"] is True


def test_find_circular_dependencies_returns_correct_shape() -> None:
    from graphrag.mcp.server import find_circular_dependencies

    with patch("graphrag.mcp.server._run_records", return_value=[]):
        result = find_circular_dependencies()
    assert "cycles" in result
    assert "cycle_count" in result
    assert result["cycle_count"] == 0


def test_find_dead_code_returns_correct_shape() -> None:
    from graphrag.mcp.server import find_dead_code

    with patch("graphrag.mcp.server._run_records", return_value=[]):
        result = find_dead_code()
    assert "dead_methods" in result
    assert "total_dead_methods" in result
    assert result["total_dead_methods"] == 0


def test_identify_god_classes_returns_correct_shape() -> None:
    from graphrag.mcp.server import identify_god_classes

    mock_rows = [
        {
            "fqn": "a.B",
            "name": "B",
            "file": "a.py",
            "language": "python",
            "method_count": 15,
            "external_deps": 8,
            "complexity_score": 23,
        }
    ]
    with patch("graphrag.mcp.server._run_records", return_value=mock_rows):
        result = identify_god_classes()
    assert "god_classes" in result
    assert result["god_classes"][0]["complexity_score"] == 23


def test_check_architecture_drift_returns_correct_shape() -> None:
    from graphrag.mcp.server import check_architecture_drift

    with patch("graphrag.mcp.server._run_records", return_value=[]):
        result = check_architecture_drift()
    assert "violations" in result
    assert "rules_checked" in result
    assert result["total_violations"] == 0


def test_map_third_party_deps_returns_correct_shape() -> None:
    from graphrag.mcp.server import map_third_party_deps

    with patch("graphrag.mcp.server._run_records", return_value=[]):
        with patch(
            "graphrag.mcp.server._run_single",
            return_value={"affected_files": 0, "matched_packages": []},
        ):
            result = map_third_party_deps("fastapi")
    assert "affected_methods" in result
    assert "package_query" in result


def test_find_interface_violations_returns_correct_shape() -> None:
    from graphrag.mcp.server import find_interface_violations

    with patch("graphrag.mcp.server._run_records", return_value=[]):
        result = find_interface_violations()
    assert "violations" in result
    assert "total_violations" in result


def test_estimate_migration_cost_returns_effort_estimate() -> None:
    from graphrag.mcp.server import estimate_migration_cost

    mock_summary = {"method_count": 5, "file_count": 3, "sample_files": []}
    mock_callers = {"dependent_callers": 2}
    with patch("graphrag.mcp.server._run_single", side_effect=[mock_summary, mock_callers]):
        result = estimate_migration_cost("requests", "httpx")
    assert "migration_cost" in result
    assert result["migration_cost"]["effort_estimate"] in {
        "LOW",
        "MEDIUM",
        "HIGH",
        "VERY HIGH",
    }
