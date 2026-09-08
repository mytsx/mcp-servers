#!/usr/bin/env python3
"""
Gemini PR Reviews MCP Server
Fetch Gemini Code Assist reviews from GitHub PRs
"""

import logging
import os
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, Literal

import httpx2
from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from . import __version__

load_dotenv()

logger = logging.getLogger(__name__)

GEMINI_BOT = "gemini-code-assist[bot]"
GITHUB_API = "https://api.github.com"

# Used when the user has never posted a "/gemini review" comment on the PR:
# far enough back that everything Gemini has said is included.
NO_REVIEW_REQUEST_CUTOFF = "2025-08-01T00:00:00Z"


def _resolve_github_token() -> str:
    """Resolve GitHub token: gh CLI first, then GITHUB_TOKEN env var."""
    try:
        result = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            logger.info("GitHub token resolved via gh CLI")
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        logger.info("GitHub token resolved via GITHUB_TOKEN env var")
    else:
        logger.warning("No GitHub token found — gh CLI not available and GITHUB_TOKEN not set")
    return token


# ---------------------------------------------------------------------------
# Wire models
# ---------------------------------------------------------------------------

CommentKind = Literal["review", "line_comment", "issue_comment"]

# Reviews sort before line comments, which sort before issue comments.
_KIND_ORDER: dict[CommentKind, int] = {"review": 0, "line_comment": 1, "issue_comment": 2}


class GeminiComment(BaseModel):
    """One thing Gemini Code Assist said on the PR."""

    type: CommentKind = Field(
        description="review: the verdict on the whole PR. line_comment: a comment on one "
        "line of the diff. issue_comment: a comment on the PR conversation."
    )
    date: str = Field(description="ISO-8601 timestamp of when it was posted.")
    body: str
    html_url: str = Field(description="Link to the comment on GitHub.")
    state: str | None = Field(
        default=None, description="For a review: APPROVED, CHANGES_REQUESTED, COMMENTED."
    )
    file: str | None = Field(default=None, description="For a line comment: the file it is on.")
    line: int | None = Field(default=None, description="For a line comment: the line number.")


class ReviewCounts(BaseModel):
    reviews: int
    line_comments: int
    issue_comments: int


class GeminiReviews(BaseModel):
    """Everything Gemini said on one PR, within the requested window."""

    repo: str = Field(description="Resolved owner/repo.")
    pr: int
    after_date: str | None = Field(
        default=None,
        description="Only comments at or after this timestamp are included. "
        "Null when the whole PR history was returned.",
    )
    counts: ReviewCounts
    comments: list[GeminiComment] = Field(
        description="Reviews first, then line comments, then issue comments; each group oldest first."
    )


# ---------------------------------------------------------------------------
# GitHub access
# ---------------------------------------------------------------------------


class GitHub:
    """The slice of the GitHub API this server needs."""

    def __init__(self, client: httpx2.AsyncClient, token: str) -> None:
        self.client = client
        self.token = token

    async def _paginate(self, path: str) -> list[dict[str, Any]]:
        """Read every page of a GitHub list endpoint.

        Any non-200 fails the call. Stopping early and returning what was
        collected so far would hand back a partial history as if it were
        complete, and a missing finding reads exactly like no finding.
        """
        items: list[dict[str, Any]] = []
        page = 1
        while True:
            try:
                resp = await self.client.get(
                    f"{GITHUB_API}{path}", params={"page": page, "per_page": 100}
                )
            except httpx2.HTTPError as exc:
                raise ToolError(f"GitHub {path} isteği başarısız: {exc}") from exc

            if resp.status_code != 200:
                logger.warning("GitHub %s → HTTP %s (sayfa %s)", path, resp.status_code, page)
                raise ToolError(_github_error(path, resp.status_code, page))

            batch = resp.json()
            if not batch:
                return items
            items.extend(batch)
            page += 1

    async def authenticated_user(self) -> str | None:
        try:
            resp = await self.client.get(f"{GITHUB_API}/user")
            if resp.status_code == 200:
                return resp.json()["login"]
        except httpx2.HTTPError as exc:
            logger.warning("Kimlik doğrulanmış kullanıcı alınamadı: %s", exc)
        return None

    async def last_pr(self, repo: str) -> int | None:
        try:
            resp = await self.client.get(
                f"{GITHUB_API}/repos/{repo}/pulls",
                params={"state": "all", "sort": "created", "direction": "desc", "per_page": 1},
            )
            if resp.status_code == 200 and resp.json():
                return resp.json()[0]["number"]
        except httpx2.HTTPError as exc:
            logger.warning("Son PR bulunamadı: %s", exc)
        return None

    async def last_review_request(self, repo: str, pr: int, username: str) -> str:
        """Timestamp of the user's most recent '/gemini review' comment on the PR."""
        comments = await self._paginate(f"/repos/{repo}/issues/{pr}/comments")
        dates = [
            c["created_at"]
            for c in comments
            if c.get("user", {}).get("login") == username
            and "/gemini review" in c.get("body", "").lower()
        ]
        if not dates:
            logger.info("'/gemini review' yorumu yok, varsayılan tarih kullanılıyor")
            return NO_REVIEW_REQUEST_CUTOFF
        latest = max(dates)
        logger.info("Son '/gemini review' yorumu: %s", latest)
        return latest

    async def reviews(self, repo: str, pr: int) -> list[dict]:
        return await self._paginate(f"/repos/{repo}/pulls/{pr}/reviews")

    async def line_comments(self, repo: str, pr: int) -> list[dict]:
        return await self._paginate(f"/repos/{repo}/pulls/{pr}/comments")

    async def issue_comments(self, repo: str, pr: int) -> list[dict]:
        return await self._paginate(f"/repos/{repo}/issues/{pr}/comments")


