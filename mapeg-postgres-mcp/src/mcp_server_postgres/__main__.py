#!/usr/bin/env python3
"""
Entry point for PostgreSQL MCP Server
Allows the package to be run as: python -m mcp_server_postgres
Or via uvx: uvx mcp-server-postgres
"""

import asyncio
from .server import PostgreSQLMCPServer
from mcp.server.stdio import stdio_server


async def main():
    """Main entry point for the PostgreSQL MCP server"""
    postgresql_server = PostgreSQLMCPServer()

    async with stdio_server() as (read_stream, write_stream):
        await postgresql_server.server.run(
            read_stream,
            write_stream,
            postgresql_server.server.create_initialization_options()
        )


def run():
    """Synchronous wrapper for the async main function"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
