#!/usr/bin/env python3
"""
Entry point for SSH MCP Server
Usage: uvx mcp-server-ssh | python -m mcp_server_ssh
"""

import asyncio
import os
import sys

# Add the original server directory to path for ssh_activity_logger
_server_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.exists(os.path.join(_server_dir, "ssh_activity_logger.py")):
    sys.path.insert(0, _server_dir)

from .server import SSHMCPServer
from mcp.server.stdio import stdio_server


async def main():
    """Main entry point for the SSH MCP server"""
    ssh_server = SSHMCPServer()

    async with stdio_server() as (read_stream, write_stream):
        await ssh_server.server.run(
            read_stream,
            write_stream,
            ssh_server.server.create_initialization_options()
        )


def run():
    """Synchronous wrapper for the async main function"""
    asyncio.run(main())


if __name__ == "__main__":
    run()