def _github_error(path: str, status: int, page: int) -> str:
    """A message that says what to do about this particular status."""
    hint = {
        401: "Token geçersiz ya da süresi dolmuş.",
        403: "Token'ın bu depoya erişimi yok ya da rate limit aşıldı.",
        404: "Depo ya da PR bulunamadı; adı ve numarayı kontrol et.",
    }.get(status, "GitHub bu isteği reddetti.")
    where = f" (sayfa {page})" if page > 1 else ""
    return f"GitHub {path} isteği HTTP {status} döndü{where}. {hint}"


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_gemini(item: dict) -> bool:
    return item.get("user", {}).get("login") == GEMINI_BOT


ProgressCallback = Callable[[int, int, str], Awaitable[None]]


async def _noop_progress(done: int, total: int, message: str) -> None:
    return None


async def collect_comments(
    gh: GitHub,
    repo: str,
    pr: int,
    after_date: str | None,
    progress: ProgressCallback = _noop_progress,
) -> list[GeminiComment]:
    """Every Gemini comment on the PR, optionally only those at or after `after_date`."""
    cutoff = _parse_ts(after_date) if after_date else None
    collected: list[GeminiComment] = []

    def keep(timestamp: str | None) -> bool:
        if not timestamp:
            return False
        return cutoff is None or _parse_ts(timestamp) >= cutoff

    await progress(0, 3, "İncelemeler alınıyor")
    for review in await gh.reviews(repo, pr):
        if not _is_gemini(review):
            continue
        submitted = review.get("submitted_at")
        if not keep(submitted):
            continue
        collected.append(
            GeminiComment(
                type="review",
                date=submitted,
                state=review.get("state"),
                body=review.get("body") or "",
                html_url=review.get("html_url", ""),
            )
        )

    await progress(1, 3, "Satır yorumları alınıyor")
    for comment in await gh.line_comments(repo, pr):
        if not _is_gemini(comment) or not keep(comment.get("created_at")):
            continue
        collected.append(
            GeminiComment(
                type="line_comment",
                date=comment["created_at"],
                file=comment.get("path"),
                line=comment.get("line"),
                body=comment.get("body") or "",
                html_url=comment.get("html_url", ""),
            )
        )

    await progress(2, 3, "PR yorumları alınıyor")
    for comment in await gh.issue_comments(repo, pr):
        if not _is_gemini(comment) or not keep(comment.get("created_at")):
            continue
        collected.append(
            GeminiComment(
                type="issue_comment",
                date=comment["created_at"],
                body=comment.get("body") or "",
                html_url=comment.get("html_url", ""),
            )
        )

    await progress(3, 3, f"{len(collected)} yorum bulundu")
    collected.sort(key=lambda c: (_KIND_ORDER[c.type], c.date))
    return collected


def _counts(comments: list[GeminiComment]) -> ReviewCounts:
    return ReviewCounts(
        reviews=sum(1 for c in comments if c.type == "review"),
        line_comments=sum(1 for c in comments if c.type == "line_comment"),
        issue_comments=sum(1 for c in comments if c.type == "issue_comment"),
    )


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------


@dataclass
class AppContext:
    gh: GitHub


# Resources cannot read the lifespan context in v2, so they go through this.
_app: AppContext | None = None


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[AppContext]:
    global _app
    token = _resolve_github_token()
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    async with httpx2.AsyncClient(timeout=30, headers=headers) as client:
        _app = AppContext(gh=GitHub(client, token))
        try:
            yield _app
        finally:
            _app = None


