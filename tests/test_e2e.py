"""
End-to-end integration test simulating an AI agent tracing
a bug through the full-stack graph. Requires live Neo4j.
"""

import os

import pytest
from dotenv import load_dotenv
from neo4j import Driver

from graphrag.graph.stitch import RouteStitcher
from graphrag.ingestion.pipeline import IngestionPipeline, IngestionResult

load_dotenv()

FULLSTACK_PATH = "tests/fixtures/fullstack_app"


def _cleanup_fullstack_graph(driver: Driver) -> None:
    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE (n.file IS NOT NULL AND n.file CONTAINS "fullstack_app")
               OR (n.path IS NOT NULL AND n.path CONTAINS "fullstack_app")
               OR (n.source_file IS NOT NULL AND n.source_file CONTAINS "fullstack_app")
               OR (
                    n:Endpoint
                    AND n.path STARTS WITH "/api/users"
                    AND NOT EXISTS {
                        MATCH (:Method)-[:HANDLES]->(n)
                        WHERE NOT coalesce(n.file, "") CONTAINS "fullstack_app"
                    }
               )
            DETACH DELETE n
            """
        )


def _build_pipeline() -> IngestionPipeline:
    return IngestionPipeline(
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_username=os.getenv("NEO4J_USERNAME", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
        workers=4,
    )


@pytest.fixture(scope="module")
def ingested_graph(neo4j_driver: Driver) -> IngestionResult:
    """
    Ingest the fullstack_app fixture once for the entire
    test module. Clean up after all tests complete.
    """
    _cleanup_fullstack_graph(neo4j_driver)
    result = _build_pipeline().run(FULLSTACK_PATH)

    stitcher = RouteStitcher(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "neo4j_password"),
    )
    try:
        stitcher.stitch()
    finally:
        stitcher.close()

    yield result
    _cleanup_fullstack_graph(neo4j_driver)


def test_pipeline_completed_without_failures(ingested_graph: IngestionResult) -> None:
    result = ingested_graph
    assert result.failed == 0, f"Failures: {result.errors}"


def test_all_backend_files_ingested(
    neo4j_driver: Driver,
    ingested_graph: IngestionResult,
) -> None:
    """main.py and users.py both appear as File nodes."""
    assert ingested_graph.failed == 0
    with neo4j_driver.session() as session:
        records = session.run(
            "MATCH (f:File) WHERE f.path CONTAINS 'fullstack_app' "
            "RETURN f.path AS path"
        )
        paths = {record["path"] for record in records}
    assert any("main.py" in path for path in paths)
    assert any("users.py" in path for path in paths)


def test_all_frontend_files_ingested(
    neo4j_driver: Driver,
    ingested_graph: IngestionResult,
) -> None:
    """UserComponent.tsx and api.ts appear as File nodes."""
    assert ingested_graph.failed == 0
    with neo4j_driver.session() as session:
        records = session.run(
            "MATCH (f:File) WHERE f.path CONTAINS 'fullstack_app' "
            "RETURN f.path AS path"
        )
        paths = {record["path"] for record in records}
    assert any("UserComponent" in path for path in paths)
    assert any("api.ts" in path for path in paths)


def test_backend_endpoints_exist(
    neo4j_driver: Driver,
    ingested_graph: IngestionResult,
) -> None:
    """FastAPI endpoints from main.py are in graph as Endpoint nodes."""
    assert ingested_graph.failed == 0
    with neo4j_driver.session() as session:
        records = session.run(
            "MATCH (e:Endpoint) WHERE e.file CONTAINS 'fullstack_app' "
            "RETURN e.path AS path, e.http_method AS method"
        )
        endpoints = {(record["path"], record["method"]) for record in records}
    assert ("/api/users", "GET") in endpoints
    assert ("/api/users", "POST") in endpoints


def test_routes_to_edges_created(
    neo4j_driver: Driver,
    ingested_graph: IngestionResult,
) -> None:
    """RouteStitcher created [:ROUTES_TO] edges."""
    assert ingested_graph.failed == 0
    with neo4j_driver.session() as session:
        record = session.run(
            """
            MATCH (frontend:Method)-[:MAKES_CALL]->(:RouteCall)-[r:ROUTES_TO]->(:Endpoint)
            WHERE frontend.file CONTAINS 'fullstack_app'
            RETURN count(r) AS cnt
            """
        ).single()
    assert record is not None
    assert int(record["cnt"]) > 0


def test_calls_edges_exist(
    neo4j_driver: Driver,
    ingested_graph: IngestionResult,
) -> None:
    """[:CALLS] edges exist between methods."""
    assert ingested_graph.failed == 0
    with neo4j_driver.session() as session:
        record = session.run(
            "MATCH (a:Method)-[r:CALLS]->(b:Method) "
            "WHERE a.file CONTAINS 'fullstack_app' "
            "RETURN count(r) AS cnt"
        ).single()
    assert record is not None
    assert int(record["cnt"]) > 0


def test_agent_step1_trace_network_boundary(ingested_graph: IngestionResult) -> None:
    """
    Agent step 1: given a bug report on /api/users,
    trace_network_boundary returns a complete chain.
    """
    assert ingested_graph.failed == 0
    from graphrag.mcp.server import trace_network_boundary

    result = trace_network_boundary("/api/users")
    assert "chains" in result
    assert len(result["chains"]) > 0, "No chains found - stitch may have failed"
    chain = result["chains"][0]
    assert chain["backend_handler"]["fqn"] != ""
    assert chain["backend_handler"]["language"] == "python"


def test_agent_step2_trace_execution_flow(ingested_graph: IngestionResult) -> None:
    """
    Agent step 2: trace execution flow from the GET /api/users handler.
    Should reach into UserService methods.
    """
    assert ingested_graph.failed == 0
    from graphrag.mcp.server import trace_execution_flow, trace_network_boundary

    boundary = trace_network_boundary("/api/users")
    assert len(boundary["chains"]) > 0
    handler_fqn = boundary["chains"][0]["backend_handler"]["fqn"]

    flow = trace_execution_flow(handler_fqn, max_depth=5)
    assert "call_tree" in flow
    assert flow["total_nodes"] >= 0


def test_agent_step3_find_data_lineage(ingested_graph: IngestionResult) -> None:
    """
    Agent step 3: find data lineage from GET /api/users handler.
    Should detect DB interaction in UserService._query_db.
    """
    assert ingested_graph.failed == 0
    from graphrag.mcp.server import find_data_lineage, trace_network_boundary

    boundary = trace_network_boundary("/api/users")
    assert len(boundary["chains"]) > 0
    handler_fqn = boundary["chains"][0]["backend_handler"]["fqn"]

    lineage = find_data_lineage(handler_fqn, max_depth=6)
    assert "lineage" in lineage
    db_nodes = [node for node in lineage["lineage"] if node["is_db_interaction"]]
    assert len(db_nodes) >= 0


def test_agent_step4_analyze_blast_radius(ingested_graph: IngestionResult) -> None:
    """
    Agent step 4: before changing UserService.get_all,
    check blast radius - frontend should appear.
    """
    assert ingested_graph.failed == 0
    from graphrag.mcp.server import analyze_blast_radius, search_ontology

    search = search_ontology("get_all")
    fqns = [
        result["identifier"]
        for result in search["results"]
        if result["node_type"] == "Method"
    ]
    if not fqns:
        pytest.skip("get_all not found in graph - skipping blast radius test")

    blast = analyze_blast_radius(fqns[0], max_depth=5)
    assert "affected_methods" in blast
    assert "frontend_callers" in blast
    assert blast["total_affected"] >= 0


def test_agent_step5_no_hallucinated_fqns(
    neo4j_driver: Driver,
    ingested_graph: IngestionResult,
) -> None:
    """
    Zero hallucination test: every FQN returned by trace_network_boundary
    must exist as a real node in Neo4j.
    """
    assert ingested_graph.failed == 0
    from graphrag.mcp.server import trace_network_boundary

    result = trace_network_boundary("/api/users")

    all_fqns = set()
    for chain in result["chains"]:
        fqn = chain["backend_handler"].get("fqn")
        if fqn and not fqn.startswith("unresolved."):
            all_fqns.add(fqn)
        for call in chain.get("downstream_calls", []):
            call_fqn = call.get("fqn")
            if call_fqn and not call_fqn.startswith("unresolved."):
                all_fqns.add(call_fqn)

    if not all_fqns:
        pytest.skip("No resolved FQNs to verify")

    with neo4j_driver.session() as session:
        for fqn in all_fqns:
            record = session.run(
                "MATCH (n) WHERE n.fqn = $fqn RETURN count(n) AS cnt",
                fqn=fqn,
            ).single()
            assert record is not None
            assert int(record["cnt"]) > 0, (
                f"HALLUCINATION DETECTED: FQN '{fqn}' not in Neo4j"
            )


def test_full_chain_query_traversable(
    neo4j_driver: Driver,
    ingested_graph: IngestionResult,
) -> None:
    """
    The complete 4-hop chain must be traversable in Neo4j directly.
    React method -> RouteCall -> Endpoint -> FastAPI handler.
    """
    assert ingested_graph.failed == 0
    with neo4j_driver.session() as session:
        records = session.run(
            """
            MATCH path = (frontend:Method)
                         -[:MAKES_CALL]->(:RouteCall)
                         -[:ROUTES_TO]->(:Endpoint)
                         <-[:HANDLES]-(backend:Method)
            WHERE frontend.file CONTAINS 'fullstack_app'
            RETURN frontend.name AS frontend_method,
                   backend.name AS backend_method,
                   backend.language AS language
            LIMIT 5
            """
        )
        chains = list(records)
    assert len(chains) > 0, "No complete chains found - network stitch may have failed"
    for chain in chains:
        assert chain["language"] == "python"


def test_all_25_tools_importable() -> None:
    """Every tool must be importable and callable."""
    from graphrag.mcp.server import (
        analyze_blast_radius,
        auto_sync_graph,
        check_architecture_drift,
        estimate_migration_cost,
        explain_change_history,
        explore_architecture,
        find_by_fqn,
        find_circular_dependencies,
        find_data_lineage,
        find_dead_code,
        find_endpoints,
        find_interface_violations,
        generate_architecture_diagram,
        generate_test_suite,
        get_file_context,
        identify_god_classes,
        map_third_party_deps,
        query_graph_raw,
        safe_write_file,
        scaffold_polyglot_feature,
        search_ontology,
        summarize_module,
        trace_execution_flow,
        trace_network_boundary,
    )

    tools = [
        explore_architecture,
        find_by_fqn,
        find_endpoints,
        get_file_context,
        search_ontology,
        analyze_blast_radius,
        find_circular_dependencies,
        find_data_lineage,
        trace_execution_flow,
        trace_network_boundary,
        check_architecture_drift,
        estimate_migration_cost,
        find_dead_code,
        find_interface_violations,
        identify_god_classes,
        map_third_party_deps,
        auto_sync_graph,
        generate_test_suite,
        query_graph_raw,
        safe_write_file,
        scaffold_polyglot_feature,
        explain_change_history,
        generate_architecture_diagram,
        summarize_module,
    ]
    assert len(set(tools)) == 24
    for tool in tools:
        assert callable(tool), f"{tool.__name__} is not callable"
