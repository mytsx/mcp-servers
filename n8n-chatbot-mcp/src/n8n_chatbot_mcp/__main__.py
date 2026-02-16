#!/usr/bin/env python3
"""
Entry point for n8n Chatbot MCP Server
Usage: n8n-chatbot-mcp | python -m n8n_chatbot_mcp
"""

from .server import mcp


def run():
    """Synchronous entry point"""
    mcp.run()


if __name__ == "__main__":
    run()
