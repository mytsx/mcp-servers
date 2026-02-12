# mcp-server-git-extended: Enhanced Git MCP Server

## Overview

An extended Model Context Protocol server for Git repository interaction and automation. This enhanced version provides comprehensive Git functionality including cherry-pick, reset modes, merge, rebase, push/pull, stash management, tag operations, **and powerful remote repository operations** - expanding far beyond the original mcp-server-git capabilities.

This extended server builds upon the original mcp-server-git to provide a complete Git workflow toolkit for Large Language Models, with support for both local and remote repository operations without requiring API tokens.

### Why Choose the Extended Version?

- **36 tools vs 13** in the original - complete Git workflow coverage
- **Token-efficient operations** - combined commands like `git_quick_fix` reduce AI token usage
- **Remote repository access** - explore and compare without switching branches
- **Advanced search** - built-in grep and commit message search
- **Recovery features** - undo operations for common mistakes
- **No API tokens required** - all remote operations use standard Git commands

### Tools

1. `git_status`
   - Shows the working tree status
   - Input:
     - `repo_path` (string): Path to Git repository
   - Returns: Current status of working directory as text output

2. `git_diff_unstaged`
   - Shows changes in working directory not yet staged
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `context_lines` (number, optional): Number of context lines to show (default: 3)
   - Returns: Diff output of unstaged changes

3. `git_diff_staged`
   - Shows changes that are staged for commit
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `context_lines` (number, optional): Number of context lines to show (default: 3)
   - Returns: Diff output of staged changes

4. `git_diff`
   - Shows differences between branches or commits
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `target` (string): Target branch or commit to compare with
     - `context_lines` (number, optional): Number of context lines to show (default: 3)
   - Returns: Diff output comparing current state with target

5. `git_commit`
   - Records changes to the repository
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `message` (string): Commit message
   - Returns: Confirmation with new commit hash

6. `git_add`
   - Adds file contents to the staging area
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `files` (string[]): Array of file paths to stage
   - Returns: Confirmation of staged files

7. `git_reset`
   - Unstages all staged changes
   - Input:
     - `repo_path` (string): Path to Git repository
   - Returns: Confirmation of reset operation

8. `git_log`
   - Shows the commit logs
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `max_count` (number, optional): Maximum number of commits to show (default: 10)
   - Returns: Array of commit entries with hash, author, date, and message

9. `git_create_branch`
   - Creates a new branch
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `branch_name` (string): Name of the new branch
     - `start_point` (string, optional): Starting point for the new branch
   - Returns: Confirmation of branch creation
10. `git_checkout`
   - Switches branches
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `branch_name` (string): Name of branch to checkout
   - Returns: Confirmation of branch switch
11. `git_show`
   - Shows the contents of a commit
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `revision` (string): The revision (commit hash, branch name, tag) to show
   - Returns: Contents of the specified commit
12. `git_init`
   - Initializes a Git repository
   - Inputs:
     - `repo_path` (string): Path to directory to initialize git repo
   - Returns: Confirmation of repository initialization

13. `git_branch`
   - List Git branches
   - Inputs:
     - `repo_path` (string): Path to the Git repository.
     - `branch_type` (string): Whether to list local branches ('local'), remote branches ('remote') or all branches('all').
     - `contains` (string, optional): The commit sha that branch should contain. Do not pass anything to this param if no commit sha is specified
     - `not_contains` (string, optional): The commit sha that branch should NOT contain. Do not pass anything to this param if no commit sha is specified
   - Returns: List of branches

14. `git_cherry_pick`
   - Apply the changes introduced by an existing commit
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `commit_sha` (string): The commit SHA to cherry-pick
     - `no_commit` (boolean, optional): Apply the change without creating a new commit (default: false)
   - Returns: Success or error message

15. `git_reset_mode`
   - Reset current HEAD to specified state with soft, mixed, or hard mode
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `mode` (string): Reset mode: 'soft', 'mixed', or 'hard'
     - `commit` (string, optional): Commit to reset to (default: HEAD)
   - Returns: Success or error message

16. `git_merge`
   - Merge a branch into the current branch
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `branch_name` (string): Branch to merge into current branch
     - `no_ff` (boolean, optional): Create a merge commit even if fast-forward is possible (default: false)
   - Returns: Success or error message

17. `git_rebase`
   - Reapply commits on top of another base branch
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `branch_name` (string): Branch to rebase onto
     - `interactive` (boolean, optional): Start an interactive rebase (not supported in this MCP server)
   - Returns: Success or error message

