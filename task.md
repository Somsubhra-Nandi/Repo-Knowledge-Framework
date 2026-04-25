# Polyglot GraphRAG MCP Server
### God-Tier Context Plugin for AI Agents
**Staff-Level Open-Source Project — Architecture & Execution Plan**

---

> **Mission:** Standard AI agents (Cursor, Claude Code) rely on Vector databases and LSP, which fail at cross-language logic and hallucinate architecture. This system provides a **deterministic, mathematical ground truth layer** by combining Tree-sitter AST parsing, Neo4j graph storage, and the Model Context Protocol to expose intelligent meta-tools directly to any AI agent.

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
   - [Layer 1 — Parser Factory](#layer-1--the-parser-factory-ingestion)
   - [Layer 2 — Universal Schema](#layer-2--the-universal-schema-translation)
   - [Layer 3 — Deterministic Graph](#layer-3--the-deterministic-brain-neo4j)
   - [Layer 4 — MCP Context Server](#layer-4--the-mcp-context-server)
2. [The 25 Meta-Tool Catalog](#2-the-25-meta-tool-catalog)
3. [Phase-by-Phase Execution Plan](#3-phase-by-phase-execution-plan)
4. [Project Summary](#4-project-summary)

---

# 1. High-Level Architecture

The system is composed of four distinct, sequentially dependent layers. Each layer transforms raw source code further toward an agentic, queryable knowledge graph.

| Layer | Name | Engine | Responsibility |
|-------|------|--------|----------------|
| 1 | Parser Factory | Tree-sitter | Ingest raw source files; produce language-agnostic ASTs |
| 2 | Universal Schema | Pydantic / Dataclasses | Translate heterogeneous ASTs into a single canonical model |
| 3 | Deterministic Graph | Neo4j | Store nodes & edges; stitch cross-language boundaries |
| 4 | MCP Context Server | FastMCP / Python | Expose Cypher queries as 25 agent-callable meta-tools |

---

## Layer 1 — The Parser Factory (Ingestion)

The Parser Factory is the entry point of the entire pipeline. Its sole job is to read every source file in a target repository and produce a structured Abstract Syntax Tree (AST) for each file, routing it to the correct Tree-sitter grammar based on its extension.

### Language Support Matrix (Top 15)

| Extension(s) | Language | Tree-sitter Grammar | Priority |
|---|---|---|---|
| `.py` | Python | `tree-sitter-python` | P0 — Core |
| `.ts`, `.tsx` | TypeScript | `tree-sitter-typescript` | P0 — Core |
| `.js`, `.jsx` | JavaScript | `tree-sitter-javascript` | P0 — Core |
| `.java` | Java | `tree-sitter-java` | P0 — Core |
| `.go` | Go | `tree-sitter-go` | P1 |
| `.rs` | Rust | `tree-sitter-rust` | P1 |
| `.cpp`, `.cc`, `.h` | C++ | `tree-sitter-cpp` | P1 |
| `.cs` | C# | `tree-sitter-c-sharp` | P1 |
| `.rb` | Ruby | `tree-sitter-ruby` | P2 |
| `.php` | PHP | `tree-sitter-php` | P2 |
| `.swift` | Swift | `tree-sitter-swift` | P2 |
| `.kt` | Kotlin | `tree-sitter-kotlin` | P2 |
| `.sh`, `.bash` | Shell | `tree-sitter-bash` | P2 |
| `.sql` | SQL | `tree-sitter-sql` | P2 |
| `.html`, `.css` | HTML/CSS | `tree-sitter-html` / `css` | P2 |

### The Dispatcher (Python Router)

A single Python function reads the file extension, selects the appropriate grammar from a pre-built shared library, instantiates a Tree-sitter Parser, and returns the raw AST. This is the **only** place language-specific routing logic lives.

```python
from tree_sitter import Language, Parser
from pathlib import Path

Language.build_library('build/languages.so', [
    'vendor/tree-sitter-python',
    'vendor/tree-sitter-typescript',
    'vendor/tree-sitter-javascript',
    'vendor/tree-sitter-java',
    # ... all 15
])

EXT_MAP = {
    '.py':   'python',
    '.ts':   'typescript',
    '.tsx':  'typescript',
    '.js':   'javascript',
    '.jsx':  'javascript',
    '.java': 'java',
    '.go':   'go',
    '.rs':   'rust',
    # ...
}

def get_parser(file_path: str) -> Parser:
    ext = Path(file_path).suffix
    lang_name = EXT_MAP.get(ext)
    if not lang_name:
        raise ValueError(f"Unsupported extension: {ext}")
    lang = Language('build/languages.so', lang_name)
    parser = Parser()
    parser.set_language(lang)
    return parser

def parse_file(file_path: str) -> 'ParsedFile':
    parser = get_parser(file_path)
    source = Path(file_path).read_bytes()
    tree = parser.parse(source)
    return ParsedFile(path=file_path, tree=tree, source=source)
```

---

## Layer 2 — The Universal Schema (Translation)

This is the **architectural crown jewel**. Every language has a unique AST structure. This layer uses an adapter pattern to collapse all of them into a single canonical Pydantic model. To the database, a TypeScript arrow function and a Python `def` statement become **mathematically identical nodes**.

### Canonical Node Types

```python
from pydantic import BaseModel, field_validator
from typing import Optional

class FileNode(BaseModel):
    path: str
    language: str
    checksum: str
    last_parsed: str

class ClassNode(BaseModel):
    fqn: str          # e.g. "com.company.auth.UserService"
    name: str
    file: str
    line: int
    language: str
    is_interface: bool = False
    is_abstract: bool = False

class MethodNode(BaseModel):
    fqn: str          # e.g. "com.company.auth.UserService.getUser"
    name: str
    file: str
    line: int
    signature: str
    language: str
    is_dynamic: bool = False  # true for monkey-patched, reflected, etc.

class EndpointNode(BaseModel):
    path: str          # e.g. "/api/users"
    http_method: str   # GET, POST, PUT, DELETE
    handler_fqn: str
    language: str
    file: str
    line: int

class ImportNode(BaseModel):
    source_file: str
    target_module: str
    symbols: list[str]
    is_external: bool  # True = third-party package

class CallEdge(BaseModel):
    caller_fqn: str
    callee_fqn: str
    line: int
    confidence: float  # 0.0 – 1.0
    resolved: bool
    dynamic_flag: bool = False

    @field_validator('confidence')
    def validate_confidence(cls, v):
        assert 0.0 <= v <= 1.0, "Confidence must be between 0 and 1"
        return v

class DependencyEdge(BaseModel):
    from_file: str
    to_file_or_package: str
    is_third_party: bool
```

### Why Fully-Qualified Names (FQN) Are Critical

> Enterprise repos have dozens of identically named functions — `getUser()` appears in auth, admin, and public modules simultaneously. FQNs like `com.company.auth.UserService.getUser` give every node a **mathematically unique identity**, eliminating all name-collision ambiguity in graph queries.

### Confidence Scoring System

Not all edges can be statically resolved. Dynamic dispatch, Python monkey-patching, and JavaScript prototype chains produce uncertain edges. Every `CallEdge` carries a confidence score:

| Score | Meaning | Example |
|-------|---------|---------|
| `1.0` | Fully resolved — direct static call | `obj.method()` with known type |
| `0.7` | Probable — inferred by type hints | Typed Python with mypy annotations |
| `0.4` | Possible — dynamic dispatch suspected | Java interface with multiple implementations |
| `0.2` | Unresolved — runtime-only | Python reflection, `eval()`, monkey-patch |

---

## Layer 3 — The Deterministic Brain (Neo4j)

Neo4j stores the universal schema as a labeled property graph. Nodes represent code entities; relationships represent structural and execution-flow edges. This layer transforms a filesystem into a **queryable, traversable knowledge graph**.

### Node Labels

| Label | Description |
|-------|-------------|
| `(:File)` | Every source file in the repo |
| `(:Class)` | Classes, interfaces, structs |
| `(:Method)` | Functions, methods, lambdas |
| `(:Endpoint)` | HTTP route handlers |
| `(:Package)` | External NPM / Pip / Cargo / Maven packages |

### Relationship Types

| Relationship | Properties | Description |
|---|---|---|
| `[:CONTAINS]` | — | File/Class → Class/Method (structural ownership) |
| `[:CALLS]` | `confidence`, `line` | Method → Method (execution flow) |
| `[:IMPORTS]` | — | File → File or Package (dependency) |
| `[:ROUTES_TO]` | `confidence` | Frontend `fetch()` → Backend Endpoint |
| `[:DEPENDS_ON]` | — | High-level module → module dependency |
| `[:IMPLEMENTS]` | — | Class → Interface |
| `[:INHERITS_FROM]` | — | Class → Parent Class |

### The Cross-Language Network Stitch

A post-processing script runs after ingestion. It extracts HTTP route strings from both frontend call sites and backend route decorators, matches them by `(path, method)` tuple, and writes `[:ROUTES_TO]` edges.

```
Frontend:  fetch('/api/users', { method: 'GET' })  ─────────────────┐
                                                                      │ [:ROUTES_TO]
Backend:   @app.get('/api/users')  ─────────────────────────────────┘
```

This is the **only feature** that gives an agent a complete, deterministic picture of a full-stack request lifecycle. Cursor and Claude Code cannot do this.

### Graph Versioning & CI/CD Integration

Each graph state is tagged with the **Git SHA** of the commit that produced it. On every push:

1. CI/CD hook runs `git diff HEAD~1 HEAD --name-only`
2. Only changed files are re-parsed
3. Neo4j nodes/edges are patched (not rebuilt from scratch)
4. Graph SHA tag is updated

This keeps the graph always in sync without expensive full rebuilds.

---

## Layer 4 — The MCP Context Server

The MCP server is the **public interface** of the entire system. It wraps complex Cypher queries behind 25 simple, semantically named Python functions and exposes them to any MCP-compatible agent (Cursor, Claude Code, Claude Desktop) via the Model Context Protocol.

### Why Meta-Tools, Not Micro-Tools

> Exposing 100+ granular tools to an AI agent causes tool-selection failure and context window explosion. Instead, 25 meta-tools each hide complex Cypher sub-queries behind a single function call. Each tool returns only the **minimal subgraph** the agent needs — reducing token usage by up to **90%** versus naive context injection.

```python
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase

mcp = FastMCP("graphrag")
driver = GraphDatabase.driver("bolt://localhost:7687")

@mcp.tool()
def trace_network_boundary(fetch_call_or_path: str) -> dict:
    """
    Inputs a frontend API call or path string.
    Returns the complete request lifecycle from UI to DB across language boundaries.
    """
    # ... Cypher query
```

---

# 2. The 25 Meta-Tool Catalog

---

## Group A — Discovery & Navigation (5 Tools)

| Tool | Input | Output |
|------|-------|--------|
| `explore_architecture` | `repo_root` path | Top-level modules, frameworks detected, primary entry points, language breakdown |
| `find_endpoints` | keyword (e.g. `"auth"`) | Exact controller file, line number, HTTP method, language, handler FQN |
| `search_ontology` | query string | Hybrid vector + full-text search across all 15 languages; returns ranked Method/Class nodes |
| `get_file_context` | `file_path` | All classes, methods, immediate imports, and outgoing call edges for one file |
| `find_by_fqn` | `fully.qualified.Name` | Exact node data: file, line, language, signature, all incoming and outgoing edges |

---

## Group B — Deep Execution Tracing (5 Tools)

| Tool | Input | Output |
|------|-------|--------|
| `trace_execution_flow` | method FQN | Full downstream call tree with confidence scores at each hop |
| `analyze_blast_radius` | method FQN | Every upstream caller, test, and frontend component that will break on change |
| `trace_network_boundary` | frontend fetch call or endpoint path | Complete request lifecycle from UI button to SQL query across language boundaries |
| `find_data_lineage` | variable or payload name | Trace from API controller → service → repository → DB persistence layer |
| `find_circular_dependencies` | module or file path | All dependency/call cycles involving this node |

### Example: `trace_network_boundary` Output

```
Input: "fetchUsers"

fetchUsers()  [UserList.tsx, line 42]
  └─ fetch('/api/users', GET)
       └─ [:ROUTES_TO, confidence: 1.0]
            └─ get_users()  [users_router.py, line 18]
                 └─ [:CALLS, confidence: 1.0]
                      └─ UserService.get_all()  [services/user.py, line 55]
                           └─ [:CALLS, confidence: 1.0]
                                └─ db.query(User)  [database.py, line 12]
```

Zero hallucinations. All FQNs verified in Neo4j.

---

## Group C — Analysis & Code Health (6 Tools)

| Tool | Input | Output |
|------|-------|--------|
| `find_dead_code` | module scope (optional) | All `Method` nodes with zero incoming `[:CALLS]` edges — safe deletion candidates |
| `identify_god_classes` | threshold (optional) | Files/classes ranked by outgoing dependency count — refactoring targets |
| `check_architecture_drift` | layer rules config | All import edges that violate defined layer boundaries (e.g. DB layer importing UI layer) |
| `map_third_party_deps` | package name | Every internal method touching a specific NPM/Pip/Cargo package |
| `find_interface_violations` | interface FQN | All classes that should implement an interface but are missing methods |
| `estimate_migration_cost` | `from_tech`, `to_tech` | Count of affected files, methods, and dependency edges for a technology migration |

### Example: `find_dead_code` Cypher

```cypher
MATCH (m:Method)
WHERE NOT (m)<-[:CALLS]-()
AND NOT m.name IN ['main', '__init__', 'setUp']
RETURN m.fqn, m.file, m.line
ORDER BY m.file
```

---

## Group D — Agentic SDLC — Read/Write (5 Tools)

| Tool | Input | Side Effect / Output |
|------|-------|----------------------|
| `safe_write_file` | `file_path`, `new_content` | Runs Tree-sitter **in-memory** syntax validation before writing. Rejects broken code. Then writes and triggers `auto_sync_graph`. |
| `auto_sync_graph` | `file_path` (auto-called) | Re-parses single modified file, diffs against Neo4j, patches only changed nodes/edges. No full reindex. |
| `scaffold_polyglot_feature` | feature name, stack config | Generates boilerplate for a full-stack feature based on existing graph patterns |
| `generate_test_suite` | method FQN | Analyzes all `[:CALLS]` edges, auto-generates mocks for every dependency, outputs a complete unit test |
| `query_graph_raw` | Cypher string | Escape-hatch: executes arbitrary **read-only** Cypher. For power users and autonomous agent exploration. |

### How `safe_write_file` Works

```
new_content
    │
    ▼
Write to /tmp/validate_XXXX.py
    │
    ▼
tree_sitter.parse(content)
    │
    ├── ERROR nodes found? ──► REJECT — return error with line numbers
    │
    └── Clean AST ──────────► Write to actual file_path
                                    │
                                    ▼
                              auto_sync_graph(file_path)
                                    │
                                    ▼
                              Neo4j patched ✓
```

---

## Group E — History, Documentation & Visualization (4 Tools)

| Tool | Input | Output |
|------|-------|--------|
| `explain_change_history` | method or file FQN | Git blame data merged with graph complexity metrics — explains *why* a method is complex |
| `generate_architecture_diagram` | module or service name | Mermaid / D2 diagram generated from a subgraph query — instant visual documentation |
| `get_dependency_report` | file or module path | Full transitive dependency tree with third-party packages annotated by risk and license |
| `summarize_module` | module path | High-level natural language summary of a module's responsibilities, generated from its graph structure |

---

# 3. Phase-by-Phase Execution Plan

> **Rule:** Every phase has exactly **one testable deliverable** — a binary pass/fail test that confirms completion before moving to the next phase. No phase exceeds 3 days.

---

## Milestone 1 — The Foundation
**Goal:** A working Python-only parser pipeline that writes structured data to Neo4j.

---

### Phase 1 — Project Scaffolding & Environment
**Duration:** 1 day
**Deliverable:** Running Docker Compose with Neo4j + Python service; `/health` endpoint returns `200 OK` and Neo4j connection is confirmed.

**Tasks:**
- Initialize Git repo with conventional commit structure (`feat:`, `fix:`, `chore:`)
- Create `docker-compose.yml`: Neo4j 5.x, Python 3.12 service, shared Docker network
- Set up `pyproject.toml` with dependency groups: `core`, `dev`, `test`
- Install core deps: `tree-sitter`, `neo4j`, `pydantic`, `fastapi`, `uvicorn`, `pytest`, `ruff`
- Write `/health` FastAPI endpoint; confirm Neo4j bolt connection from Python container
- Configure `.env`: Neo4j credentials, repo root path, log level

---

### Phase 2 — First Tree-sitter Grammar (Python Parser)
**Duration:** 1–2 days
**Deliverable:** `parse_file('sample.py')` returns a populated `ParsedFile` with all functions and classes extracted and correctly attributed.

**Tasks:**
- Install `tree-sitter-python` grammar; compile to shared `.so` library
- Write `get_parser(extension)` dispatcher — Python only
- Write `extract_python(ast_node)` adapter: extract `ClassNode` and `MethodNode` from AST
- Populate `ParsedFile` dataclass: `path`, `language`, `classes[]`, `methods[]`, `imports[]`
- Write pytest: parse a 50-line `sample.py`; assert function names, line numbers, and class memberships are correct

---

### Phase 3 — Universal Schema Definition
**Duration:** 1 day
**Deliverable:** All Pydantic models defined with validators; serialization round-trip test passes with zero data loss.

**Tasks:**
- Define Pydantic v2 models: `FileNode`, `ClassNode`, `MethodNode`, `ImportNode`, `CallEdge`, `DependencyEdge`, `EndpointNode`
- Add `fqn` field with builder: `build_fqn(language, file, class_name, method_name) -> str`
- Add `confidence: float` to `CallEdge` with validator (must be `0.0–1.0`)
- Add `resolved: bool` and `dynamic_flag: bool` to `CallEdge`
- Write serialization test: `model → dict → model` round-trip; assert no field is lost or mutated

---

### Phase 4 — Neo4j Ingestion Engine (Write Path)
**Duration:** 2 days
**Deliverable:** Running `ingest_file('sample.py')` creates correct nodes and relationships in Neo4j, verified via Neo4j Browser.

**Tasks:**
- Write `Neo4jWriter` class: `create_file_node()`, `create_class_node()`, `create_method_node()`, `create_call_edge()`
- Use `MERGE` (not `CREATE`) for all nodes — ensures idempotent re-ingestion
- Create Neo4j indexes: on `:Method(fqn)`, `:File(path)`, `:Class(fqn)`
- Create uniqueness constraint: `:Method(fqn)` must be unique
- Write integration test: ingest `sample.py`, query Neo4j, assert node count and relationship structure match expected values

---

### Phase 5 — Call Graph Extraction (Python `[:CALLS]` Edges)
**Duration:** 2 days
**Deliverable:** After ingesting a Python file with 3 functions calling each other, Neo4j shows correct `[:CALLS]` edges with accurate confidence scores.

**Tasks:**
- Walk Tree-sitter AST to find all `call_expression` nodes within each function body
- Resolve callee FQN: check local scope → module imports → mark as `unresolved` if not found
- Assign confidence scores: `1.0` direct call, `0.7` type-annotated, `0.4` interface dispatch, `0.2` dynamic
- Write `CallEdge` nodes to Neo4j with `confidence`, `line`, `resolved` properties
- Write pytest: ingest Python file with known call structure; assert all `[:CALLS]` edges exist with correct confidence values

---

### Phase 6 — Import Graph (Python `[:IMPORTS]` Edges)
**Duration:** 1 day
**Deliverable:** After ingesting a two-file Python project, Neo4j shows correct `[:IMPORTS]` edges and third-party packages appear as `(:Package)` nodes.

**Tasks:**
- Extract import statements from AST: handle `import x`, `from x import y`, `from . import z`
- Resolve relative imports to absolute file paths within the repo root
- Mark unresolved imports (third-party) as `(:Package)` nodes
- Write `[:IMPORTS]` (file-level) and `[:DEPENDS_ON]` (module-level) relationships
- Test: two-file Python project with one cross-file import; verify both the relationship and the third-party package node in Neo4j

---

## Milestone 2 — Polyglot Expansion
**Goal:** The same pipeline works for TypeScript and Java, with all three languages sharing the universal schema.

---

### Phase 7 — TypeScript / JavaScript Parser
**Duration:** 2 days
**Deliverable:** `parse_file('api.ts')` returns correct `MethodNode` and `ClassNode` instances; arrow functions and class methods are both captured correctly.

**Tasks:**
- Install `tree-sitter-typescript` and `tree-sitter-javascript` grammars
- Add `.ts`, `.tsx`, `.js`, `.jsx` to the extension dispatcher
- Write `extract_typescript()` adapter: handle `class_declaration`, `method_definition`, `arrow_function`, `function_declaration`
- Map TypeScript `interface` → `ClassNode` with `is_interface: True` flag
- Write `extract_imports_typescript()`: handle ES `import` statements and `require()` calls
- Test: parse a TypeScript React component; verify component function, props interface, and all imports are captured

---

### Phase 8 — Java Parser
**Duration:** 2 days
**Deliverable:** `parse_file('UserService.java')` correctly extracts class hierarchy, all public methods, and `@annotation` metadata.

**Tasks:**
- Install `tree-sitter-java` grammar; add `.java` to dispatcher
- Write `extract_java()` adapter: handle `class_declaration`, `method_declaration`, `interface_declaration`
- Extract Java annotations (`@Override`, `@GetMapping`, `@RestController`) as metadata on nodes
- Handle Java FQN: `package com.company.auth` → FQN prefix for all nodes in that file
- Write `extract_imports_java()`: single-class and wildcard imports
- Test: parse a Spring Boot controller; assert all endpoint methods, class name, package FQN, and annotations are captured correctly

---

### Phase 9 — Bulk Ingestion Engine & Repo Walker
**Duration:** 1–2 days
**Deliverable:** `ingest_repo('/path/to/repo')` fully ingests a mixed Python + TypeScript + Java project in under 60 seconds.

**Tasks:**
- Write `RepoWalker`: `os.walk` with extension filtering and `.gitignore` respect
- Add parallel file parsing with `concurrent.futures.ThreadPoolExecutor`
- Add progress reporting: files parsed / total, errors written to `parse_errors.log`
- Add checksum-based skip: if `sha256(file)` matches stored checksum, skip re-parse
- Performance test: ingest a 10,000-line mixed repo; assert completion under 60 seconds and zero crashes

---

### Phase 10 — Go & Rust Parsers (P1 Languages)
**Duration:** 2 days
**Deliverable:** Go interfaces and Rust traits are correctly mapped to `ClassNode`; `impl` blocks are correctly linked to their parent structs.

**Tasks:**
- Install `tree-sitter-go` and `tree-sitter-rust` grammars
- Write `extract_go()`: handle `func_declaration`, `method_declaration`, `interface_type`, `struct_type`
- Write `extract_rust()`: handle `fn_item`, `impl_item`, `trait_item`, `struct_item`
- Handle Rust `impl Trait for Struct` → write `[:IMPLEMENTS]` edge
- Test: parse a Go HTTP handler and a Rust Actix-web endpoint; verify correct node types and all method FQNs

---

## Milestone 3 — The Cross-Language Bridge
**Goal:** The network stitch connects frontend TypeScript `fetch()` calls to backend route handlers with `[:ROUTES_TO]` edges.

---

### Phase 11 — Endpoint Node Extraction
**Duration:** 1–2 days
**Deliverable:** After ingesting a FastAPI backend and a Spring Boot backend separately, all HTTP route handlers appear as `(:Endpoint)` nodes in Neo4j.

**Tasks:**
- **Python:** detect `@app.get()`, `@app.post()`, `@router.get()` decorator patterns; extract path string and HTTP method
- **Java:** detect `@GetMapping`, `@PostMapping`, `@RequestMapping` annotations; extract path and method
- **TypeScript/Express:** detect `app.get()`, `router.post()` call patterns; extract path string and handler function reference
- **Go:** detect `chi`, `gin`, `echo` router registration patterns
- Write `(:Endpoint)` nodes: `path` (normalized), `http_method`, `handler_fqn`, `language`, `file`, `line`
- Test: ingest sample FastAPI app; assert all route endpoints appear as nodes with correct normalized paths

---

### Phase 12 — Frontend API Call Extraction
**Duration:** 1 day
**Deliverable:** `fetch('/api/users')` and `axios.get('/api/users')` calls in TypeScript files are extracted and stored as candidate `RouteCall` objects.

**Tasks:**
- Detect `fetch()`, `axios.get/post/put/delete()`, and `XMLHttpRequest` patterns in TypeScript/JS AST
- Extract URL path string; handle template literals with regex fallback and assign `confidence: 0.5`
- Create `RouteCall` objects: `{source_method_fqn, path, http_method, confidence}`
- Store candidates temporarily (not yet in Neo4j) pending matching in Phase 13
- Test: parse a React component with 3 different API calls; assert all 3 `RouteCall` objects are extracted with correct paths and methods

---

### Phase 13 — The Network Stitch (`[:ROUTES_TO]` Edges)
**Duration:** 2 days
**Deliverable:** After ingesting a full-stack React + FastAPI project, `trace_network_boundary('fetchUsers')` returns the complete 4-hop chain from React component to Python route handler.

**Tasks:**
- Write `RouteStitcher`: match `RouteCall.path` to `Endpoint.path` — exact match first, then regex for parameterized routes (`/users/:id` ↔ `/users/{id}`)
- Write `[:ROUTES_TO]` edges: `confidence: 1.0` for exact match, `confidence: 0.7` for parameterized match
- Handle path prefix normalization (strip `/api` prefix patterns configurable via `.env`)
- Write Cypher query backing `trace_network_boundary` tool
- Integration test: mini full-stack project (React + FastAPI); verify the complete chain:
  ```
  React component → fetch() → [:ROUTES_TO] → FastAPI handler → [:CALLS] → DB function
  ```

---

## Milestone 4 — The MCP Server
**Goal:** All 25 meta-tools are callable via MCP protocol; an AI agent can run end-to-end architectural queries against a real repo.

---

### Phase 14 — MCP Server Scaffold
**Duration:** 1 day
**Deliverable:** Claude Desktop (or Cursor) successfully connects to the MCP server and the tool list appears in the agent's context panel.

**Tasks:**
- Install `fastmcp` (or `mcp` Python SDK)
- Create `mcp_server.py` with `@mcp.tool()` decorator pattern
- Register 3 placeholder tools (`explore_architecture`, `find_endpoints`, `get_file_context`) returning stub responses
- Write `mcp_config.json` for local Claude Desktop configuration
- Test: connect Claude Desktop to MCP server; confirm all 3 stub tools appear in the agent tool list

---

### Phase 15 — Group A Tools (Discovery & Navigation)
**Duration:** 2 days
**Deliverable:** All 5 discovery tools return correct, structured JSON results when called via Claude Desktop on a sample repo.

**Tasks:**
- `explore_architecture`: Cypher query for top-level modules, framework detection heuristics, `CALL db.labels()`
- `find_endpoints`: full-text index search on `(:Endpoint)` nodes by keyword
- `search_ontology`: combine Neo4j full-text index + optional vector embedding for semantic matching
- `get_file_context`: single-file subgraph query — return all classes, methods, and immediate edges
- `find_by_fqn`: exact FQN node lookup with all incoming and outgoing edges
- Live test via MCP: prompt Claude *"find all auth endpoints"*; verify it returns correct results from the graph with no hallucinated names

---

### Phase 16 — Group B Tools (Deep Execution Tracing)
**Duration:** 2–3 days
**Deliverable:** `trace_network_boundary` returns the correct full-stack chain; `analyze_blast_radius` correctly identifies all callers of a modified method.

**Tasks:**
- `trace_execution_flow`: recursive Cypher `MATCH path` query with configurable depth limit and confidence threshold filter
- `analyze_blast_radius`: reverse traversal — find all ancestor nodes of the target
- `trace_network_boundary`: combined query traversing `[:ROUTES_TO]` then `[:CALLS]` edges
- `find_data_lineage`: trace by variable/parameter name through the call chain
- `find_circular_dependencies`: Cypher cycle detection query scoped to a module
- Test: modify a core utility function; verify `analyze_blast_radius` returns every affected caller and related test file

---

### Phase 17 — Group C Tools (Analysis & Code Health)
**Duration:** 2 days
**Deliverable:** `find_dead_code` returns a list of genuinely unreferenced functions; `check_architecture_drift` catches a deliberately introduced layer violation.

**Tasks:**
- `find_dead_code`: `WHERE NOT (m)<-[:CALLS]-()` Cypher with common entrypoint exclusions
- `identify_god_classes`: `ORDER BY size((c)-[:CONTAINS]->()) DESC` Cypher
- `check_architecture_drift`: configurable layer rules checked against all `[:IMPORTS]` edges
- `map_third_party_deps`: traverse inward from `(:Package)` node
- `find_interface_violations`: compare interface method signatures against all implementing class nodes
- `estimate_migration_cost`: subgraph query scoped to a technology's nodes and edges
- Test: introduce a dead function and a deliberate architecture violation; confirm both are caught with correct file and line numbers

---

### Phase 18 — `safe_write_file` & `auto_sync_graph`
**Duration:** 2 days
**Deliverable:** Writing syntactically broken Python via `safe_write_file` is rejected with a specific error; a valid write correctly patches Neo4j without a full reindex.

**Tasks:**
- `safe_write_file`: write content to `/tmp` → parse with Tree-sitter in-memory → scan for `ERROR` nodes in AST → if clean, write to actual path → call `auto_sync_graph`
- `auto_sync_graph`: parse modified file → diff against existing Neo4j nodes via checksum → `MERGE` new, `DETACH DELETE` removed, `SET` updated
- Add Git SHA tracking: tag graph state with `git rev-parse HEAD` after each sync
- Test A: write valid Python → confirm Neo4j is updated with new method node
- Test B: write `def broken(:` → confirm rejection with error message, zero file writes, graph unchanged

---

### Phase 19 — Group D & E Tools (SDLC, History & Visualization)
**Duration:** 2 days
**Deliverable:** `scaffold_polyglot_feature` generates a correctly structured file pair (TS + Python); `generate_architecture_diagram` returns valid Mermaid syntax that renders correctly.

**Tasks:**
- `scaffold_polyglot_feature`: query graph for existing structural patterns → generate boilerplate files from Jinja2 templates
- `generate_test_suite`: traverse `[:CALLS]` edges → generate mock stubs for each callee in native language
- `query_graph_raw`: read-only Cypher execution with basic input sanitization (reject `WRITE`, `CREATE`, `DELETE` keywords)
- `explain_change_history`: `git log --follow -p <file>` wrapper + graph complexity metrics merged
- `generate_architecture_diagram`: Cypher subgraph → Mermaid `flowchart TD` serializer
- `get_dependency_report` and `summarize_module`: subgraph queries with structured JSON output
- Test: generate a diagram for the sample repo; validate Mermaid syntax renders without errors

---

### Phase 20 — End-to-End Agent Integration Test
**Duration:** 1–2 days
**Deliverable:** Claude (via MCP) autonomously traces a bug from a frontend API call to a backend DB query with **zero hallucinations**, using only graph data.

**Tasks:**
- Set up a realistic sample monorepo: React frontend + FastAPI backend + SQLAlchemy models (~500 lines total)
- Fully ingest with all parsers and the network stitch
- Write the test prompt:
  > *"A bug is reported on the `/api/users` endpoint. Trace the full execution path from the React component to the database and identify which functions could be responsible."*
- Verify Claude uses the chain: `trace_network_boundary` → `trace_execution_flow` → `find_data_lineage`
- Assert: zero hallucinated function names, all returned FQNs exist in Neo4j, complete chain is accurate

---

## Milestone 5 — Open Source Launch
**Goal:** Dockerized, documented, and production-ready for public release.

---

### Phase 21 — Remaining P2 Languages
**Duration:** 3 days
**Deliverable:** All 15 languages successfully parse and ingest into Neo4j with correct node types.

**Tasks:**
- Install all remaining grammars: Ruby, PHP, Swift, Kotlin, Shell, SQL, HTML/CSS
- Write minimal adapter for each: extract top-level functions/classes and imports
- **SQL special case:** detect `CREATE TABLE`, stored procedures; add `(:Table)` node type with `[:READS_FROM]` / `[:WRITES_TO]` edges from methods
- **Shell special case:** detect function definitions and script entry points
- Bulk ingest test: polyglot sample repo with all 15 language file types; assert zero crashes and correct node counts per language

---

### Phase 22 — Dockerization & One-Command Setup
**Duration:** 1–2 days
**Deliverable:** `docker compose up` + `python -m graphrag ingest /path/to/repo` fully ingests a test repo and the MCP server is reachable in under 5 minutes on a fresh machine.

**Tasks:**
- Finalize `docker-compose.yml`: Neo4j, Python MCP server, optional pgvector sidecar for semantic search
- Write `Dockerfile` for Python service with all 15 Tree-sitter grammars pre-compiled in the image
- Write CLI: `graphrag ingest <path>`, `graphrag status`, `graphrag reset`
- Write `mcp_config.json` generator script for auto-configuring Claude Desktop and Cursor
- Fresh machine test: clone repo → `docker compose up` → `graphrag ingest ./sample_repo` → MCP tools visible in Claude Desktop — all under 5 minutes

---

### Phase 23 — Documentation & README
**Duration:** 2 days
**Deliverable:** README scores above 90% on an OSS documentation quality checklist; a developer unfamiliar with the project can set it up in under 10 minutes.

**Tasks:**
- Write `README.md`: problem statement, architecture overview, quick-start, tool catalog, contribution guide
- Generate the architecture diagram using the tool itself (dogfooding `generate_architecture_diagram`)
- Record a 2-minute demo video: `trace_network_boundary` on a React + FastAPI sample repo showing the full chain
- Write `CONTRIBUTING.md`: how to add a new language grammar in under 30 minutes (step-by-step guide)
- Write `ROADMAP.md`: v1.1 features (Git SHA versioning, multi-repo support, IDE extension)

---

### Phase 24 — Benchmarking, Performance & Launch
**Duration:** 2 days
**Deliverable:** Published benchmarks show at least 80%+ token reduction vs. naive context injection on 3 real-world repos; GitHub repo is public with CI passing.

**Tasks:**
- **Token benchmark:** same architectural query answered via (a) naive file dump into context vs (b) MCP graph query — measure and record token counts for both
- **Ingestion benchmark:** small (10k LOC), medium (100k LOC), large (500k LOC) repos — record parse time and Neo4j write time
- Set up GitHub Actions CI: lint (`ruff`), type-check (`mypy`), test (`pytest`), Docker build
- Write GitHub Release with benchmark table, demo GIF, and one-line install command
- Submit to: Hacker News (Show HN), r/programming, relevant Discord communities (Cursor, Claude, Rust, Python)

---

# 4. Project Summary

## Milestone Timeline

| Milestone | Focus | Phases | Estimated Duration |
|-----------|-------|--------|--------------------|
| 1 — Foundation | Python parser, universal schema, Neo4j ingestion | 1–6 | ~10 days |
| 2 — Polyglot Expansion | TS, Java, Go, Rust parsers + bulk ingestion | 7–10 | ~8 days |
| 3 — Cross-Language Bridge | Endpoint extraction + network stitch | 11–13 | ~5 days |
| 4 — MCP Server | All 25 meta-tools live and agent-tested | 14–20 | ~14 days |
| 5 — Open Source Launch | Docker, docs, benchmarks, public release | 21–24 | ~8 days |
| **TOTAL** | | **24 Phases** | **~45 days** |

---

## Competitive Differentiation

| Capability | Cursor | Claude Code | This MCP Server |
|---|---|---|---|
| Cross-language call tracing | ❌ | ❌ | ✅ Deterministic |
| Frontend → Backend route stitching | ❌ | ❌ | ✅ `[:ROUTES_TO]` edges |
| Blast radius analysis | ❌ | Partial | ✅ Mathematically exact |
| Dead code detection | ❌ | ❌ | ✅ Zero incoming edges |
| Syntax-validated writes | ❌ | ❌ | ✅ In-memory Tree-sitter |
| God class / dependency density | ❌ | ❌ | ✅ Cypher density query |
| Token-efficient context | ❌ | ❌ | ✅ 85–90% reduction |
| Confidence-scored edges | ❌ | ❌ | ✅ Per `CallEdge` |
| 15-language universal schema | ❌ | ❌ | ✅ Single canonical model |
| Git SHA graph versioning | ❌ | ❌ | ✅ v1.1 roadmap |

---

## Suggested Repo Structure

```
graphrag-mcp/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── .env.example
├── README.md
├── CONTRIBUTING.md
├── ROADMAP.md
│
├── graphrag/
│   ├── __init__.py
│   ├── cli.py                  # graphrag ingest / status / reset
│   ├── parser/
│   │   ├── factory.py          # get_parser() dispatcher
│   │   ├── languages.py        # EXT_MAP and grammar loader
│   │   ├── adapters/
│   │   │   ├── python.py
│   │   │   ├── typescript.py
│   │   │   ├── java.py
│   │   │   ├── go.py
│   │   │   ├── rust.py
│   │   │   └── ...             # one file per language
│   │   └── walker.py           # RepoWalker
│   │
│   ├── schema/
│   │   └── models.py           # All Pydantic models + FQN builder
│   │
│   ├── graph/
│   │   ├── writer.py           # Neo4jWriter
│   │   ├── queries.py          # All Cypher query strings
│   │   └── stitch.py           # RouteStitcher (network bridge)
│   │
│   └── mcp/
│       ├── server.py           # FastMCP server + all @mcp.tool() decorators
│       └── tools/
│           ├── discovery.py    # Group A
│           ├── tracing.py      # Group B
│           ├── health.py       # Group C
│           ├── sdlc.py         # Group D
│           └── history.py      # Group E
│
├── tests/
│   ├── fixtures/               # Sample files for each language
│   ├── test_parsers.py
│   ├── test_schema.py
│   ├── test_ingestion.py
│   ├── test_stitch.py
│   └── test_mcp_tools.py
│
└── sample_repo/                # Realistic React + FastAPI demo project
    ├── frontend/               # React + TypeScript
    └── backend/                # FastAPI + SQLAlchemy
```

---

*Polyglot GraphRAG MCP Server — Architecture & Execution Plan*
*Open Source — Build the brain, not the UI.*
