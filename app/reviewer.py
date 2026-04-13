"""
Background Task Orchestrator (The Reviewer)

This is the core pipeline that runs asynchronously AFTER the webhook endpoint
has already returned HTTP 202 to GitHub. It coordinates the entire review flow:

    Authenticate → Gather Context → Filter Noise → Infer → Post Comments

All operations happen strictly in memory — no code is ever written to disk (P0).
All exceptions are caught and logged to prevent silent failures (P1).
"""

import logging

from github import GithubException

from app.github_auth import get_github_client
from app.context import assemble_context
from app.inference import execute_deep_analysis, execute_review

logger = logging.getLogger(__name__)


def process_pull_request(repo_name: str, pr_number: int, installation_id: int) -> None:
    """
    Process a Pull Request webhook payload end-to-end.

    This function is designed to run as a FastAPI BackgroundTask. It:
    1. Extracts PR metadata from the webhook payload.
    2. Authenticates as the GitHub App for the target installation.
    3. Fetches the PR diff and full file context (with noise filtering).
    4. Aborts early if the diff is empty after filtering (P0: no wasted inference).
    5. Sends the context to Vertex AI for structured code review.
    6. Posts each AI comment as an inline review comment on the PR.

    All errors are caught and logged — this function never raises, ensuring
    the background task doesn't crash silently.

    Args:
        repo_name: The full repository name (e.g., "org/repo")
        pr_number: The pull request number
        installation_id: The GitHub App installation ID
    """
    logger.info(
        "Processing PR #%d on %s [installation: %d]",
        pr_number,
        repo_name,
        installation_id,
    )

    # -----------------------------------------------------------------------
    # 2. Authenticate as the GitHub App
    # -----------------------------------------------------------------------
    try:
        github_client = get_github_client(installation_id)
        repo = github_client.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
    except Exception as exc:
        logger.error(
            "GitHub authentication/API failure for %s PR #%d: %s",
            repo_name,
            pr_number,
            exc,
        )
        return

    # -----------------------------------------------------------------------
    # 3. Assemble context (diff + full files, noise filtered)
    # -----------------------------------------------------------------------
    try:
        diff_text, full_files_context = assemble_context(repo, pr)
    except Exception as exc:
        logger.error(
            "Context assembly failed for %s PR #%d: %s",
            repo_name,
            pr_number,
            exc,
        )
        return

    # -----------------------------------------------------------------------
    # 4. Early exit if diff is empty after filtering (P0)
    # -----------------------------------------------------------------------
    if not diff_text.strip():
        logger.info(
            "PR #%d on %s has no reviewable changes after filtering. Skipping.",
            pr_number,
            repo_name,
        )
        return

    # -----------------------------------------------------------------------
    # 5. Execute Vertex AI inference
    # -----------------------------------------------------------------------
    try:
        comments = execute_review(repo_name, diff_text, full_files_context)
    except Exception as exc:
        logger.error(
            "Vertex AI inference failed for %s PR #%d: %s",
            repo_name,
            pr_number,
            exc,
        )
        return

    if not comments:
        logger.info(
            "AI found no issues in PR #%d on %s. No comments to post.",
            pr_number,
            repo_name,
        )
        return

    # -----------------------------------------------------------------------
    # 6. Post batched review to the PR (single API call)
    # -----------------------------------------------------------------------
    # CRITICAL: We batch ALL comments into a single pr.create_review() call
    # instead of firing individual create_review_comment() requests.
    # If a PR has 12 issues and we fire 12 rapid sequential requests,
    # GitHub's secondary abuse limits will temporarily shadowban the App.

    # Fetch the Commit OBJECT (not just the SHA string) — PyGithub requires this
    try:
        commit_obj = repo.get_commit(pr.head.sha)
    except Exception as exc:
        logger.error(
            "Failed to fetch commit object %s for %s PR #%d: %s",
            pr.head.sha,
            repo_name,
            pr_number,
            exc,
        )
        return

    # Build the comments array for the batched review
    review_comments = []
    for comment in comments:
        review_comments.append({
            "path": comment.path,
            "line": comment.line,
            "side": "RIGHT",  # We only review added lines (new file side)
            "body": comment.body,
        })

    try:
        pr.create_review(
            commit=commit_obj,
            body=(
                f"🤖 **AI Code Review** — {len(review_comments)} "
                f"issue{'s' if len(review_comments) != 1 else ''} found.\n\n"
                f"_Reviewed by Universal AI Reviewer (Gemini) · "
                f"Strictness: STRICT_"
            ),
            event="COMMENT",
            comments=review_comments,
        )
        logger.info(
            "Review complete for %s PR #%d: %d comments posted in single review",
            repo_name,
            pr_number,
            len(review_comments),
        )
    except GithubException as exc:
        logger.error(
            "Failed to post batched review for %s PR #%d: %s (status: %s, data: %s)",
            repo_name,
            pr_number,
            exc,
            getattr(exc, "status", "N/A"),
            getattr(exc, "data", "N/A"),
        )
    except Exception as exc:
        logger.error(
            "Unexpected error posting batched review for %s PR #%d: %s",
            repo_name,
            pr_number,
            exc,
        )

    # -----------------------------------------------------------------------
    # 7. Orchestrate Pass 2: Heavy Model (Deep Analysis)
    # -----------------------------------------------------------------------
    logger.info("Initiating Phase 2: Deep Analysis for %s PR #%d", repo_name, pr_number)
    
    # Serialize the first-pass comments
    flash_comments_data = [{"path": c.path, "line": c.line, "body": c.body} for c in comments]

    try:
        deep_comments = execute_deep_analysis(repo_name, diff_text, full_files_context, flash_comments_data)
    except Exception as exc:
        logger.error("Vertex AI Deep inference failed for %s PR #%d: %s", repo_name, pr_number, exc)
        return

    if not deep_comments:
        logger.info("AI Deep Analysis found no underlying root causes in PR #%d on %s.", pr_number, repo_name)
        return

    # Post Pass 2 Review
    deep_review_comments = []
    for comment in deep_comments:
        deep_review_comments.append({
            "path": comment.path,
            "line": comment.line,
            "side": "RIGHT",
            "body": f"🧠 **Deep Analysis (gemini-2.5-pro)**: \n\n{comment.body}",
        })

    try:
        pr.create_review(
            commit=commit_obj,
            body=(
                f"🧠 **Principal Architect Code Review** — {len(deep_review_comments)} "
                f"deep root-cause issue{'s' if len(deep_review_comments) != 1 else ''} found.\n\n"
                f"_Reviewed by Universal AI Reviewer (Gemini Pro) · Strictly Analyzing architecture_"
            ),
            event="COMMENT",
            comments=deep_review_comments,
        )
        logger.info(
            "Deep Review complete for %s PR #%d: %d deep comments posted",
            repo_name,
            pr_number,
            len(deep_review_comments),
        )
    except Exception as exc:
        logger.error("Failed to post Deep review for %s PR #%d: %s", repo_name, pr_number, exc)
