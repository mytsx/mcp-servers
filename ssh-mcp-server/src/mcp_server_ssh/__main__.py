#!/usr/bin/env python3
"""
Entry point for SSH MCP Server
Usage: uvx mcp-server-ssh | python -m mcp_server_ssh
"""

from .server import mcp


def run():
    """Synchronous entry point"""
    mcp.run()


if __name__ == "__main__":
    run()
