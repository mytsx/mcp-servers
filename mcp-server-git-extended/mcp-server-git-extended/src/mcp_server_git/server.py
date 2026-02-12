import logging
from pathlib import Path
from typing import Sequence, Optional
import asyncio
import threading

from mcp.server import Server
from mcp.server.session import ServerSession
from mcp.server.stdio import stdio_server
from mcp.types import (
    ClientCapabilities,
    TextContent,
    Tool,
    ListRootsResult,
    RootsCapability,
)
from enum import Enum
import git
from pydantic import BaseModel, Field

from .logger import log_command
from .web_interface import start_web_server

# Default number of context lines to show in diff output
DEFAULT_CONTEXT_LINES = 3

class GitStatus(BaseModel):
    repo_path: str

class GitDiffUnstaged(BaseModel):
    repo_path: str
    context_lines: int = DEFAULT_CONTEXT_LINES

class GitDiffStaged(BaseModel):
    repo_path: str
    context_lines: int = DEFAULT_CONTEXT_LINES

class GitDiff(BaseModel):
    repo_path: str
    target: str
    context_lines: int = DEFAULT_CONTEXT_LINES

class GitCommit(BaseModel):
    repo_path: str
    message: str

class GitAdd(BaseModel):
    repo_path: str
    files: list[str]

class GitReset(BaseModel):
    repo_path: str

class GitLog(BaseModel):
    repo_path: str
    max_count: int = 10

class GitCreateBranch(BaseModel):
    repo_path: str
    branch_name: str
    base_branch: str | None = None

class GitCheckout(BaseModel):
    repo_path: str
    branch_name: str

class GitShow(BaseModel):
    repo_path: str
    revision: str

class GitInit(BaseModel):
    repo_path: str

class GitBranch(BaseModel):
    repo_path: str = Field(
        ...,
        description="The path to the Git repository.",
    )
    branch_type: str = Field(
        ...,
        description="Whether to list local branches ('local'), remote branches ('remote') or all branches('all').",
    )
    contains: Optional[str] = Field(
        None,
        description="The commit sha that branch should contain. Do not pass anything to this param if no commit sha is specified",
    )
    not_contains: Optional[str] = Field(
        None,
        description="The commit sha that branch should NOT contain. Do not pass anything to this param if no commit sha is specified",
    )

class GitCherryPick(BaseModel):
    repo_path: str
    commit_sha: str = Field(
        ...,
        description="The commit SHA to cherry-pick"
    )
    no_commit: bool = Field(
        False,
        description="Apply the change without creating a new commit"
    )

class GitResetMode(BaseModel):
    repo_path: str
    mode: str = Field(
        ...,
        description="Reset mode: 'soft', 'mixed', or 'hard'"
    )
    commit: str = Field(
        "HEAD",
        description="Commit to reset to (default: HEAD)"
    )

class GitMerge(BaseModel):
    repo_path: str
    branch_name: str = Field(
        ...,
        description="Branch to merge into current branch"
    )
    no_ff: bool = Field(
        False,
        description="Create a merge commit even if fast-forward is possible"
    )

class GitRebase(BaseModel):
    repo_path: str
    branch_name: str = Field(
        ...,
        description="Branch to rebase onto"
    )
    interactive: bool = Field(
        False,
        description="Start an interactive rebase"
    )

class GitPush(BaseModel):
    repo_path: str
    remote: str = Field(
        "origin",
        description="Remote repository name (default: origin)"
    )
    branch: Optional[str] = Field(
        None,
        description="Branch to push (default: current branch)"
    )
    force: bool = Field(
        False,
        description="Force push"
    )

class GitPull(BaseModel):
    repo_path: str
    remote: str = Field(
        "origin",
        description="Remote repository name (default: origin)"
    )
    branch: Optional[str] = Field(
        None,
        description="Branch to pull (default: current branch)"
    )

class GitStash(BaseModel):
    repo_path: str
    action: str = Field(
        ...,
        description="Stash action: 'save', 'pop', 'list', 'apply', 'drop', 'clear'"
    )
    message: Optional[str] = Field(
        None,
        description="Message for stash save"
    )
    index: Optional[int] = Field(
        None,
        description="Stash index for apply/drop operations"
    )

class GitTag(BaseModel):
    repo_path: str
    action: str = Field(
        ...,
        description="Tag action: 'create', 'list', 'delete'"
    )
    tag_name: Optional[str] = Field(
        None,
        description="Tag name for create/delete operations"
    )
    message: Optional[str] = Field(
        None,
        description="Tag message for annotated tags"
    )
    commit: str = Field(
        "HEAD",
        description="Commit to tag (default: HEAD)"
    )

class GitQuickFix(BaseModel):
    repo_path: str
    files: list[str] = Field(
        ...,
        description="Files to add and commit"
    )
    message: str = Field(
        ...,
        description="Commit message"
    )
    push: bool = Field(
        True,
        description="Push to remote after commit (default: true)"
    )
    remote: str = Field(
        "origin",
        description="Remote to push to (default: origin)"
    )

