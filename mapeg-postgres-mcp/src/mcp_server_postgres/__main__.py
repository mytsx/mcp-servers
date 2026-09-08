#!/usr/bin/env python3
"""
Entry point for PostgreSQL MCP Server
Usage: uvx mapeg-postgres-mcp | python -m mcp_server_postgres
"""

from .server import mcp


def run():
    """Synchronous entry point"""
    mcp.run()


if __name__ == "__main__":
    run()