18. `git_push`
   - Push commits to a remote repository
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `remote` (string, optional): Remote repository name (default: origin)
     - `branch` (string, optional): Branch to push (default: current branch)
     - `force` (boolean, optional): Force push (default: false)
   - Returns: Success or error message

19. `git_pull`
   - Pull commits from a remote repository
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `remote` (string, optional): Remote repository name (default: origin)
     - `branch` (string, optional): Branch to pull (default: current branch)
   - Returns: Success or error message

20. `git_stash`
   - Manage stashed changes (now includes untracked files)
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `action` (string): Stash action: 'save', 'pop', 'list', 'apply', 'drop', 'clear'
     - `message` (string, optional): Message for stash save
     - `index` (number, optional): Stash index for apply/drop operations
   - Returns: Result of stash operation
   - **Note**: Enhanced to automatically include untracked files with `-u` flag

21. `git_tag`
   - Manage tags
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `action` (string): Tag action: 'create', 'list', 'delete'
     - `tag_name` (string, optional): Tag name for create/delete operations
     - `message` (string, optional): Tag message for annotated tags
     - `commit` (string, optional): Commit to tag (default: HEAD)
   - Returns: Result of tag operation

### Advanced Operations (New in Extended Version)

22. `git_quick_fix`
   - Quick add, commit, and optionally push changes
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `files` (string[]): Files to add and commit
     - `message` (string): Commit message
     - `push` (boolean, optional): Push to remote after commit (default: true)
     - `remote` (string, optional): Remote to push to (default: origin)
   - Returns: Success message with commit hash and push status
   - **Use case**: Rapidly commit and push changes with a single command

23. `git_sync`
   - Sync with remote: pull, rebase/merge, and push
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `remote` (string, optional): Remote to sync with (default: origin)
     - `branch` (string, optional): Branch to sync (default: current branch)
     - `rebase` (boolean, optional): Use rebase instead of merge (default: true)
   - Returns: Sync operation results
   - **Use case**: Keep local and remote branches in sync with one command

24. `git_undo`
   - Undo last operation (commit, merge, or rebase)
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `operation` (string): What to undo: 'commit', 'merge', 'rebase'
   - Returns: Status of undo operation
   - **Use case**: Quickly revert mistakes

25. `git_blame`
   - Show who last modified each line of a file
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `file_path` (string): File to blame
     - `line_range` (string, optional): Line range to blame (e.g., '10,20')
   - Returns: Blame information with commit details
   - **Use case**: Track down who made specific changes

26. `git_stats`
   - Show repository statistics and contributor info
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `since` (string, optional): Show stats since this date (e.g., '1 week ago')
     - `author` (string, optional): Filter by author
   - Returns: Repository statistics including contributors and changes
   - **Use case**: Get insights about repository activity

### Remote Repository Operations (New in Extended Version)

27. `git_remote_info`
   - Show remote repository information and URLs
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `remote` (string, optional): Remote name to get info about (default: origin)
   - Returns: Remote URLs, branches, and tracking information
   - **Use case**: Understand remote repository configuration

28. `git_clone`
   - Clone a repository from URL
   - Inputs:
     - `url` (string): Repository URL to clone
     - `target_path` (string, optional): Target directory path (default: repo name)
     - `branch` (string, optional): Specific branch to clone
   - Returns: Clone operation status
   - **Use case**: Clone repositories without leaving the chat

29. `git_fetch_all`
   - Fetch all remote branches with optional pruning
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `prune` (boolean, optional): Remove deleted remote branches (default: true)
   - Returns: Fetch operation results
   - **Use case**: Update all remote tracking branches

30. `git_track_remote`
   - Set local branch to track remote branch
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `branch_name` (string): Local branch name
     - `remote_branch` (string): Remote branch to track (e.g., origin/feature)
   - Returns: Tracking configuration status
   - **Use case**: Set up branch tracking relationships

31. `git_delete_remote_branch`
   - Delete a branch from remote repository
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `branch_name` (string): Branch name to delete from remote
     - `remote` (string, optional): Remote name (default: origin)
   - Returns: Deletion status
   - **Use case**: Clean up remote branches

32. `git_show_remote_file`
   - Show file content from remote branch
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `file_path` (string): File path to show
     - `ref` (string, optional): Remote ref (default: origin/main)
   - Returns: File content from remote branch
   - **Use case**: View files without switching branches