class GitSync(BaseModel):
    repo_path: str
    remote: str = Field(
        "origin",
        description="Remote to sync with (default: origin)"
    )
    branch: Optional[str] = Field(
        None,
        description="Branch to sync (default: current branch)"
    )
    rebase: bool = Field(
        True,
        description="Use rebase instead of merge (default: true)"
    )

class GitUndo(BaseModel):
    repo_path: str
    operation: str = Field(
        ...,
        description="What to undo: 'commit', 'merge', 'rebase'"
    )
    
class GitBlame(BaseModel):
    repo_path: str
    file_path: str = Field(
        ...,
        description="File to blame"
    )
    line_range: Optional[str] = Field(
        None,
        description="Line range to blame (e.g., '10,20')"
    )

class GitStats(BaseModel):
    repo_path: str
    since: Optional[str] = Field(
        None,
        description="Show stats since this date (e.g., '1 week ago')"
    )
    author: Optional[str] = Field(
        None,
        description="Filter by author"
    )

class GitRemoteInfo(BaseModel):
    repo_path: str
    remote: str = Field(
        "origin",
        description="Remote name to get info about (default: origin)"
    )

class GitClone(BaseModel):
    url: str = Field(
        ...,
        description="Repository URL to clone"
    )
    target_path: Optional[str] = Field(
        None,
        description="Target directory path (default: repo name)"
    )
    branch: Optional[str] = Field(
        None,
        description="Specific branch to clone"
    )

class GitFetchAll(BaseModel):
    repo_path: str
    prune: bool = Field(
        True,
        description="Remove deleted remote branches (default: true)"
    )

class GitTrackRemote(BaseModel):
    repo_path: str
    branch_name: str = Field(
        ...,
        description="Local branch name"
    )
    remote_branch: str = Field(
        ...,
        description="Remote branch to track (e.g., origin/feature)"
    )

class GitDeleteRemoteBranch(BaseModel):
    repo_path: str
    branch_name: str = Field(
        ...,
        description="Branch name to delete from remote"
    )
    remote: str = Field(
        "origin",
        description="Remote name (default: origin)"
    )

class GitShowRemoteFile(BaseModel):
    repo_path: str
    file_path: str = Field(
        ...,
        description="File path to show"
    )
    ref: str = Field(
        "origin/main",
        description="Remote ref (default: origin/main)"
    )

class GitLsRemote(BaseModel):
    repo_path: str
    ref: str = Field(
        "origin/main",
        description="Remote ref to list files from"
    )
    path: Optional[str] = Field(
        None,
        description="Specific path to list (default: root)"
    )

class GitDiffRemote(BaseModel):
    repo_path: str
    remote_ref: str = Field(
        "origin/main",
        description="Remote ref to compare with"
    )
    local_ref: str = Field(
        "HEAD",
        description="Local ref to compare (default: HEAD)"
    )

class GitGrep(BaseModel):
    repo_path: str
    pattern: str = Field(
        ...,
        description="Pattern to search for"
    )
    path: Optional[str] = Field(
        None,
        description="Path to search in"
    )
    case_sensitive: bool = Field(
        True,
        description="Case sensitive search (default: true)"
    )

class GitLogSearch(BaseModel):
    repo_path: str
    pattern: str = Field(
        ...,
        description="Pattern to search in commit messages"
    )
    max_count: int = Field(
        20,
        description="Maximum results to return (default: 20)"
    )

class GitTools(str, Enum):
    STATUS = "git_status"
    DIFF_UNSTAGED = "git_diff_unstaged"
    DIFF_STAGED = "git_diff_staged"
    DIFF = "git_diff"
    COMMIT = "git_commit"
    ADD = "git_add"
    RESET = "git_reset"
    LOG = "git_log"
    CREATE_BRANCH = "git_create_branch"
    CHECKOUT = "git_checkout"
    SHOW = "git_show"
    INIT = "git_init"
    BRANCH = "git_branch"
    CHERRY_PICK = "git_cherry_pick"
    RESET_MODE = "git_reset_mode"
    MERGE = "git_merge"
    REBASE = "git_rebase"
    PUSH = "git_push"
    PULL = "git_pull"
    STASH = "git_stash"
    TAG = "git_tag"
    QUICK_FIX = "git_quick_fix"
    SYNC = "git_sync"
    UNDO = "git_undo"
    BLAME = "git_blame"
    STATS = "git_stats"
    REMOTE_INFO = "git_remote_info"
    CLONE = "git_clone"
    FETCH_ALL = "git_fetch_all"
    TRACK_REMOTE = "git_track_remote"
    DELETE_REMOTE_BRANCH = "git_delete_remote_branch"
    SHOW_REMOTE_FILE = "git_show_remote_file"
    LS_REMOTE = "git_ls_remote"
    DIFF_REMOTE = "git_diff_remote"
    GREP = "git_grep"
    LOG_SEARCH = "git_log_search"

@log_command
def git_status(repo: git.Repo) -> str:
    return repo.git.status()

@log_command
def git_diff_unstaged(repo: git.Repo, context_lines: int = DEFAULT_CONTEXT_LINES) -> str:
    return repo.git.diff(f"--unified={context_lines}")

@log_command
def git_diff_staged(repo: git.Repo, context_lines: int = DEFAULT_CONTEXT_LINES) -> str:
    return repo.git.diff(f"--unified={context_lines}", "--cached")

