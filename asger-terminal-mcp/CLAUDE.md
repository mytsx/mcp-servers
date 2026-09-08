# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is an MCP (Model Context Protocol) server that enables AI assistants to interact with SSH terminals through web browsers using Playwright automation and OCR text extraction.

## Commands

### Development
```bash
# Install dependencies (including Playwright browsers)
npm install
npx playwright install chromium

# Setup environment
cp .env.example .env
# Edit .env and set TERMINAL_URL

# Start the MCP server
npm start

# Run the smoke test (in-process, no browser launched)
npm test
```

## Architecture

### Core Components

1. **MCP Server Implementation** (`server.js`):
   - Uses `@modelcontextprotocol/server` 2.x, speaking protocol revision 2026-07-28
     while still serving 2025-era clients
   - `buildServer()` is a factory; `serveStdio(buildServer)` pins one instance per
     connection, which is what makes the 2026 era available over stdio
   - Tools are registered with `registerTool` and Zod schemas; every tool declares an
     `outputSchema` and returns `structuredContent`
   - Browser state (browser, context, page) is module-level: it outlives any one
     connection
   - Session persistence through `session-state.json`, overridable with `SESSION_FILE`

2. **Browser Automation**:
   - Playwright with Chromium in non-headless mode
   - Manual authentication workflow (no credential automation)
   - Session state saved/loaded to avoid repeated logins

3. **Text Extraction Strategy**:
   - Terminal renders in Canvas element (not DOM text)
   - Screenshots captured after command execution
   - Tesseract.js OCR extracts text from screenshots
   - Clear-before-command pattern for cleaner outputs

### Key Design Decisions

- **Security First**: Never store credentials, all authentication is manual
- **Session Persistence**: Browser cookies/storage saved locally
- **OCR Approach**: Terminal Canvas rendering requires image-based text extraction
- **Turkish Language**: Tool descriptions and messages are in Turkish
- **Confirm Before Destroying**: `execute_command` and `execute_and_read` put destructive
  commands to the user through elicitation before typing them. A client that cannot ask
  gets a refusal — never an unconfirmed run
- **Honest About OCR**: every text result carries a caveat, and `extract_text` also returns
  the raw OCR output, so a misread is visible rather than presented as fact
- **Screenshots Out of the Checkout**: written to `SCREENSHOT_DIR` (a temp dir by default)

### MCP Tools Available

- `open_terminal`: Opens browser with terminal URL
- `save_session`: Persists browser session after manual login
- `execute_command`: Runs command with optional screen clear
- `execute_and_read`: Executes command and returns OCR-extracted output
- `take_screenshot`: Captures terminal screenshot
- `extract_text`: Runs OCR on current terminal view
- `disconnect`: Closes browser connection
- `clear_session`: Removes saved session data

## Important Files to Ignore

The `.gitignore` is configured to exclude:
- `session-state.json` (browser session data)
- `*.png` files (screenshots)
- `.env` files

## Known Limitations

- OCR accuracy depends on terminal font and clarity
- Canvas-based terminals prevent direct DOM text access
- Manual login required on first use or session expiry
- Turkish language in tool descriptions (by design)