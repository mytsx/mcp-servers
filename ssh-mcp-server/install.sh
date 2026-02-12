#!/bin/bash

echo "🚀 Installing SSH MCP Server..."

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
pip install -r requirements.txt

echo "✅ SSH MCP Server installation completed!"
echo ""
echo "📝 Next steps:"
echo "1. Edit .env file with your SSH credentials"
echo "2. Test the server: python server.py"
echo "3. Add to Claude Desktop configuration"
echo ""
echo "🔒 Security Note:"
echo "- Only use with trusted servers"
echo "- Dangerous commands are automatically blocked"
echo "- Review logs regularly"