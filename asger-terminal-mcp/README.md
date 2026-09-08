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
- 📦 **Structured Output**: Every tool returns typed JSON — `execute_and_read` gives the output
  as both a string and a line array, plus the screenshot path
- ✋ **Destructive Command Confirmation**: `rm -rf`, `reboot`, `mkfs`, `kill -9`, package removal
  and similar are put to the user before they are typed into the terminal
- ⏳ **OCR Progress**: Long OCR passes report progress to the client
- 🗂️ **Screenshots Out of the Way**: written to a temp directory by default (`SCREENSHOT_DIR`)

## Prerequisites

- Node.js 20+
- npm or yarn
- Chromium browser (automatically installed by Playwright)

## Installation

### Option 1: Using npx (Recommended)

No installation required! Just configure Claude Desktop:

```json
{
  "mcpServers": {
    "ssh-terminal": {
      "command": "npx",
      "args": ["-y", "asger-terminal-mcp"],
      "env": {
        "TERMINAL_URL": "https://your-web-terminal-url"
      }
    }
  }
}
```

### Option 2: Install from npm

```bash
npm install -g asger-terminal-mcp
```

### Option 3: Install from Source

```bash
cd asger-terminal-mcp
npm install
npx playwright install chromium
cp .env.example .env
# Edit .env and set TERMINAL_URL
```

## Usage

### 1. Configure Claude Desktop

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "ssh-terminal": {
      "command": "npx",
      "args": ["-y", "asger-terminal-mcp"]
    }
  }
}
```

### 2. Available Tools

- **open_terminal**: Open terminal URL for manual login
- **save_session**: Save browser session after login
- **execute_command**: Execute a terminal command (destructive ones are confirmed first)
- **execute_and_read**: Execute command and extract output with OCR (confirmed the same way)
- **take_screenshot**: Capture terminal screenshot — returns the image itself, not just a path
- **extract_text**: Extract text from current terminal view
- **disconnect**: Close browser connection
- **clear_session**: Clear saved session data

### Prompt

- **terminal_arastir**: Investigate a question on the server one command at a time, treating
  OCR output as unreliable rather than as ground truth

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `TERMINAL_URL` | — | Terminal URL opened by `open_terminal` |
| `SESSION_FILE` | `session-state.json` next to the server | Where the browser session is saved |
| `SCREENSHOT_DIR` | `$TMPDIR/asger-terminal-mcp` | Where screenshots are written |
| `WAIT_AFTER_COMMAND` | `2000` | Milliseconds to wait after a command |
| `WAIT_AFTER_CLEAR` | `1000` | Milliseconds to wait after clearing the screen |
| `WAIT_AFTER_CLICK` | `500` | Milliseconds to wait after focusing the terminal |

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

- Built with MCP SDK 2.x (`@modelcontextprotocol/server@^2`), speaking the 2026-07-28 protocol
  revision while still serving older clients
- Uses Playwright for browser automation
- Tesseract.js for OCR functionality
- Implements clear-before-command strategy for clean outputs

### On OCR accuracy

The terminal is drawn to a canvas, so there is no DOM text to read: OCR of a screenshot is the
only text source available here. Every text result carries a caveat saying so, and
`extract_text` also returns the raw OCR output next to the extracted portion, so a wrong guess
is visible rather than silent. For anything where an exact value matters, check the screenshot.

## Project Structure

```
asger-terminal-mcp/
├── server.js          # Main MCP server implementation
├── test/smoke.mjs     # In-process smoke test (npm test)
├── package.json       # Dependencies and scripts
└── README.md          # This file
```

## Troubleshooting

- **OCR accuracy**: Terminal fonts may affect OCR accuracy. The system is optimized for standard terminal fonts.
- **Session expiry**: If session expires, use `clear_session` and login again
- **Browser issues**: Ensure Chromium is properly installed with `npx playwright install chromium`

## License

This project is for internal use. Please ensure compliance with your organization's security policies.