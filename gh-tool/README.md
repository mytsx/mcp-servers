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

1. Clone or download this repository

2. Run the installation script:
   ```bash
   cd /path/to/gh_tool
   ./install.sh
   ```
   
   This will:
   - Create a Python virtual environment
   - Install all required dependencies
   - Create a `.env` file (if it doesn't exist)
   - Make scripts executable

3. Edit the `.env` file with your GitHub token:
   ```bash
   GITHUB_TOKEN=your_actual_github_token_here
   ```

   To get a GitHub token:
   - Go to https://github.com/settings/tokens
   - Click "Generate new token (classic)"
   - Give it a name and select the `repo` scope
   - Copy the generated token

## Configuration for Claude Desktop

Add this server to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "gemini-pr-reviews": {
      "command": "/path/to/gh_tool/run.sh"
    }
  }
}
```

Replace `/path/to/gh_tool` with the actual path to this directory.

**Note:** The `run.sh` script automatically activates the virtual environment and runs the server. Your GitHub token should be in the `.env` file.

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