@log_command
def git_diff(repo: git.Repo, target: str, context_lines: int = DEFAULT_CONTEXT_LINES) -> str:
    return repo.git.diff(f"--unified={context_lines}", target)

@log_command
def git_commit(repo: git.Repo, message: str) -> str:
    commit = repo.index.commit(message)
    return f"Changes committed successfully with hash {commit.hexsha}"

@log_command
def git_add(repo: git.Repo, files: list[str]) -> str:
    repo.index.add(files)
    return "Files staged successfully"

@log_command
def git_reset(repo: git.Repo) -> str:
    repo.index.reset()
    return "All staged changes reset"

@log_command
def git_log(repo: git.Repo, max_count: int = 10) -> list[str]:
    commits = list(repo.iter_commits(max_count=max_count))
    log = []
    for commit in commits:
        log.append(
            f"Commit: {commit.hexsha!r}\n"
            f"Author: {commit.author!r}\n"
            f"Date: {commit.authored_datetime}\n"
            f"Message: {commit.message!r}\n"
        )
    return log

@log_command
def git_create_branch(repo: git.Repo, branch_name: str, base_branch: str | None = None) -> str:
    if base_branch:
        base = repo.references[base_branch]
    else:
        base = repo.active_branch

    repo.create_head(branch_name, base)
    return f"Created branch '{branch_name}' from '{base.name}'"

@log_command
def git_checkout(repo: git.Repo, branch_name: str) -> str:
    repo.git.checkout(branch_name)
    return f"Switched to branch '{branch_name}'"

@log_command
def git_init(repo_path: str) -> str:
    try:
        repo = git.Repo.init(path=repo_path, mkdir=True)
        return f"Initialized empty Git repository in {repo.git_dir}"
    except Exception as e:
        return f"Error initializing repository: {str(e)}"

@log_command
def git_show(repo: git.Repo, revision: str) -> str:
    commit = repo.commit(revision)
    output = [
        f"Commit: {commit.hexsha!r}\n"
        f"Author: {commit.author!r}\n"
        f"Date: {commit.authored_datetime!r}\n"
        f"Message: {commit.message!r}\n"
    ]
    if commit.parents:
        parent = commit.parents[0]
        diff = parent.diff(commit, create_patch=True)
    else:
        diff = commit.diff(git.NULL_TREE, create_patch=True)
    for d in diff:
        output.append(f"\n--- {d.a_path}\n+++ {d.b_path}\n")
        output.append(d.diff.decode('utf-8'))
    return "".join(output)

@log_command
def git_branch(repo: git.Repo, branch_type: str, contains: str | None = None, not_contains: str | None = None) -> str:
    match contains:
        case None:
            contains_sha = (None,)
        case _:
            contains_sha = ("--contains", contains)

    match not_contains:
        case None:
            not_contains_sha = (None,)
        case _:
            not_contains_sha = ("--no-contains", not_contains)

    match branch_type:
        case 'local':
            b_type = None
        case 'remote':
            b_type = "-r"
        case 'all':
            b_type = "-a"
        case _:
            return f"Invalid branch type: {branch_type}"

    # None value will be auto deleted by GitPython
    branch_info = repo.git.branch(b_type, *contains_sha, *not_contains_sha)

    return branch_info

@log_command
def git_cherry_pick(repo: git.Repo, commit_sha: str, no_commit: bool = False) -> str:
    try:
        if no_commit:
            repo.git.cherry_pick(commit_sha, "--no-commit")
            return f"Applied changes from commit {commit_sha} without creating a new commit"
        else:
            repo.git.cherry_pick(commit_sha)
            return f"Successfully cherry-picked commit {commit_sha}"
    except Exception as e:
        return f"Error cherry-picking commit {commit_sha}: {str(e)}"

@log_command
def git_reset_mode(repo: git.Repo, mode: str, commit: str = "HEAD") -> str:
    try:
        if mode not in ["soft", "mixed", "hard"]:
            return f"Invalid reset mode: {mode}. Use 'soft', 'mixed', or 'hard'"
        
        repo.git.reset(f"--{mode}", commit)
        return f"Successfully reset to {commit} with {mode} mode"
    except Exception as e:
        return f"Error resetting repository: {str(e)}"

@log_command
def git_merge(repo: git.Repo, branch_name: str, no_ff: bool = False) -> str:
    try:
        if no_ff:
            repo.git.merge(branch_name, "--no-ff")
        else:
            repo.git.merge(branch_name)
        return f"Successfully merged branch '{branch_name}' into current branch"
    except Exception as e:
        return f"Error merging branch '{branch_name}': {str(e)}"

@log_command
def git_rebase(repo: git.Repo, branch_name: str, interactive: bool = False) -> str:
    try:
        if interactive:
            return "Interactive rebase is not supported in this MCP server. Use regular rebase instead."
        repo.git.rebase(branch_name)
        return f"Successfully rebased current branch onto '{branch_name}'"
    except Exception as e:
        return f"Error rebasing onto '{branch_name}': {str(e)}"

