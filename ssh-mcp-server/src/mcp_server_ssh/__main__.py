#!/usr/bin/env python3
"""
Entry point for SSH MCP Server
Usage: uvx mcp-server-ssh | python -m mcp_server_ssh
"""

import os
import sys

# ssh_activity_logger.py sits next to the package rather than inside it, so it
# is not part of the published distribution. When running from a checkout it is
# there, and this puts it on the path so activity logging works regardless of
# the working directory. Without it the import only succeeds when the process
# happens to start in ssh-mcp-server/.
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if os.path.exists(os.path.join(_project_root, "ssh_activity_logger.py")):
    sys.path.insert(0, _project_root)

from .server import mcp  # noqa: E402 - must follow the path setup above


def run():
    """Synchronous entry point"""
    mcp.run()


if __name__ == "__main__":
    run()
