from __future__ import annotations

"""
Context Assembly & Signal-to-Noise Filter

Parses the PR's changed files, filters out dependency trees and static assets
to protect Vertex AI compute budgets, and assembles the diff + full file
context for the inference engine.
"""

import logging

from github import Repository, PullRequest

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Noise Filter Configuration
# ---------------------------------------------------------------------------

# File extensions to always skip (dependency locks, static assets, binaries)
SKIP_EXTENSIONS: set[str] = {
    ".lock",
    ".csv",
    ".svg",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".map",
    ".min.js",
    ".min.css",
}

# Exact filenames to always skip (common lock files)
SKIP_FILENAMES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Pipfile.lock",
    "poetry.lock",
    "Cargo.lock",
    "go.sum",
    "composer.lock",
    "Gemfile.lock",
    "bun.lockb",
}

# Directory prefixes to always skip (build outputs, vendored deps)
SKIP_DIRECTORIES: tuple[str, ...] = (
    "dist/",
    "build/",
    "node_modules/",
    ".next/",
    "vendor/",
    "__pycache__/",
    ".nuxt/",
    "target/",
    "out/",
    ".output/",
)


def _should_skip_file(filename: str) -> bool:
    """
    Determine if a file should be excluded from AI review.

    Checks against known noisy file types: dependency locks, static assets,
    build outputs, and auto-generated directories.

    Args:
        filename: The relative path of the file in the repository.

    Returns:
        True if the file should be skipped, False otherwise.
    """
    # Check exact filename matches (e.g., "package-lock.json")
    basename = filename.rsplit("/", 1)[-1] if "/" in filename else filename
    if basename in SKIP_FILENAMES:
        return True

    # Check file extensions
    for ext in SKIP_EXTENSIONS:
        if filename.endswith(ext):
            return True

    # Check directory prefixes
    for dir_prefix in SKIP_DIRECTORIES:
        if dir_prefix in filename:
            return True

    return False


def assemble_context(
    repo: Repository.Repository,
    pr: PullRequest.PullRequest,
) -> tuple[str, str]:
    """
    Extract filtered diffs and full file context from a Pull Request.

    Iterates through all changed files in the PR, applies the noise filter,
    and builds two text blocks:
    1. `diff_text`: The unified diff patches for reviewable files.
    2. `full_files_context`: The complete file contents at the PR's HEAD SHA
       for providing surrounding context to the AI.

    Files that were deleted or are binary are gracefully skipped for full
    content fetching (their diffs are still included if available).

    Args:
        repo: The PyGithub Repository object.
        pr: The PyGithub PullRequest object.

    Returns:
        A tuple of (diff_text, full_files_context). Both may be empty strings
        if all changed files are filtered out.
    """
    diff_text = ""
    full_files_context = ""
    commit_sha = pr.head.sha

    files = pr.get_files()
    reviewed_count = 0
    skipped_count = 0

    for file in files:
        # Apply the noise filter
        if _should_skip_file(file.filename):
            skipped_count += 1
            logger.debug("Skipping noisy file: %s", file.filename)
            continue

        reviewed_count += 1

        # Append diff patch (may be None for binary files or renames)
        if file.patch:
            diff_text += f"\n--- {file.filename} ---\n{file.patch}\n"

        # Fetch full file content for surrounding context
        try:
            content = repo.get_contents(file.filename, ref=commit_sha)
            if content and not isinstance(content, list):
                decoded = content.decoded_content.decode("utf-8")
                full_files_context += (
                    f"\n--- FULL FILE: {file.filename} ---\n{decoded}\n"
                )
        except Exception as exc:
            # File was deleted, is binary, or is too large — skip gracefully
            logger.debug(
                "Could not fetch content for %s: %s", file.filename, exc
            )

    logger.info(
        "Context assembly complete: %d files reviewed, %d skipped",
        reviewed_count,
        skipped_count,
    )

    return diff_text, full_files_context
