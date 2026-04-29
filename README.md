# Polyglot GraphRAG MCP Server

**Give AI agents deterministic, mathematical ground truth about your codebase.**

![Python](https://img.shields.io/badge/python-3.12-blue)
![Neo4j](https://img.shields.io/badge/neo4j-5.x-green)
![Languages](https://img.shields.io/badge/languages-15-orange)
![MCP](https://img.shields.io/badge/MCP-compatible-purple)
![License](https://img.shields.io/badge/license-MIT-blue)

---

Cursor and Claude Code are excellent at writing code. They are terrible at *understanding* it.

They use vector search over file chunks. That means they guess at call paths, confuse identically-named functions across modules, and hallucinate architecture details that don't exist in your repo. The larger the codebase, the worse it gets.

This server fixes that. It parses your entire repository into a deterministic property graph — every class, every method, every function call, every import, every HTTP route — and exposes 25 intelligent query tools to your AI agent via the Model Context Protocol. The agent stops guessing. It queries facts.

```
React component → fetch('/api/users')
       ↓  [:ROUTES_TO]
FastAPI @app.get('/api/users')
       ↓  [:CALLS]
UserService.get_all()
       ↓  [:CALLS]
db.query("SELECT * FROM users")
```

**Zero hallucinations. Across languages. Deterministic.**

---

## Why This Is Different

| Capability | Cursor | Claude Code | This Server |
|---|---|---|---|
| Cross-language call tracing | ❌ | ❌ | ✅ |
| Frontend → Backend route stitching | ❌ | ❌ | ✅ |
| Blast radius before refactoring | ❌ | Partial | ✅ Exact |
| Dead code detection | ❌ | ❌ | ✅ |
| Syntax-validated writes | ❌ | ❌ | ✅ |
| Token-efficient context | ❌ | ❌ | ✅ 88% less |
| 15-language universal schema | ❌ | ❌ | ✅ |

---

## Quick Start

**Requirements:** Docker, Python 3.12+

```bash
git clone https://github.com/your-username/graphrag-mcp
cd graphrag-mcp

cp .env.example .env
# Edit .env if needed — defaults work out of the box

docker compose up -d
# Starts Neo4j + API + MCP server

pip install -e ".[core]"

graphrag ingest /path/to/your/repo --repo-id my_project
# Parses all supported files and builds the graph
# Shows per-file progress: Parsed (12/156) src/auth/service.py [0.043s]

python scripts/generate_mcp_config.py
# Generates mcp_config.json for Claude Desktop / Cursor
```

That's it. Your agent now has a complete knowledge graph of your codebase.

---

## Connecting Your Agent

**Claude Desktop:** Add the generated `mcp_config.json` path to Claude Desktop → Settings → MCP Servers.

**Cursor:** Add the server config to Cursor's MCP settings JSON.

Once connected, your agent can call tools like:

```
trace_network_boundary("/api/users")
→ Returns: React fetchUsers() → RouteCall → FastAPI get_users() → UserService.get_all() → db.query()

analyze_blast_radius("UserService.get_all")
→ Returns: 12 affected methods, 3 frontend callers, 2 test files

find_dead_code()
→ Returns: 7 unreferenced methods safe to delete
```

---

## Multi-Repo Support

Each repo gets its own isolated namespace in the graph via `--repo-id`:

```bash
# Ingest two separate repos
graphrag ingest /path/to/backend --repo-id backend
graphrag ingest /path/to/frontend --repo-id frontend

# Check stats per repo
graphrag status --repo-id backend

# Reset only one repo without touching the other
graphrag reset --repo-id frontend

# All MCP tools accept an optional repo_id parameter
trace_execution_flow("UserService.get_user", repo_id="backend")
```

`repo_id` defaults to `"default"` — existing ingested data is unaffected.

---

## Supported Languages

| Language | Extensions | Notes |
|---|---|---|
| Python | `.py` | Full support — decorators, type hints, async |
| TypeScript | `.ts`, `.tsx` | Classes, interfaces, arrow functions |
| JavaScript | `.js`, `.jsx` | Classes, functions, CommonJS + ESM |
| Java | `.java` | Spring Boot annotations, package FQNs |
| Go | `.go` | Structs, interfaces, receivers, packages |
| Rust | `.rs` | Structs, traits, impl blocks |
| C | `.c`, `.h` | Structs, functions, includes |
| C++ | `.cpp`, `.cc`, `.hpp` | Classes, namespaces, templates |
| Ruby | `.rb` | Classes, modules, methods |
| PHP | `.php` | Classes, interfaces, namespaces |
| Swift | `.swift` | Classes, structs, protocols |
| Kotlin | `.kt`, `.kts` | Classes, objects, interfaces |
| Shell | `.sh`, `.bash` | Functions, source commands |
| SQL | `.sql` | Tables (→ ClassNode), stored procedures |
| HTML/CSS | `.html`, `.css` | Script/link deps, selectors |

---

## The 25 Tools

### Group A — Discovery
| Tool | What it does |
|---|---|
| `explore_architecture` | High-level overview: languages, entry points, top modules |
| `find_by_fqn` | Exact node lookup by fully-qualified name |
| `search_ontology` | Keyword search across all classes, methods, files |
| `get_file_context` | All classes, methods, imports, and call counts for one file |
| `find_endpoints` | Find all HTTP route handlers by keyword |

### Group B — Deep Tracing
| Tool | What it does |
|---|---|
| `trace_execution_flow` | Every function this method calls, recursively, with confidence |
| `analyze_blast_radius` | Everything that breaks if you change this method |
| `trace_network_boundary` | Complete chain: React fetch → FastAPI handler → DB |
| `find_data_lineage` | Where does a payload go after entering this handler |
| `find_circular_dependencies` | All import cycles in the codebase |

### Group C — Code Health
| Tool | What it does |
|---|---|
| `find_dead_code` | Methods with zero callers — safe to delete |
| `identify_god_classes` | Classes doing too much — top refactoring targets |
| `check_architecture_drift` | Import violations against your layer rules |
| `map_third_party_deps` | Every internal method touching a specific package |
| `find_interface_violations` | Classes missing required interface methods |
| `estimate_migration_cost` | Touch points for migrating away from a dependency |

### Group D — Agentic SDLC
| Tool | What it does |
|---|---|
| `safe_write_file` | Write code only after Tree-sitter syntax validation |
| `auto_sync_graph` | Re-parse one file and patch the graph incrementally |
| `query_graph_raw` | Read-only Cypher escape hatch for power users |
| `scaffold_polyglot_feature` | Generate full-stack boilerplate from graph patterns |
| `generate_test_suite` | Auto-generate mocks for every dependency of a method |

### Group E — History & Visualization
| Tool | What it does |
|---|---|
| `explain_change_history` | Git blame + graph complexity — why is this method complex |
| `generate_architecture_diagram` | Mermaid diagram from any module subgraph |
| `summarize_module` | Public interface + dependencies of a module |

---

## Token Efficiency

The same architectural question answered two ways on a React + FastAPI project:

| Approach | Est. Tokens | Method |
|---|---|---|
| Naive (dump all files into context) | ~630 | Raw file content |
| Graph (3 MCP tool calls) | ~71 | Structured subgraph queries |
| **Reduction** | **88.7%** | |

Run the benchmark yourself after ingesting a repo:
```bash
python scripts/benchmark_tokens.py
```

---

## How It Works

Four layers, each with one job:

**1. Parser Factory** — Tree-sitter reads every source file and produces a language-agnostic AST. A Python `def get_user():` and a Java `public User getUser()` both become identical `MethodNode` objects in memory.

**2. Universal Schema** — Pydantic models translate raw AST output into graph-ready nodes with fully-qualified names (`com.company.auth.UserService.getUser`), confidence-scored call edges, and source code metadata on every method.

**3. Deterministic Graph** — Neo4j stores the schema as a property graph. A post-processing stitch pass matches frontend `fetch('/api/users')` calls to backend `@app.get('/api/users')` handlers and writes `[:ROUTES_TO]` edges across language boundaries.

**4. MCP Context Server** — FastMCP wraps 25 Cypher queries as simple Python functions and exposes them to any MCP-compatible agent. The agent gets precise, minimal subgraphs — not raw file dumps.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) — adding a new language takes about 30 minutes.

## Roadmap

See [ROADMAP.md](ROADMAP.md).

## License

MIT