mcp = MCPServer("gemini-reviews-mcp", version=__version__, lifespan=app_lifespan)


async def _resolve_target(gh: GitHub, repo: str, pr: int | None) -> tuple[str, int]:
    """Fill in the repo owner and the PR number when the caller left them out."""
    if not gh.token:
        raise ToolError(
            "GitHub token bulunamadı. `gh auth login` çalıştır ya da GITHUB_TOKEN ayarla."
        )

    if "/" not in repo:
        owner = await gh.authenticated_user()
        if not owner:
            raise ToolError(
                "Depo sahibi belirlenemedi. Tam yolu ver: owner/repo."
            )
        repo = f"{owner}/{repo}"
        logger.info("Depo sahibi otomatik bulundu: %s", owner)

    if pr is None:
        found = await gh.last_pr(repo)
        if not found:
            raise ToolError(f"{repo} deposunda PR bulunamadı. `pr` parametresini ver.")
        pr = found
        logger.info("Son PR: #%s", pr)

    return repo, pr


@mcp.tool(
    title="Gemini incelemelerini getir",
    description="Get Gemini Code Assist reviews from a GitHub PR. Can fetch all reviews or "
    "only those after your last '/gemini review' comment.",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def get_gemini_reviews(
    repo: Annotated[
        str,
        Field(
            description="Repository as 'owner/repo', or just the name to use the authenticated "
            "user as owner (e.g. 'YtbMp3Indir' or 'owner/YtbMp3Indir')."
        ),
    ],
    ctx: Context[AppContext],
    pr: Annotated[
        int | None,
        Field(ge=1, description="PR number. Omitted means the most recently created PR."),
    ] = None,
    after_last_review: Annotated[
        bool,
        Field(
            description="Only return comments posted after your most recent '/gemini review' "
            "comment. False returns the whole PR history."
        ),
    ] = True,
    username: Annotated[
        str,
        Field(
            description="GitHub username whose '/gemini review' comment marks the cutoff. "
            "Empty means the authenticated user. Only used when after_last_review is true."
        ),
    ] = "",
) -> GeminiReviews:
    gh = ctx.request_context.lifespan_context.gh
    repo, pr = await _resolve_target(gh, repo, pr)

    after_date: str | None = None
    if after_last_review:
        who = username or await gh.authenticated_user()
        if not who:
            raise ToolError(
                "GitHub kullanıcısı belirlenemedi. `username` parametresini ver ya da "
                "after_last_review=false kullan."
            )
        after_date = await gh.last_review_request(repo, pr, who)

    async def report(done: int, total: int, message: str) -> None:
        await ctx.report_progress(done, total, message)

    comments = await collect_comments(gh, repo, pr, after_date, progress=report)

    return GeminiReviews(
        repo=repo, pr=pr, after_date=after_date, counts=_counts(comments), comments=comments
    )


@mcp.resource(
    "review://{owner}/{repo}/{pr}",
    name="PR Gemini incelemesi",
    description="Bir GitHub PR'ındaki tüm Gemini Code Assist yorumları, JSON olarak.",
    mime_type="application/json",
)
async def review_resource(owner: str, repo: str, pr: str) -> str:
    if _app is None:
        raise ResourceError("Sunucu henüz hazır değil.")
    try:
        pr_number = int(pr)
    except ValueError as exc:
        raise ResourceError(f"PR numarası sayı olmalı, '{pr}' verildi.") from exc

    full_repo = f"{owner}/{repo}"
    comments = await collect_comments(_app.gh, full_repo, pr_number, after_date=None)
    return GeminiReviews(
        repo=full_repo,
        pr=pr_number,
        after_date=None,
        counts=_counts(comments),
        comments=comments,
    ).model_dump_json(indent=2)


@mcp.prompt(title="Gemini incelemesini ele al")
def address_review(repo: str, pr: str = "") -> str:
    """Read Gemini's review of a PR and work through its findings."""
    target = f"{repo} PR #{pr}" if pr else f"{repo} deposundaki son PR"
    return (
        f"{target} için Gemini Code Assist incelemesini `get_gemini_reviews` ile al ve ele al:\n\n"
        "1. Her bulguyu oku; satır yorumlarını ilgili dosya ve satırla eşleştir.\n"
        "2. Bulguları ciddiyetine göre sırala: gerçek hata > güvenlik > bakım kolaylığı > stil.\n"
        "3. Her biri için ya düzelt ya da neden düzeltmediğini tek cümleyle gerekçelendir.\n"
        "4. Yanlış olduğunu düşündüğün bulgular varsa ayrıca listele — körlemesine uygulama.\n"
        "5. Sonunda ne değiştiğini özetle."
    )


if __name__ == "__main__":
    mcp.run()
