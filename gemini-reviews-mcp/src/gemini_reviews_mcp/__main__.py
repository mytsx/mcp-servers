#!/usr/bin/env python3
"""
Entry point for Gemini PR Reviews MCP Server
Usage: uvx gemini-reviews-mcp | python -m gemini_reviews_mcp
"""

from .server import mcp


def run():
    """Synchronous entry point"""
    mcp.run()


if __name__ == "__main__":
    run()
