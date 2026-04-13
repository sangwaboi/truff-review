from __future__ import annotations

"""
Vertex AI Inference Engine

Executes structured code review inference using the Google Gen AI SDK
(google-genai). Enforces a strict JSON schema on the model output to
guarantee parseable review comments.

Uses Application Default Credentials (ADC) via the Cloud Run service account.
No hardcoded API keys.
"""

import json
import logging

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.prompt_config import build_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GCP Configuration
# ---------------------------------------------------------------------------
GCP_PROJECT_ID = "code-review-493116"
GCP_LOCATION = "us-central1"
MODEL_ID = "gemini-3.1-pro"


# ---------------------------------------------------------------------------
# Output Schema (Pydantic model for type-safe structured output)
# ---------------------------------------------------------------------------
class ReviewComment(BaseModel):
    """A single inline code review comment from the AI."""

    path: str = Field(description="The relative file path in the repository")
    line: int = Field(description="The line number in the new version of the file")
    body: str = Field(description="A concise, actionable code review comment")


# ---------------------------------------------------------------------------
# Inference Execution
# ---------------------------------------------------------------------------
def execute_review(
    repo_name: str,
    diff: str,
    context: str,
) -> list[ReviewComment]:
    """
    Send the PR context to Vertex AI and receive structured review comments.

    Builds the prompt using the modular prompt configuration, sends it to
    Gemini with strict JSON schema enforcement, and parses the response
    into a list of ReviewComment objects.

    Args:
        repo_name: The full repository name (e.g., "org/repo").
        diff: The filtered diff text from the PR.
        context: The full file contents for surrounding context.

    Returns:
        A list of ReviewComment objects. May be empty if the AI finds no issues.

    Raises:
        google.api_core.exceptions.ResourceExhausted: If the Vertex AI rate
            limit is hit.
        google.api_core.exceptions.DeadlineExceeded: If the inference times out.
        json.JSONDecodeError: If the model output is not valid JSON despite
            schema enforcement.
    """
    # Initialize the Gen AI client with Vertex AI backend
    client = genai.Client(
        vertexai=True,
        project=GCP_PROJECT_ID,
        location=GCP_LOCATION,
    )

    # Assemble the full prompt
    prompt = build_prompt(repo_name, diff, context)

    logger.info(
        "Sending inference request to %s for repo: %s", MODEL_ID, repo_name
    )

    # Execute inference with strict JSON schema enforcement
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=list[ReviewComment],
            temperature=0.2,  # Low temperature for deterministic, precise reviews
        ),
    )

    # Parse the structured response
    raw_output = response.text
    logger.debug("Raw inference output: %s", raw_output[:500])

    parsed = json.loads(raw_output)

    # Validate each item against the Pydantic model
    comments = [ReviewComment(**item) for item in parsed]

    logger.info(
        "Inference complete for %s: %d comments generated",
        repo_name,
        len(comments),
    )

    return comments
