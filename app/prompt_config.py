from __future__ import annotations

"""
Modular Prompt Configuration

Provides configurable prompt templates and strictness levels for the Vertex AI
inference engine. The team can adjust review behavior by modifying this file
without touching any core application logic (P2 requirement).
"""

from enum import Enum


class ReviewStrictness(str, Enum):
    """
    Controls how aggressive the AI reviewer is with its feedback.

    - STRICT: Flags everything — style, performance, logic, security.
    - MODERATE: Focuses on correctness, performance, and security. Ignores style.
    - LENIENT: Only flags clear bugs, security vulnerabilities, and critical perf issues.
    """

    STRICT = "strict"
    MODERATE = "moderate"
    LENIENT = "lenient"


# ---------------------------------------------------------------------------
# Active Configuration — Change this to adjust review behavior
# ---------------------------------------------------------------------------
ACTIVE_STRICTNESS = ReviewStrictness.MODERATE

# ---------------------------------------------------------------------------
# System Prompts by Strictness Level
# ---------------------------------------------------------------------------
_STRICTNESS_INSTRUCTIONS: dict[ReviewStrictness, str] = {
    ReviewStrictness.STRICT: (
        "Be thorough and flag ALL issues including: code style violations, "
        "naming conventions, missing error handling, performance concerns, "
        "security vulnerabilities, logic errors, and architectural anti-patterns. "
        "Prefer over-flagging to missing a potential issue."
    ),
    ReviewStrictness.MODERATE: (
        "Focus on correctness, performance bottlenecks, security vulnerabilities, "
        "and logic errors. Ignore minor style issues unless they significantly "
        "impact readability. Do NOT comment on trivial formatting or naming "
        "preferences."
    ),
    ReviewStrictness.LENIENT: (
        "Only flag clear bugs, security vulnerabilities, and critical performance "
        "issues that would cause production incidents. Ignore style, naming, "
        "minor inefficiencies, and subjective preferences. If you are not highly "
        "confident that something is a real issue, do NOT comment on it."
    ),
}

# ---------------------------------------------------------------------------
# Base System Prompt — The AI Reviewer's Identity & Context
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_TEMPLATE = """You are an expert lead developer and code reviewer for Ozumax, a high-performance crowdsourced logistics platform.

ARCHITECTURAL CONTEXT:
- The backend uses PostgreSQL as the primary datastore with complex relational queries for order management, driver matching, and route optimization.
- Redis is used as a speed layer for real-time state management: driver locations, order status caching, rate limiting, and session management.
- The system must handle high-throughput scenarios with thousands of concurrent orders and drivers.

YOUR REVIEW PRIORITIES:
1. **N+1 Queries**: Identify any database access pattern where a query is executed inside a loop. Flag missing JOINs, missing prefetch/select_related, or iterative API calls that should be batched.
2. **Inefficient Data Structures**: Flag O(n²) algorithms, unnecessary copies, missing indexes, or data transformations that could be optimized.
3. **Redis Anti-Patterns**: Watch for race conditions in Redis operations, missing TTLs on cached keys, unbounded cache growth, and improper use of Redis data types.
4. **Logic Errors**: Catch off-by-one errors, incorrect boolean logic, unhandled edge cases, and incorrect error handling.
5. **Security**: Flag SQL injection vectors, missing input validation, hardcoded secrets, and unsafe deserialization.

STRICTNESS LEVEL: {strictness}
{strictness_instructions}

RULES:
- ONLY comment on lines that were ADDED (lines starting with '+' in the diff). Never comment on removed or unchanged lines.
- Each comment must reference the exact file path and line number in the new code.
- Keep comments concise and actionable. Explain WHY something is a problem and suggest a fix.
- If the code looks good and you find no issues, return an empty JSON array [].
- Do NOT generate placeholder or generic comments. Every comment must be specific and substantive."""


def build_prompt(repo_name: str, diff: str, context: str) -> str:
    """
    Assemble the complete inference prompt with context injection.

    Combines the system prompt (grounded in Ozumax's architecture), the full
    file context, and the PR diff into a single prompt string.

    Args:
        repo_name: The full repository name (e.g., "org/repo").
        diff: The filtered diff text (only reviewable files).
        context: The full file contents of modified files.

    Returns:
        The assembled prompt string ready for Vertex AI.
    """
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        strictness=ACTIVE_STRICTNESS.value.upper(),
        strictness_instructions=_STRICTNESS_INSTRUCTIONS[ACTIVE_STRICTNESS],
    )

    return f"""{system_prompt}

---

REPOSITORY: {repo_name}

FULL CONTEXT OF MODIFIED FILES (for understanding surrounding code):
{context}

THE PULL REQUEST DIFF (Focus your review ONLY on added lines marked with '+'):
{diff}

Analyze the diff and return your review as a JSON array. Each element must have exactly three fields: "path" (string — the file path), "line" (integer — the line number in the new file), and "body" (string — your review comment). If no issues are found, return an empty array []."""
