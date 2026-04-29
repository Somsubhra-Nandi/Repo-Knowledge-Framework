# Roadmap

## v1.0 - Current
Completed foundation and production readiness phases, including:
- Polyglot parsing for 15 languages
- Deterministic graph schema and Neo4j ingestion
- FQN-based symbol modeling with call/import edges
- Endpoint extraction and frontend route-call stitching
- MCP server and tooling across discovery, tracing, SDLC, history, and health
- CLI flows for ingest/status/reset
- Dockerized local stack
- Test coverage across parsers, stitching, ingestion, MCP, schema, and e2e
- Multi-repo namespacing with `repo_id`
- Per-file ingestion progress reporting
- Project documentation baseline

## v1.1 - Near Term
- Git SHA graph versioning (tag each graph state with commit hash)
- Named Neo4j databases for stronger repo isolation
- IDE extension (VS Code) with inline blast radius hints
- `graphrag diff` command to compare graph state across commits

## v1.2 - Medium Term
- Vector embeddings for semantic search (pgvector sidecar)
- GitHub Actions integration for auto-ingest on push
- Web UI for graph exploration and visualization
- Monorepo workspace support (Nx, Turborepo, Cargo workspaces)

## v2.0 - Long Term
- Multi-repo federation (stitch graphs across repositories)
- Real-time graph updates via LSP integration
- Cloud-hosted graph API
