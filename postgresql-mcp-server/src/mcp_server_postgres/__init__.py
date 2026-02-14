"""
PostgreSQL MCP Server
Natural language queries to PostgreSQL database via MCP protocol
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__license__ = "MIT"

from .server import PostgreSQLMCPServer

__all__ = ["PostgreSQLMCPServer"]
