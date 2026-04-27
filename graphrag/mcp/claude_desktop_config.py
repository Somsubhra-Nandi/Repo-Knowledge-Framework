"""Print the Claude Desktop MCP configuration for this server."""

import json
import sys
from pathlib import Path


def main() -> None:
    """Print the Claude Desktop config snippet for this MCP server."""
    python_path = sys.executable
    server_path = str(Path(__file__).parent / "server.py")

    config = {
        "mcpServers": {
            "graphrag": {
                "command": python_path,
                "args": [server_path],
                "env": {
                    "NEO4J_URI": "bolt://localhost:7687",
                    "NEO4J_USERNAME": "neo4j",
                    "NEO4J_PASSWORD": "neo4j_password",
                },
            }
        }
    }
    print(json.dumps(config, indent=2))
    print("\nAdd the above to your Claude Desktop config file:")
    print("  macOS: ~/Library/Application Support/Claude/claude_desktop_config.json")
    print("  Windows: %APPDATA%\\Claude\\claude_desktop_config.json")


if __name__ == "__main__":
    main()