@log_command
def git_push(repo: git.Repo, remote: str = "origin", branch: str | None = None, force: bool = False) -> str:
    try:
        if branch is None:
            branch = repo.active_branch.name
        
        if force:
            repo.git.push(remote, branch, "--force")
            return f"Force pushed branch '{branch}' to remote '{remote}'"
        else:
            repo.git.push(remote, branch)
            return f"Successfully pushed branch '{branch}' to remote '{remote}'"
    except Exception as e:
        return f"Error pushing to remote: {str(e)}"

@log_command
def git_pull(repo: git.Repo, remote: str = "origin", branch: str | None = None) -> str:
    try:
        if branch is None:
            branch = repo.active_branch.name
        
        repo.git.pull(remote, branch)
        return f"Successfully pulled from '{remote}/{branch}'"
    except Exception as e:
        return f"Error pulling from remote: {str(e)}"

@log_command
def git_stash(repo: git.Repo, action: str, message: str | None = None, index: int | None = None) -> str:
    try:
        match action:
            case "save":
                if message:
                    repo.git.stash("push", "-u", "-m", message)
                    return f"Stashed changes with message: {message} (including untracked files)"
                else:
                    repo.git.stash("push", "-u")
                    return "Stashed changes (including untracked files)"
            case "pop":
                if index is not None:
                    repo.git.stash("pop", f"stash@{{{index}}}")
                    return f"Popped stash@{{{index}}}"
                else:
                    repo.git.stash("pop")
                    return "Popped latest stash"
            case "list":
                stash_list = repo.git.stash("list")
                return f"Stash list:\n{stash_list}" if stash_list else "No stashes found"
            case "apply":
                if index is not None:
                    repo.git.stash("apply", f"stash@{{{index}}}")
                    return f"Applied stash@{{{index}}}"
                else:
                    repo.git.stash("apply")
                    return "Applied latest stash"
            case "drop":
                if index is not None:
                    repo.git.stash("drop", f"stash@{{{index}}}")
                    return f"Dropped stash@{{{index}}}"
                else:
                    repo.git.stash("drop")
                    return "Dropped latest stash"
            case "clear":
                repo.git.stash("clear")
                return "Cleared all stashes"
            case _:
                return f"Invalid stash action: {action}"
    except Exception as e:
        return f"Error with stash operation: {str(e)}"

@log_command
def git_tag(repo: git.Repo, action: str, tag_name: str | None = None, message: str | None = None, commit: str = "HEAD") -> str:
    try:
        match action:
            case "create":
                if not tag_name:
                    return "Tag name is required for create action"
                if message:
                    repo.create_tag(tag_name, commit, message=message)
                    return f"Created annotated tag '{tag_name}' at commit {commit}"
                else:
                    repo.create_tag(tag_name, commit)
                    return f"Created lightweight tag '{tag_name}' at commit {commit}"
            case "list":
                tags = [str(tag) for tag in repo.tags]
                return f"Tags:\n" + "\n".join(tags) if tags else "No tags found"
            case "delete":
                if not tag_name:
                    return "Tag name is required for delete action"
                repo.delete_tag(tag_name)
                return f"Deleted tag '{tag_name}'"
            case _:
                return f"Invalid tag action: {action}"
    except Exception as e:
        return f"Error with tag operation: {str(e)}"

@log_command
def git_quick_fix(repo: git.Repo, files: list[str], message: str, push: bool = True, remote: str = "origin") -> str:
    try:
        # Add files
        repo.index.add(files)
        
        # Commit
        commit = repo.index.commit(message)
        result = f"Files added and committed with hash {commit.hexsha}"
        
        # Push if requested
        if push:
            branch = repo.active_branch.name
            repo.git.push(remote, branch)
            result += f"\nPushed to {remote}/{branch}"
        
        return result
    except Exception as e:
        return f"Error in quick fix: {str(e)}"

@log_command
def git_sync(repo: git.Repo, remote: str = "origin", branch: str | None = None, rebase: bool = True) -> str:
    try:
        if branch is None:
            branch = repo.active_branch.name
        
        # Fetch latest
        repo.git.fetch(remote)
        
        # Pull with rebase or merge
        if rebase:
            repo.git.pull(remote, branch, "--rebase")
            result = f"Pulled and rebased from {remote}/{branch}"
        else:
            repo.git.pull(remote, branch)
            result = f"Pulled and merged from {remote}/{branch}"
        
        # Push back
        repo.git.push(remote, branch)
        result += f"\nPushed to {remote}/{branch}"
        
        return result
    except Exception as e:
        return f"Error syncing repository: {str(e)}"

@log_command
def git_undo(repo: git.Repo, operation: str) -> str:
    try:
        match operation:
            case "commit":
                # Undo last commit but keep changes
                repo.git.reset("--soft", "HEAD~1")
                return "Undid last commit, changes are staged"
            case "merge":
                # Check if we're in a merge state by checking for MERGE_HEAD
                merge_head_path = Path(repo.git_dir) / "MERGE_HEAD"
                if merge_head_path.exists():
                    repo.git.merge("--abort")
                    return "Aborted ongoing merge"
                else:
                    # Undo last merge commit
                    repo.git.reset("--hard", "HEAD~1")
                    return "Undid last merge"
            case "rebase":
                try:
                    repo.git.rebase("--abort")
                    return "Aborted rebase"
                except git.GitCommandError:
                    return "No rebase in progress"
            case _:
                return f"Invalid operation: {operation}. Use 'commit', 'merge', or 'rebase'"
    except Exception as e:
        return f"Error undoing operation: {str(e)}"

