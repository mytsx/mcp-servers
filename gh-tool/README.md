# Gemini PR Reviews MCP Server

MCP (Model Context Protocol) server for fetching Gemini Code Assist reviews from GitHub pull requests. This tool allows Claude Desktop to retrieve and analyze code reviews from Gemini Code Assist bot on GitHub PRs.

## Features

- Fetch all Gemini Code Assist reviews from a GitHub PR
- Get reviews after your last `/gemini review` comment (default behavior)
- Smart defaults: auto-detect repository owner and last PR
- GitHub token authentication support
- Full pagination support for large PRs
- Retrieves all comment types (reviews, line comments, issue comments)
- Raw JSON output for maximum flexibility
- Easy installation with provided script

## Installation

### Option 1: Using uvx (Recommended)

No installation required! Just configure Claude Desktop:

```json
{
  "mcpServers": {
    "gemini-pr-reviews": {
      "command": "uvx",
      "args": ["mcp-gemini-pr-reviews"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

### Option 2: Install from PyPI

```bash
pip install mcp-gemini-pr-reviews
```

### Option 3: Install from Source

```bash
cd gh-tool
pip install -e .
# or
./install.sh
```

### GitHub Token Setup

1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Give it a name and select the `repo` scope
4. Copy the generated token

Create a `.env` file:
```bash
GITHUB_TOKEN=your_actual_github_token_here
```

## Configuration for Claude Desktop

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "gemini-pr-reviews": {
      "command": "uvx",
      "args": ["mcp-gemini-pr-reviews"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

## Available Tool

### `get_gemini_reviews`
Get Gemini Code Assist reviews from a GitHub PR. Can fetch all reviews or only those after your last '/gemini review' comment.

**Parameters:**
- `repo` (string, required): Repository name or owner/repo format
  - If just repo name: `"YtbMp3Indir"` - uses authenticated user as owner
  - Full format: `"owner/RepoName"`
- `pr` (integer, optional): PR number (uses last PR if not specified)
- `after_last_review` (boolean, optional): If true, only fetch reviews after your last '/gemini review' comment (default: **true**)
- `username` (string, optional): GitHub username (only used when after_last_review is true, defaults to authenticated user)

**Note:** The tool returns raw JSON data for maximum flexibility. By default, it fetches reviews after your last '/gemini review' comment.

## Usage Examples

1. **Simplest usage (most common) - Get reviews after your last comment:**
   ```
   Use get_gemini_reviews for repo YtbMp3Indir
   ```
   This automatically:
   - Uses your GitHub username as owner
   - Finds the last PR
   - Gets reviews after your last '/gemini review' comment

2. **Specify a PR number:**
   ```
   Use get_gemini_reviews for repo YtbMp3Indir pr 2
   ```

3. **Get ALL reviews (not just after your last comment):**
   ```
   Use get_gemini_reviews for repo YtbMp3Indir with after_last_review false
   ```

4. **Use full repo path (if needed):**
   ```
   Use get_gemini_reviews for repo someoneelse/TheirRepo
   ```

## How It Works

The server fetches Gemini Code Assist comments from GitHub PRs using the GitHub API v3. It supports three types of comments:
- **Reviews**: General PR reviews with overall feedback
- **Line Comments**: Code-specific comments on particular lines
- **Issue Comments**: General discussion comments on the PR

When `after_last_review` is true (default), the tool:
1. Finds your last `/gemini review` comment in the PR
2. Fetches all Gemini bot responses after that timestamp
3. Returns them sorted by type and date

## Notes

- The server requires Python 3.7+
- GitHub API rate limits apply (5000 requests/hour with token, 60 without)
- Authentication via GitHub token is highly recommended
- The server returns raw JSON data for maximum flexibility
- All API calls use pagination to handle large PRs
- Supports typo variants like "/genimi review"

## Testing

Run the test script to verify the server is working:
```bash
python3 test_raw_output.py
```

## Standalone Script

You can also use the original CLI script directly:
```bash
python3 gemini_pr_reviews.py --repo owner/repo --pr 123
```

## License

MIT