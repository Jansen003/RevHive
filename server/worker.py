"""Async review processor for GitHub PR events.

Handles the full pipeline:
  JWT signing → installation token → fetch diff → run workflow → post comment
"""

import asyncio
import logging
import os
import time

import httpx
import jwt

from server.config_server import (
    GITHUB_API_BASE,
    GITHUB_APP_ID,
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_MODEL,
    get_private_key,
)

# Set LLM env vars once at import time so CodeReviewWorkflow picks them up
# without mutating os.environ on every request.
os.environ.setdefault("LLM_BASE_URL", LLM_BASE_URL)
os.environ.setdefault("LLM_MODEL", LLM_MODEL)
if LLM_API_KEY:
    os.environ.setdefault("LLM_API_KEY", LLM_API_KEY)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GitHub App authentication
# ---------------------------------------------------------------------------


def _build_jwt() -> str:
    """Build a short-lived JWT for GitHub App authentication (RS256)."""
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": GITHUB_APP_ID,
    }
    return jwt.encode(payload, get_private_key(), algorithm="RS256")


async def get_installation_token(installation_id: int) -> str:
    """Exchange a JWT for an installation access token."""
    app_jwt = _build_jwt()
    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {app_jwt}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------


async def get_pr_diff(token: str, repo: str, pr_number: int) -> str:
    """Fetch the unified diff for a pull request."""
    url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3.diff",
            },
        )
        resp.raise_for_status()
    return resp.text


async def post_pr_comment(token: str, repo: str, pr_number: int, body: str) -> None:
    """Post a review comment on a pull request."""
    url = f"{GITHUB_API_BASE}/repos/{repo}/issues/{pr_number}/comments"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
            },
            json={"body": body},
        )
        resp.raise_for_status()


# ---------------------------------------------------------------------------
# Review pipeline
# ---------------------------------------------------------------------------


async def review_and_comment(
    token: str, repo: str, pr_number: int, diff: str
) -> None:
    """Run the revhive workflow on a diff and post the result as a PR comment."""
    logger.info("Input to workflow (first 200 chars): %s", diff[:200])

    from revhive.graph.workflow import CodeReviewWorkflow, ReviewReport

    workflow = CodeReviewWorkflow(model=LLM_MODEL)
    result = await workflow.run(code=diff, file_path=f"PR#{pr_number}")

    logger.info(
        "workflow.run() returned: type=%s, summary=%s, result(first 500)=%s",
        type(result).__name__, result.summary, str(result)[:500],
    )
    logger.info("Findings count: %d", len(result.findings))

    markdown = ReviewReport(result).to_markdown()

    await post_pr_comment(token, repo, pr_number, markdown)
    logger.info(
        "Posted review comment on %s#%d — %d findings, summary: %s",
        repo, pr_number, len(result.findings), result.summary,
    )


# ---------------------------------------------------------------------------
# Top-level event handler
# ---------------------------------------------------------------------------


async def process_pr_event(payload: dict, event_id: str = "") -> None:
    """Process a GitHub pull_request webhook event.

    Extracts the installation ID, repo name, and PR number, then runs
    the full review pipeline. Retries up to 3 times with exponential
    backoff (1s, 4s, 9s). Errors are logged with the delivery ID.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            installation_id = payload["installation"]["id"]
            pr_number = payload["pull_request"]["number"]
            repo = payload["repository"]["full_name"]

            logger.info(
                "Processing PR %s#%d (installation %d, attempt %d/%d, event=%s)",
                repo, pr_number, installation_id, attempt + 1, max_retries, event_id,
            )

            token = await get_installation_token(installation_id)
            diff = await get_pr_diff(token, repo, pr_number)
            await review_and_comment(token, repo, pr_number, diff)
            return

        except Exception:
            delay = (attempt + 1) ** 2
            if attempt < max_retries - 1:
                logger.warning(
                    "Attempt %d/%d failed for event %s, retrying in %ds",
                    attempt + 1, max_retries, event_id, delay,
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "All %d attempts failed for event %s",
                    max_retries, event_id,
                    exc_info=True,
                )
