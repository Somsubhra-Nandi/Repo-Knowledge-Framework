"""
Token efficiency benchmark.
Compares naive context injection vs MCP graph queries
for the same architectural question.
"""

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

QUESTION = (
    "A bug is reported on the /api/users endpoint. "
    "Trace the full execution path from the React component "
    "to the database and identify which functions could be responsible."
)

FIXTURE_FILES = [
    "tests/fixtures/fullstack_app/backend/main.py",
    "tests/fixtures/fullstack_app/backend/users.py",
    "tests/fixtures/fullstack_app/frontend/UserComponent.tsx",
    "tests/fixtures/fullstack_app/frontend/api.ts",
]


def count_tokens_approx(text: str) -> int:
    """Approximate token count: ~4 chars per token."""
    return len(text) // 4


def naive_context() -> str:
    """Naive approach: dump all file contents."""
    parts = [f"Question: {QUESTION}\n\n"]
    for file_path in FIXTURE_FILES:
        try:
            content = Path(file_path).read_text(encoding="utf-8")
            parts.append(f"=== {file_path} ===\n{content}\n\n")
        except FileNotFoundError:
            parts.append(f"=== {file_path} === [NOT FOUND]\n\n")
    return "".join(parts)


def graph_context() -> str:
    """Graph approach: use MCP tools."""
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from graphrag.mcp.server import (
        find_data_lineage,
        trace_execution_flow,
        trace_network_boundary,
    )

    parts = [f"Question: {QUESTION}\n\n"]

    result1 = trace_network_boundary("/api/users")
    chains = result1.get("chains", [])
    parts.append("MCP graph trace:\n")

    if chains:
        chain = chains[0]
        frontend = chain["frontend"]
        route_call = chain["route_call"]
        backend_handler = chain["backend_handler"]
        handler_fqn = backend_handler["fqn"]

        parts.append(
            f"{frontend['method_name']} -> "
            f"{route_call['http_method']} {route_call['path']} -> "
            f"{backend_handler['name']}\n"
        )

        result2 = trace_execution_flow(handler_fqn, max_depth=3)
        parts.append(f"downstream_count: {result2.get('total_nodes', 0)}\n")

        result3 = find_data_lineage(handler_fqn, max_depth=4)
        db_nodes = [
            node["fqn"]
            for node in result3.get("lineage", [])
            if node.get("is_db_interaction")
        ]
        parts.append(f"db_interaction_count: {len(db_nodes)}\n")
    else:
        parts.append("chains: 0\n")

    return "".join(parts)


def main() -> None:
    print("=" * 60)
    print("GraphRAG Token Efficiency Benchmark")
    print("=" * 60)

    naive = naive_context()
    naive_tokens = count_tokens_approx(naive)
    print("\nNaive (raw file dump):")
    print(f"  Characters : {len(naive):,}")
    print(f"  Est. tokens: {naive_tokens:,}")

    try:
        graph = graph_context()
        graph_tokens = count_tokens_approx(graph)
        print("\nGraph (MCP tool queries):")
        print(f"  Characters : {len(graph):,}")
        print(f"  Est. tokens: {graph_tokens:,}")

        if naive_tokens > 0:
            reduction = (1 - graph_tokens / naive_tokens) * 100
            print(f"\nToken reduction: {reduction:.1f}%")
            print(f"Multiplier    : {naive_tokens / max(graph_tokens, 1):.1f}x more efficient")
    except Exception as exc:  # noqa: BLE001
        print(f"\nGraph query failed (Neo4j may not be running): {exc}")
        print(
            "Run 'docker compose up neo4j -d' and "
            "'graphrag ingest tests/fixtures/fullstack_app' first."
        )

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
