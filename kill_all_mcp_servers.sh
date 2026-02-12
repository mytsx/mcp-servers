#!/bin/bash

# Kill All MCP Servers Script
# This script kills all running MCP server processes

echo "🔴 Stopping all MCP servers..."
echo "================================"

# Function to kill processes and report
kill_process() {
    local pattern=$1
    local name=$2
    
    # Check if process exists
    if pgrep -f "$pattern" > /dev/null; then
        echo "⏹️  Stopping $name..."
        pkill -f "$pattern"
        sleep 0.5
        
        # Verify it's killed
        if pgrep -f "$pattern" > /dev/null; then
            echo "⚠️  Force killing $name..."
            pkill -9 -f "$pattern"
        fi
        echo "✅ $name stopped"
    else
        echo "ℹ️  $name not running"
    fi
}

# Kill SSH MCP Server
kill_process "ssh-mcp-server/server.py" "SSH MCP Server"

# Kill PostgreSQL MCP Server
kill_process "postgresql-mcp-server/server.py" "PostgreSQL MCP Server"

# Kill Oracle MCP Server
kill_process "oracle-mcp-server/server.py" "Oracle MCP Server"

# Kill Git Extended MCP Server
kill_process "mcp_server_git" "Git Extended MCP Server"

# Kill Context7 MCP
kill_process "context7-mcp" "Context7 MCP"

# Kill Docker MCP
kill_process "docker-mcp" "Docker MCP"
kill_process "docker mcp gateway" "Docker MCP Gateway"

# Kill Mapeg MCP Server
kill_process "MapegMcpServer" "Mapeg MCP Server"

# Kill any remaining Python server.py processes in ai_db directory
kill_process "/ai_db/.*server\.py" "AI_DB Server Scripts"

# Kill Smithery CLI (Context7)
kill_process "@smithery/cli" "Smithery CLI"

# Kill any npm exec processes related to MCP
kill_process "npm.*context7-mcp" "NPM Context7 MCP"

# General cleanup for any remaining MCP processes
kill_process "[Mm][Cc][Pp].*[Ss]erver" "Remaining MCP Servers"

echo ""
echo "================================"
echo "🔍 Checking for remaining processes..."
echo ""

# Check if any MCP-related processes are still running
# Exclude VSCode extensions and other non-MCP servers
remaining=$(ps aux | grep -E "(mcp|MCP|server\.py)" | grep -v grep | grep -v "kill_all_mcp_servers.sh" | grep -v ".vscode/extensions" | grep -v "autopep8" | grep -v "lsp_server")

if [ -z "$remaining" ]; then
    echo "✅ All MCP servers successfully stopped!"
else
    echo "⚠️  Some processes might still be running:"
    echo "$remaining"
    echo ""
    echo "You may need to manually kill these processes or restart your system."
fi

echo ""
echo "💡 Tip: Restart Claude Desktop now for a clean start"
echo "================================"