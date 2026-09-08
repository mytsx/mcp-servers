#!/usr/bin/env python3
"""
Entry point for Oracle MCP Server
Usage: uvx mapeg-oracle-mcp | python -m mcp_server_oracle
"""

from .server import mcp


def run():
    """Synchronous entry point"""
    mcp.run()


if __name__ == "__main__":
    run()
