# SSH Terminal MCP Server

An MCP (Model Context Protocol) server that enables AI assistants to interact with SSH terminals through web browsers. This tool allows AI to execute commands and read terminal outputs via browser automation.

## Features

- 🌐 **Web-based SSH Terminal Access**: Connect to SSH terminals through web interfaces
- 🔐 **Manual Authentication**: Secure manual login with session persistence
- 💻 **Command Execution**: Execute terminal commands programmatically
- 📸 **Screenshot Capture**: Take screenshots of terminal output
- 🔍 **OCR Text Extraction**: Extract text from terminal screenshots using Tesseract.js
- 💾 **Session Management**: Save and restore browser sessions to avoid repeated logins
- 🧹 **Clean Output Mode**: Clear terminal before commands for cleaner outputs

## Prerequisites

- Node.js 18+
- npm or yarn
- Chromium browser (automatically installed by Playwright)

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd ssh_terminal_mcp

# Install dependencies
npm install

# Install Playwright browsers
npx playwright install chromium

# Copy environment file and configure
cp .env.example .env
# Edit .env and set TERMINAL_URL
```

## Usage

### 1. Configure Claude Desktop

Add the server to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ssh-terminal": {
      "command": "node",
      "args": ["/path/to/ssh_terminal_mcp/server.js"]
    }
  }
}
```

### 2. Available Tools

- **open_terminal**: Open terminal URL for manual login
- **save_session**: Save browser session after login
- **execute_command**: Execute a terminal command
- **execute_and_read**: Execute command and extract output with OCR
- **take_screenshot**: Capture terminal screenshot
- **extract_text**: Extract text from current terminal view
- **disconnect**: Close browser connection
- **clear_session**: Clear saved session data

### 3. Typical Workflow

1. Open terminal URL with `open_terminal`
2. Login manually with your credentials
3. Save session with `save_session`
4. Execute commands with `execute_and_read` to get AI-readable output

## Security Notes

- **Never commit sensitive files**: The `.gitignore` is configured to exclude:
  - Session files (`session-state.json`)
  - Screenshots (`*.png`)
  - Test files with potential credentials
  - Environment files (`.env`)
- **Manual authentication**: Credentials are never stored or automated
- **Session persistence**: Browser sessions are stored locally and should not be shared

## Technical Details

- Built with MCP SDK v0.5.0
- Uses Playwright for browser automation
- Tesseract.js for OCR functionality
- Implements clear-before-command strategy for clean outputs

## Project Structure

```
ssh_terminal_mcp/
├── server.js          # Main MCP server implementation
├── package.json       # Dependencies and scripts
├── .gitignore        # Security-focused ignore patterns
└── README.md         # This file
```

## Troubleshooting

- **OCR accuracy**: Terminal fonts may affect OCR accuracy. The system is optimized for standard terminal fonts.
- **Session expiry**: If session expires, use `clear_session` and login again
- **Browser issues**: Ensure Chromium is properly installed with `npx playwright install chromium`

## License

This project is for internal use. Please ensure compliance with your organization's security policies.