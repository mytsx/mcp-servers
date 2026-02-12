#!/bin/bash
set -euo pipefail

echo "🚀 Starting SSH MCP Activity Dashboard..."
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Check if database exists in home directory
DB_PATH="$HOME/.ssh_mcp_logs/ssh_mcp_activities.db"
if [ ! -f "$DB_PATH" ]; then
    echo "⚠️  Warning: No activity database found at $DB_PATH"
    echo "   Please run the SSH MCP server first to generate activity logs."
    echo ""
fi

# Start the dashboard
echo ""
echo "🌐 Starting Flask dashboard on http://localhost:5555"
echo "📊 Press Ctrl+C to stop the server"
echo ""

python ssh_log_dashboard.py