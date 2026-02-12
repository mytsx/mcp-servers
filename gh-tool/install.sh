#!/bin/bash

# Get the directory where this script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "🚀 Gemini PR Reviews MCP Server - Installation Script"
echo "===================================================="

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.7 or higher."
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Change to the script directory
cd "$DIR"

# Remove existing virtual environment if it exists
if [ -d "venv" ]; then
    echo "🗑️  Removing existing virtual environment..."
    rm -rf venv
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📚 Installing requirements..."
pip install -r requirements.txt

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo ""
    echo "⚠️  No .env file found!"
    echo "📝 Creating .env file..."
    echo "GITHUB_TOKEN=your_github_token_here" > .env
    echo ""
    echo "🔑 Please edit the .env file and add your GitHub Personal Access Token:"
    echo "   $DIR/.env"
    echo ""
    echo "To get a GitHub token:"
    echo "1. Go to https://github.com/settings/tokens"
    echo "2. Click 'Generate new token (classic)'"
    echo "3. Give it a name and select 'repo' scope"
    echo "4. Copy the token and paste it in the .env file"
else
    echo "✅ .env file already exists"
fi

# Make run.sh executable
if [ -f "run.sh" ]; then
    chmod +x run.sh
    echo "✅ run.sh is now executable"
fi

# Make install.sh executable (self)
chmod +x install.sh

echo ""
echo "✨ Installation complete!"
echo ""
echo "📋 Next steps:"
echo "1. Edit .env file with your GitHub token (if not already done)"
echo "2. Add this to your Claude Desktop config:"
echo ""
echo '  "gemini-pr-reviews": {'
echo "    \"command\": \"$DIR/run.sh\""
echo '  }'
echo ""
echo "📍 Location: ~/Library/Application Support/Claude/claude_desktop_config.json"
echo ""
echo "🚀 To test the server manually:"
echo "   ./run.sh"