@log_command
def git_blame(repo: git.Repo, file_path: str, line_range: str | None = None) -> str:
    try:
        if line_range:
            # Parse line range like "10,20"
            blame_output = repo.git.blame(f"-L{line_range}", file_path)
        else:
            blame_output = repo.git.blame(file_path)
        
        return f"Blame for {file_path}:\n{blame_output}"
    except Exception as e:
        return f"Error running blame: {str(e)}"

@log_command
def git_stats(repo: git.Repo, since: str | None = None, author: str | None = None) -> str:
    try:
        args = ["--stat", "--summary"]
        
        if since:
            args.append(f"--since='{since}'")
        
        if author:
            args.append(f"--author='{author}'")
        
        # Get shortlog for contributor stats
        shortlog_args = ["-sn"]
        if since:
            shortlog_args.append(f"--since='{since}'")
        
        shortlog = repo.git.shortlog(*shortlog_args)
        
        # Get general stats
        log_stats = repo.git.log(*args)
        
        result = "Repository Statistics:\n\n"
        result += "Contributors:\n"
        result += shortlog + "\n\n"
        
        if since:
            result += f"Changes since {since}:\n"
        result += log_stats
        
        return result
    except Exception as e:
        return f"Error getting stats: {str(e)}"

@log_command
def git_remote_info(repo: git.Repo, remote: str = "origin") -> str:
    try:
        # Get remote URLs
        remotes = repo.git.remote("-v")
        
        # Get remote branches
        remote_info = repo.git.remote("show", remote)
        
        result = f"Remote: {remote}\n\n"
        result += "URLs:\n"
        result += remotes + "\n\n"
        result += "Detailed Info:\n"
        result += remote_info
        
        return result
    except Exception as e:
        return f"Error getting remote info: {str(e)}"

@log_command
def git_clone(url: str, target_path: str | None = None, branch: str | None = None) -> str:
    try:
        args = [url]
        
        if target_path:
            args.append(target_path)
        
        if branch:
            args.extend(["-b", branch])
        
        # Clone the repository
        git.Repo.clone_from(url, target_path or url.split('/')[-1].replace('.git', ''), branch=branch)
        
        return f"Successfully cloned {url}" + (f" to {target_path}" if target_path else "")
    except Exception as e:
        return f"Error cloning repository: {str(e)}"

@log_command
def git_fetch_all(repo: git.Repo, prune: bool = True) -> str:
    try:
        if prune:
            result = repo.git.fetch("--all", "--prune")
        else:
            result = repo.git.fetch("--all")
        
        return f"Fetched all remotes\n{result}" if result else "Fetched all remotes successfully"
    except Exception as e:
        return f"Error fetching remotes: {str(e)}"

@log_command
def git_track_remote(repo: git.Repo, branch_name: str, remote_branch: str) -> str:
    try:
        # Set upstream branch
        repo.git.branch("-u", remote_branch, branch_name)
        return f"Branch '{branch_name}' now tracks '{remote_branch}'"
    except Exception as e:
        return f"Error setting upstream branch: {str(e)}"

@log_command
def git_delete_remote_branch(repo: git.Repo, branch_name: str, remote: str = "origin") -> str:
    try:
        # Delete remote branch
        repo.git.push(remote, "--delete", branch_name)
        return f"Deleted branch '{branch_name}' from remote '{remote}'"
    except Exception as e:
        return f"Error deleting remote branch: {str(e)}"

@log_command
def git_show_remote_file(repo: git.Repo, file_path: str, ref: str = "origin/main") -> str:
    try:
        # Show file content from remote ref
        content = repo.git.show(f"{ref}:{file_path}")
        return f"Content of {file_path} from {ref}:\n\n{content}"
    except Exception as e:
        return f"Error showing remote file: {str(e)}"

@log_command
def git_ls_remote(repo: git.Repo, ref: str = "origin/main", path: str | None = None) -> str:
    try:
        if path:
            # List specific path
            tree_content = repo.git.ls_tree("-r", ref, path)
        else:
            # List root
            tree_content = repo.git.ls_tree("-r", ref)
        
        return f"Files in {ref}" + (f" at {path}" if path else "") + f":\n{tree_content}"
    except Exception as e:
        return f"Error listing remote files: {str(e)}"

@log_command
def git_diff_remote(repo: git.Repo, remote_ref: str = "origin/main", local_ref: str = "HEAD") -> str:
    try:
        # Compare local with remote
        diff = repo.git.diff(local_ref, remote_ref)
        
        if not diff:
            return f"No differences between {local_ref} and {remote_ref}"
        
        return f"Differences between {local_ref} and {remote_ref}:\n{diff}"
    except Exception as e:
        return f"Error comparing with remote: {str(e)}"

