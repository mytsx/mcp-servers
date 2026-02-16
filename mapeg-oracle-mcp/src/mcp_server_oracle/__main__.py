#!/usr/bin/env python3
"""
Entry point for Oracle MCP Server
Allows the package to be run as: python -m mcp_server_oracle
Or via uvx: uvx mcp-server-oracle
"""

import asyncio
from .server import OracleMCPServer
from mcp.server.stdio import stdio_server


async def main():
    """Main entry point for the Oracle MCP server"""
    oracle_server = OracleMCPServer()

    async with stdio_server() as (read_stream, write_stream):
        await oracle_server.server.run(
            read_stream,
            write_stream,
            oracle_server.server.create_initialization_options()
        )


def run():
    """Synchronous wrapper for the async main function"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