33. `git_ls_remote`
   - List files in remote branch
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `ref` (string, optional): Remote ref to list files from (default: origin/main)
     - `path` (string, optional): Specific path to list (default: root)
   - Returns: File listing from remote branch
   - **Use case**: Explore remote repository structure

34. `git_diff_remote`
   - Compare local with remote branch
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `remote_ref` (string, optional): Remote ref to compare with (default: origin/main)
     - `local_ref` (string, optional): Local ref to compare (default: HEAD)
   - Returns: Differences between local and remote
   - **Use case**: See what's different before pulling/pushing

### Search Operations (New in Extended Version)

35. `git_grep`
   - Search for pattern in repository files
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `pattern` (string): Pattern to search for
     - `path` (string, optional): Path to search in
     - `case_sensitive` (boolean, optional): Case sensitive search (default: true)
   - Returns: Search results with line numbers
   - **Use case**: Find code patterns across the repository

36. `git_log_search`
   - Search for pattern in commit messages
   - Inputs:
     - `repo_path` (string): Path to Git repository
     - `pattern` (string): Pattern to search in commit messages
     - `max_count` (number, optional): Maximum results to return (default: 20)
   - Returns: Matching commits
   - **Use case**: Find commits by message content

## Key Features Over Original mcp-server-git

| Feature | Original | Extended |
|---------|----------|----------|
| Basic Git Operations | ✓ | ✓ |
| Cherry-pick | ✗ | ✓ |
| Reset Modes (soft/mixed/hard) | ✗ | ✓ |
| Merge with options | ✗ | ✓ |
| Rebase | ✗ | ✓ |
| Push/Pull | ✗ | ✓ |
| Stash (with untracked files) | ✗ | ✓ |
| Tag Management | ✗ | ✓ |
| Quick Fix (add+commit+push) | ✗ | ✓ |
| Sync (pull+rebase+push) | ✗ | ✓ |
| Undo Operations | ✗ | ✓ |
| Blame | ✗ | ✓ |
| Repository Statistics | ✗ | ✓ |
| Remote Info | ✗ | ✓ |
| Clone | ✗ | ✓ |
| Remote Branch Management | ✗ | ✓ |
| Remote File Operations | ✗ | ✓ |
| Advanced Search (grep) | ✗ | ✓ |
| Commit Message Search | ✗ | ✓ |
| Command Logging | ✗ | ✓ |
| Web Interface for Logs | ✗ | ✓ |

## Installation

### From Source

Clone and install the extended version:

```bash
git clone https://github.com/yourusername/mcp-server-git-extended.git
cd mcp-server-git-extended
pip install -e .
```

### Using pip

```bash
pip install mcp-server-git-extended
```

After installation, you can run it as a script using:

```bash
python -m mcp_server_git
```

## Configuration

### Usage with Claude Desktop

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "git-extended": {
      "command": "/path/to/python",
      "args": ["-m", "mcp_server_git", "--repository", "/path/to/your/repo"],
      "env": {
        "GIT_AUTHOR_NAME": "Your Name",
        "GIT_AUTHOR_EMAIL": "your.email@example.com",
        "GIT_COMMITTER_NAME": "Your Name",
        "GIT_COMMITTER_EMAIL": "your.email@example.com"
      }
    }
  }
}
```

Example configuration:
```json
{
  "mcpServers": {
    "git-extended": {
      "command": "/Users/yourname/.pyenv/versions/3.11.9/bin/python",
      "args": ["-m", "mcp_server_git", "--repository", "/Users/yourname/projects/myrepo"],
      "cwd": "/path/to/mcp-server-git-extended",
      "env": {
        "GIT_AUTHOR_NAME": "John Doe",
        "GIT_AUTHOR_EMAIL": "john@example.com",
        "GIT_COMMITTER_NAME": "John Doe",
        "GIT_COMMITTER_EMAIL": "john@example.com"
      }
    }
  }
}
```

### Usage with VS Code

Add to your VS Code settings:

```json
{
  "mcp": {
    "servers": {
      "git-extended": {
        "command": "python",
        "args": ["-m", "mcp_server_git", "--repository", "${workspaceFolder}"]
      }
    }
  }
}
```

### Usage with Zed

Add to your Zed settings.json:

```json
{
  "context_servers": {
    "git-extended": {
      "command": {
        "path": "python",
        "args": ["-m", "mcp_server_git", "--repository", "/path/to/your/repo"]
      }
    }
  }
}
```

## Usage Examples

### Quick Development Workflow
```bash
# Make changes and quickly push them
git_quick_fix --files "src/main.py" "tests/test_main.py" --message "Fix bug in main function"

