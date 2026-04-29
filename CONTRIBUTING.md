# Contributing

## How to Add a New Language Parser
1. Install the corresponding tree-sitter grammar dependency.
2. Add file extension mapping in `graphrag/parser/languages.py` (`EXT_MAP`).
3. Add grammar loading logic in `load_language()` in `graphrag/parser/languages.py`.
4. Implement `_collect_X_definitions()` in `graphrag/parser/factory.py`.
5. Add dispatch branch for that language in `parse_file()` in `graphrag/parser/factory.py`.
6. Add fixture file at `tests/fixtures/sample.X`.
7. Add parser test file `tests/test_X_parser.py`.
8. Run `pytest tests/ -v` and confirm green.

## How to Add a New MCP Tool
1. Add a new `@mcp.tool()` function in `graphrag/mcp/server.py`.
2. Re-export it in the relevant `graphrag/mcp/tools/*.py` module.
3. Add/extend mock coverage in `tests/test_mcp_tools.py`.
4. Update tool count and tool table in `README.md`.

## Dev Setup
1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -e ".[core,dev,test]"
   ```
3. Run lint:
   ```bash
   python -m ruff check .
   ```

## Commit Convention
Use conventional prefixes:
- `feat:`
- `fix:`
- `chore:`
- `docs:`

## PR Checklist
- `ruff` passes
- `pytest` passes
- New code includes tests when behavior changes
