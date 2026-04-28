"""Generate mcp_config.json for Claude Desktop and Cursor."""
import json
import os
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).parent.parent.resolve()
    python_path = sys.executable

    config = {
        "mcpServers": {
            "graphrag": {
                "command": str(python_path),
                "args": ["-m", "graphrag.mcp.server"],
                "cwd": str(repo_root),
                "env": {
                    "NEO4J_URI": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                    "NEO4J_USERNAME": os.getenv("NEO4J_USERNAME", "neo4j"),
                    "NEO4J_PASSWORD": os.getenv("NEO4J_PASSWORD", "neo4j_password"),
                },
            }
        }
    }

    output_path = repo_root / "mcp_config.json"
    output_path.write_text(json.dumps(config, indent=2))
    print(f"Written: {output_path}")
    print("Add this file path to Claude Desktop settings > MCP Servers.")


if __name__ == "__main__":
    main()