# Sync with remote before starting work
git_sync --remote origin --branch main

# If something goes wrong, undo the last commit
git_undo --operation commit
```

### Remote Repository Analysis
```bash
# Check what's different between local and remote
git_diff_remote --remote_ref origin/main

# View a file from production without switching branches
git_show_remote_file --file_path "config/production.yaml" --ref origin/production

# Search for a pattern across the entire repository
git_grep --pattern "TODO|FIXME" --case_sensitive false
```

### Collaborative Development
```bash
# See who made changes to a critical file
git_blame --file_path "src/auth.py" --line_range "50,100"

# Find commits related to a specific feature
git_log_search --pattern "authentication" --max_count 10

# Cherry-pick a bug fix from another branch
git_cherry_pick --commit_sha abc123def
```

## Benefits for AI Models

This extended Git MCP server is specifically designed to reduce token usage and improve efficiency for AI models:

1. **Combined Operations**: Commands like `git_quick_fix` and `git_sync` combine multiple Git operations into single calls, reducing the back-and-forth communication.

2. **Direct Remote Access**: Remote operations work without API tokens, using standard Git commands for security and simplicity.

3. **Comprehensive Information**: Tools like `git_stats` and `git_blame` provide rich context in single responses.

4. **Error Prevention**: The `git_undo` feature allows quick recovery from mistakes without complex command sequences.

5. **Search Efficiency**: Built-in grep and log search eliminate the need for multiple file reads.

## Command Logging and Web Interface

This extended version includes a comprehensive logging system that tracks all Git operations with a modern web interface for easy monitoring.

### Features

- 📊 **Automatic Logging**: All Git commands are automatically logged with execution time, arguments, and results
- 🌐 **Web Interface**: Modern, responsive UI built with FastAPI and Tailwind CSS
- ⚡ **Real-time Updates**: WebSocket support for live log streaming
- 🔍 **Search & Filter**: Search commands and filter by status
- 💾 **SQLite Storage**: Lightweight database stored in `~/.mcp-git-extended/logs.db`
- 🚀 **Easy Setup**: Single script to install dependencies and start the interface

### Getting Started

1. **Start the web interface**:
   ```bash
   cd mcp-server-git-extended
   ./start_web_interface.sh
   ```
   
   The script will:
   - Create a virtual environment (on first run)
   - Install all required dependencies
   - Start the web interface on http://localhost:5555

2. **View logs**: Open http://localhost:5555 in your browser

### Web Interface Features

- **Main Table View**: Shows command, arguments, status, duration, and timestamp
- **Details Modal**: Click "Details" to see full command output and errors
- **Real-time Updates**: New logs appear automatically without refresh
- **Search**: Filter logs by command name
- **Status Filter**: View only successful or failed commands

### Log Data Structure

Each log entry captures:
- **Command**: Git function name (e.g., `git_status`, `git_commit`)
- **Arguments**: Full arguments passed to the function
- **Output**: Command output (stdout)
- **Error**: Error messages if any
- **Duration**: Execution time in seconds
- **Status**: Success or error
- **Timestamp**: When the command was executed
- **Repository Path**: Which repository was affected

### Technical Details

- **Database**: SQLite with SQLModel ORM
- **Web Framework**: FastAPI with Uvicorn
- **Frontend**: Vanilla JavaScript with Tailwind CSS
- **Real-time**: WebSockets for live updates
- **Port Selection**: Automatically finds available port starting from 5555

## Debugging

You can use the MCP inspector to debug the server:

```
npx @modelcontextprotocol/inspector python -m mcp_server_git
```

Check logs for troubleshooting:
```
tail -n 50 -f ~/Library/Logs/Claude/mcp*.log
```

## Development

For local development:

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/mcp-server-git-extended.git
   cd mcp-server-git-extended
   ```

2. Install in development mode:
   ```bash
   pip install -e .
   ```

3. Test your changes using the MCP inspector:
   ```bash
   npx @modelcontextprotocol/inspector python -m mcp_server_git --repository /path/to/test/repo
   ```

4. For testing with Claude Desktop, update your `claude_desktop_config.json` to point to your development directory.

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This MCP server is licensed under the MIT License. This means you are free to use, modify, and distribute the software, subject to the terms and conditions of the MIT License. For more details, please see the LICENSE file in the project repository.