@log_command
def git_grep(repo: git.Repo, pattern: str, path: str | None = None, case_sensitive: bool = True) -> str:
    try:
        args = ["-n"]  # Show line numbers
        
        if not case_sensitive:
            args.append("-i")
        
        args.append(pattern)
        
        if path:
            args.extend(["--", path])
        
        try:
            results = repo.git.grep(*args)
            return f"Search results for '{pattern}':\n{results}"
        except git.exc.GitCommandError:
            return f"No matches found for '{pattern}'"
    except Exception as e:
        return f"Error searching: {str(e)}"

@log_command
def git_log_search(repo: git.Repo, pattern: str, max_count: int = 20) -> str:
    try:
        # Search in commit messages
        log_results = repo.git.log(f"--grep={pattern}", f"--max-count={max_count}", "--oneline")
        
        if not log_results:
            return f"No commits found matching '{pattern}'"
        
        return f"Commits matching '{pattern}':\n{log_results}"
    except Exception as e:
        return f"Error searching logs: {str(e)}"

async def serve(repository: Path | None) -> None:
    logger = logging.getLogger(__name__)

    if repository is not None:
        try:
            git.Repo(repository)
            logger.info(f"Using repository at {repository}")
        except git.InvalidGitRepositoryError:
            logger.error(f"{repository} is not a valid Git repository")
            return

    # Start the web interface in a background thread
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    server = Server("mcp-git")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name=GitTools.STATUS,
                description="Shows the working tree status",
                inputSchema=GitStatus.model_json_schema(),
            ),
            Tool(
                name=GitTools.DIFF_UNSTAGED,
                description="Shows changes in the working directory that are not yet staged",
                inputSchema=GitDiffUnstaged.model_json_schema(),
            ),
            Tool(
                name=GitTools.DIFF_STAGED,
                description="Shows changes that are staged for commit",
                inputSchema=GitDiffStaged.model_json_schema(),
            ),
            Tool(
                name=GitTools.DIFF,
                description="Shows differences between branches or commits",
                inputSchema=GitDiff.model_json_schema(),
            ),
            Tool(
                name=GitTools.COMMIT,
                description="Records changes to the repository",
                inputSchema=GitCommit.model_json_schema(),
            ),
            Tool(
                name=GitTools.ADD,
                description="Adds file contents to the staging area",
                inputSchema=GitAdd.model_json_schema(),
            ),
            Tool(
                name=GitTools.RESET,
                description="Unstages all staged changes",
                inputSchema=GitReset.model_json_schema(),
            ),
            Tool(
                name=GitTools.LOG,
                description="Shows the commit logs",
                inputSchema=GitLog.model_json_schema(),
            ),
            Tool(
                name=GitTools.CREATE_BRANCH,
                description="Creates a new branch from an optional base branch",
                inputSchema=GitCreateBranch.model_json_schema(),
            ),
            Tool(
                name=GitTools.CHECKOUT,
                description="Switches branches",
                inputSchema=GitCheckout.model_json_schema(),
            ),
            Tool(
                name=GitTools.SHOW,
                description="Shows the contents of a commit",
                inputSchema=GitShow.model_json_schema(),
            ),
            Tool(
                name=GitTools.INIT,
                description="Initialize a new Git repository",
                inputSchema=GitInit.model_json_schema(),
            ),
            Tool(
                name=GitTools.BRANCH,
                description="List Git branches",
                inputSchema=GitBranch.model_json_schema(),
            ),
            Tool(
                name=GitTools.CHERRY_PICK,
                description="Apply the changes introduced by an existing commit",
                inputSchema=GitCherryPick.model_json_schema(),
            ),
            Tool(
                name=GitTools.RESET_MODE,
                description="Reset current HEAD to specified state with soft, mixed, or hard mode",
                inputSchema=GitResetMode.model_json_schema(),
            ),
            Tool(
                name=GitTools.MERGE,
                description="Merge a branch into the current branch",
                inputSchema=GitMerge.model_json_schema(),
            ),
            Tool(
                name=GitTools.REBASE,
                description="Reapply commits on top of another base branch",
                inputSchema=GitRebase.model_json_schema(),
            ),
            Tool(
                name=GitTools.PUSH,
                description="Push commits to a remote repository",
                inputSchema=GitPush.model_json_schema(),
            ),
            Tool(
                name=GitTools.PULL,
                description="Pull commits from a remote repository",
                inputSchema=GitPull.model_json_schema(),
            ),
            Tool(
                name=GitTools.STASH,
                description="Manage stashed changes (save, pop, list, apply, drop, clear)",
                inputSchema=GitStash.model_json_schema(),
            ),
            Tool(
                name=GitTools.TAG,
                description="Manage tags (create, list, delete)",
                inputSchema=GitTag.model_json_schema(),
            ),
            Tool(
                name=GitTools.QUICK_FIX,
                description="Quick add, commit, and optionally push changes",
                inputSchema=GitQuickFix.model_json_schema(),
            ),
            Tool(
                name=GitTools.SYNC,
                description="Sync with remote: pull, rebase/merge, and push",
                inputSchema=GitSync.model_json_schema(),
            ),
            Tool(
                name=GitTools.UNDO,
                description="Undo last operation (commit, merge, or rebase)",
                inputSchema=GitUndo.model_json_schema(),
            ),
            Tool(
                name=GitTools.BLAME,
                description="Show who last modified each line of a file",
                inputSchema=GitBlame.model_json_schema(),
            ),
            Tool(
                name=GitTools.STATS,
                description="Show repository statistics and contributor info",
                inputSchema=GitStats.model_json_schema(),
            ),
            Tool(
                name=GitTools.REMOTE_INFO,
                description="Show remote repository information and URLs",
                inputSchema=GitRemoteInfo.model_json_schema(),
            ),
            Tool(
                name=GitTools.CLONE,
                description="Clone a repository from URL",
                inputSchema=GitClone.model_json_schema(),
            ),
            Tool(
                name=GitTools.FETCH_ALL,
                description="Fetch all remote branches with optional pruning",
                inputSchema=GitFetchAll.model_json_schema(),
            ),
            Tool(
                name=GitTools.TRACK_REMOTE,
                description="Set local branch to track remote branch",
                inputSchema=GitTrackRemote.model_json_schema(),
            ),
            Tool(
                name=GitTools.DELETE_REMOTE_BRANCH,
                description="Delete a branch from remote repository",
                inputSchema=GitDeleteRemoteBranch.model_json_schema(),
            ),
            Tool(
                name=GitTools.SHOW_REMOTE_FILE,
                description="Show file content from remote branch",
                inputSchema=GitShowRemoteFile.model_json_schema(),
            ),
            Tool(
                name=GitTools.LS_REMOTE,
                description="List files in remote branch",
                inputSchema=GitLsRemote.model_json_schema(),
            ),
            Tool(
                name=GitTools.DIFF_REMOTE,
                description="Compare local with remote branch",
                inputSchema=GitDiffRemote.model_json_schema(),
            ),
            Tool(
                name=GitTools.GREP,
                description="Search for pattern in repository files",
                inputSchema=GitGrep.model_json_schema(),
            ),
            Tool(
                name=GitTools.LOG_SEARCH,
                description="Search for pattern in commit messages",
                inputSchema=GitLogSearch.model_json_schema(),
            )
        ]

    async def list_repos() -> Sequence[str]:
        async def by_roots() -> Sequence[str]:
            if not isinstance(server.request_context.session, ServerSession):
                raise TypeError("server.request_context.session must be a ServerSession")

            if not server.request_context.session.check_client_capability(
                ClientCapabilities(roots=RootsCapability())
            ):
                return []

            roots_result: ListRootsResult = await server.request_context.session.list_roots()
            logger.debug(f"Roots result: {roots_result}")
            repo_paths = []
            for root in roots_result.roots:
                path = root.uri.path
                try:
                    git.Repo(path)
                    repo_paths.append(str(path))
                except git.InvalidGitRepositoryError:
                    pass
            return repo_paths

        def by_commandline() -> Sequence[str]:
            return [str(repository)] if repository is not None else []

        cmd_repos = by_commandline()
        root_repos = await by_roots()
        return [*root_repos, *cmd_repos]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        # Handle git clone separately since it doesn't require an existing repo
        if name == GitTools.CLONE:
            result = await asyncio.to_thread(
                git_clone,
                arguments["url"],
                arguments.get("target_path", None),
                arguments.get("branch", None)
            )
            return [TextContent(
                type="text",
                text=result
            )]
        
        repo_path = Path(arguments["repo_path"])
        
        # Handle git init separately since it doesn't require an existing repo
        if name == GitTools.INIT:
            result = await asyncio.to_thread(git_init, str(repo_path))
            return [TextContent(
                type="text",
                text=result
            )]
            
        # For all other commands, we need an existing repo
        try:
            repo = git.Repo(repo_path)
        except git.InvalidGitRepositoryError:
            return [TextContent(
                type="text",
                text=f"Error: '{repo_path}' is not a valid Git repository. Please check the path or initialize a new repository with 'git_init'."
            )]
        except git.NoSuchPathError:
            return [TextContent(
                type="text",
                text=f"Error: Path '{repo_path}' does not exist. Please check the path and try again."
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"Error accessing repository: {type(e).__name__}: {str(e)}"
            )]

        match name:
            case GitTools.STATUS:
                status = await asyncio.to_thread(git_status, repo)
                return [TextContent(
                    type="text",
                    text=f"Repository status:\n{status}"
                )]

            case GitTools.DIFF_UNSTAGED:
                diff = await asyncio.to_thread(git_diff_unstaged, repo, arguments.get("context_lines", DEFAULT_CONTEXT_LINES))
                return [TextContent(
                    type="text",
                    text=f"Unstaged changes:\n{diff}"
                )]

            case GitTools.DIFF_STAGED:
                diff = await asyncio.to_thread(git_diff_staged, repo, arguments.get("context_lines", DEFAULT_CONTEXT_LINES))
                return [TextContent(
                    type="text",
                    text=f"Staged changes:\n{diff}"
                )]

            case GitTools.DIFF:
                diff = await asyncio.to_thread(git_diff, repo, arguments["target"], arguments.get("context_lines", DEFAULT_CONTEXT_LINES))
                return [TextContent(
                    type="text",
                    text=f"Diff with {arguments['target']}:\n{diff}"
                )]

            case GitTools.COMMIT:
                result = await asyncio.to_thread(git_commit, repo, arguments["message"])
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.ADD:
                result = await asyncio.to_thread(git_add, repo, arguments["files"])
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.RESET:
                result = await asyncio.to_thread(git_reset, repo)
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.LOG:
                log = await asyncio.to_thread(git_log, repo, arguments.get("max_count", 10))
                return [TextContent(
                    type="text",
                    text="Commit history:\n" + "\n".join(log)
                )]

            case GitTools.CREATE_BRANCH:
                result = await asyncio.to_thread(
                    git_create_branch,
                    repo,
                    arguments["branch_name"],
                    arguments.get("base_branch")
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.CHECKOUT:
                result = await asyncio.to_thread(git_checkout, repo, arguments["branch_name"])
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.SHOW:
                result = await asyncio.to_thread(git_show, repo, arguments["revision"])
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.BRANCH:
                result = await asyncio.to_thread(
                    git_branch,
                    repo,
                    arguments.get("branch_type", 'local'),
                    arguments.get("contains", None),
                    arguments.get("not_contains", None),
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.CHERRY_PICK:
                result = await asyncio.to_thread(
                    git_cherry_pick,
                    repo,
                    arguments["commit_sha"],
                    arguments.get("no_commit", False)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.RESET_MODE:
                result = await asyncio.to_thread(
                    git_reset_mode,
                    repo,
                    arguments["mode"],
                    arguments.get("commit", "HEAD")
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.MERGE:
                result = await asyncio.to_thread(
                    git_merge,
                    repo,
                    arguments["branch_name"],
                    arguments.get("no_ff", False)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.REBASE:
                result = await asyncio.to_thread(
                    git_rebase,
                    repo,
                    arguments["branch_name"],
                    arguments.get("interactive", False)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.PUSH:
                result = await asyncio.to_thread(
                    git_push,
                    repo,
                    arguments.get("remote", "origin"),
                    arguments.get("branch", None),
                    arguments.get("force", False)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.PULL:
                result = await asyncio.to_thread(
                    git_pull,
                    repo,
                    arguments.get("remote", "origin"),
                    arguments.get("branch", None)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.STASH:
                result = await asyncio.to_thread(
                    git_stash,
                    repo,
                    arguments["action"],
                    arguments.get("message", None),
                    arguments.get("index", None)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.TAG:
                result = await asyncio.to_thread(
                    git_tag,
                    repo,
                    arguments["action"],
                    arguments.get("tag_name", None),
                    arguments.get("message", None),
                    arguments.get("commit", "HEAD")
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.QUICK_FIX:
                result = await asyncio.to_thread(
                    git_quick_fix,
                    repo,
                    arguments["files"],
                    arguments["message"],
                    arguments.get("push", True),
                    arguments.get("remote", "origin")
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.SYNC:
                result = await asyncio.to_thread(
                    git_sync,
                    repo,
                    arguments.get("remote", "origin"),
                    arguments.get("branch", None),
                    arguments.get("rebase", True)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.UNDO:
                result = await asyncio.to_thread(
                    git_undo,
                    repo,
                    arguments["operation"]
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.BLAME:
                result = await asyncio.to_thread(
                    git_blame,
                    repo,
                    arguments["file_path"],
                    arguments.get("line_range", None)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.STATS:
                result = await asyncio.to_thread(
                    git_stats,
                    repo,
                    arguments.get("since", None),
                    arguments.get("author", None)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.REMOTE_INFO:
                result = await asyncio.to_thread(
                    git_remote_info,
                    repo,
                    arguments.get("remote", "origin")
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.FETCH_ALL:
                result = await asyncio.to_thread(
                    git_fetch_all,
                    repo,
                    arguments.get("prune", True)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.TRACK_REMOTE:
                result = await asyncio.to_thread(
                    git_track_remote,
                    repo,
                    arguments["branch_name"],
                    arguments["remote_branch"]
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.DELETE_REMOTE_BRANCH:
                result = await asyncio.to_thread(
                    git_delete_remote_branch,
                    repo,
                    arguments["branch_name"],
                    arguments.get("remote", "origin")
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.SHOW_REMOTE_FILE:
                result = await asyncio.to_thread(
                    git_show_remote_file,
                    repo,
                    arguments["file_path"],
                    arguments.get("ref", "origin/main")
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.LS_REMOTE:
                result = await asyncio.to_thread(
                    git_ls_remote,
                    repo,
                    arguments.get("ref", "origin/main"),
                    arguments.get("path", None)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.DIFF_REMOTE:
                result = await asyncio.to_thread(
                    git_diff_remote,
                    repo,
                    arguments.get("remote_ref", "origin/main"),
                    arguments.get("local_ref", "HEAD")
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.GREP:
                result = await asyncio.to_thread(
                    git_grep,
                    repo,
                    arguments["pattern"],
                    arguments.get("path", None),
                    arguments.get("case_sensitive", True)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case GitTools.LOG_SEARCH:
                result = await asyncio.to_thread(
                    git_log_search,
                    repo,
                    arguments["pattern"],
                    arguments.get("max_count", 20)
                )
                return [TextContent(
                    type="text",
                    text=result
                )]

            case _:
                raise ValueError(f"Unknown tool: {name}")

    options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, options, raise_exceptions=True)
