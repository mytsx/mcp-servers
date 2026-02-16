#!/usr/bin/env python3
"""
Entry point for Gemini PR Reviews MCP Server
Usage: uvx gemini-reviews-mcp | python -m gemini_reviews_mcp
"""

import asyncio
from .server import GeminiPRReviewsMCPServer
from mcp.server.stdio import stdio_server


async def main():
    """Main entry point for the Gemini PR Reviews MCP server"""
    pr_server = GeminiPRReviewsMCPServer()

    async with stdio_server() as (read_stream, write_stream):
        await pr_server.server.run(
            read_stream,
            write_stream,
            pr_server.server.create_initialization_options()
        )


def run():
    """Synchronous wrapper for the async main function"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
