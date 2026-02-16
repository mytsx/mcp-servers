#!/usr/bin/env python3
"""
Entry point for Docusaurus MCP Server
Usage: docusaurus-mcp | python -m docusaurus_mcp
"""

from .server import mcp


def run():
    """Synchronous entry point"""
    mcp.run()


if __name__ == "__main__":
    run()
