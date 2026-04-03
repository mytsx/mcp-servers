# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

MCP server that enables AI assistants to interact with SSH terminals (ASGER/Guacamole) through Playwright browser automation. Uses a 3-layer hybrid text extraction: Guacamole buffer → base64 encoding → OCR fallback.

## Commands

### Development
```bash
npm install
npx playwright install chromium
cp .env.example .env
npm start
```

## Architecture

### Hybrid Text Extraction (v2.0)

Terminal renders to HTML5 Canvas (not DOM), so direct text access is impossible. Three extraction layers are tried in order:

1. **Layer 1 - Guacamole Buffer**: Injects JS into page to find Guacamole client's clipboard/text buffer. Fastest and most accurate when available.
2. **Layer 2 - Base64 Encoding**: Wraps command output to temp file, base64-encodes it, reads via OCR. Base64 charset (A-Za-z0-9+/=) is OCR-friendly. Decodes server-side for exact output. Returns exit code.
3. **Layer 3 - OCR Fallback**: Screenshot + Tesseract.js. Improved settings but still subject to typical OCR errors.

### MCP Tools

- `open_terminal`: Opens browser with terminal URL
- `save_session`: Persists browser session after manual login
- `execute_command`: Runs command (no output capture)
- `execute_and_read`: **Main tool** - runs command and returns output via hybrid extraction. Params: `method` (auto/buffer/base64/ocr), `wait_ms` (custom wait time)
- `take_screenshot`: Captures terminal screenshot
- `extract_text`: Extracts text from current view (buffer first, then OCR)
- `disconnect`: Closes browser connection
- `clear_session`: Removes saved session data

### Key Design Decisions

- **Security First**: Never store credentials, all authentication is manual
- **Hybrid Extraction**: buffer→base64→ocr cascade for reliability
- **Structured Output**: Returns method used, exit code, and screenshot path
- **Turkish Language**: Tool descriptions and messages are in Turkish

## Known Limitations

- Guacamole buffer (Layer 1) may not be accessible on all ASGER deployments
- Base64 (Layer 2) runs the command twice (once to execute, once to read encoded output)
- OCR (Layer 3) still has character confusion issues (0/O, 1/l/I, special chars)
- Canvas-based terminals prevent direct DOM text access
- Manual login required on first use or session expiry
