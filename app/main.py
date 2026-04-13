from __future__ import annotations
from typing import Optional

"""
Universal AI Code Reviewer — FastAPI Application

The main entry point for the webhook receiver. Exposes:
- POST /webhook  — GitHub webhook ingress with HMAC validation & background processing
- GET  /health   — Cloud Run health check endpoint

Architecture:
    GitHub Webhook → HMAC Verify → Event Filter → BackgroundTask → HTTP 202
                                                        ↓
                                              (async) reviewer.process_pull_request()
"""

import logging

from fastapi import FastAPI, Request, Header, BackgroundTasks
from fastapi.responses import JSONResponse

from app.security import verify_signature
from app.secrets import get_secret
from app.reviewer import process_pull_request

# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Universal AI Code Reviewer",
    description=(
        "A stateless, event-driven microservice that reviews Pull Requests "
        "using Vertex AI (Gemini) and posts inline comments back to GitHub."
    ),
    version="1.0.0",
)

# Accepted PR actions that trigger a review
REVIEWABLE_ACTIONS = {"opened", "synchronize"}


# ---------------------------------------------------------------------------
# Health Check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """
    Health check endpoint for Cloud Run.

    Returns a simple 200 OK response. Cloud Run uses this to determine
    whether the container is ready to receive traffic.
    """
    return {"status": "healthy", "service": "universal-ai-reviewer"}


# ---------------------------------------------------------------------------
# Webhook Endpoint
# ---------------------------------------------------------------------------
@app.post("/webhook", status_code=202)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    """
    Receive and process GitHub webhook events.

    Flow:
    1. Read the raw payload body.
    2. Fetch the webhook secret from GCP Secret Manager.
    3. Validate the HMAC-SHA256 signature (timing-attack safe).
    4. Filter: only process `pull_request` events with action `opened` or `synchronize`.
    5. Offload the heavy processing to a BackgroundTask.
    6. Return HTTP 202 Accepted immediately (satisfies GitHub's 10s timeout).

    Args:
        request: The incoming FastAPI request.
        background_tasks: FastAPI's BackgroundTasks queue.
        x_hub_signature_256: The HMAC-SHA256 signature header from GitHub.
        x_github_event: The event type header from GitHub.

    Returns:
        HTTP 202 with a status message.
    """
    # 1. Read raw payload for signature verification
    payload_body = await request.body()

    # 2. Fetch webhook secret from GCP Secret Manager
    try:
        webhook_secret = get_secret("github-webhook-secret")
    except Exception as exc:
        logger.error("Failed to fetch webhook secret: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal configuration error"},
        )

    # 3. Validate HMAC-SHA256 signature
    verify_signature(payload_body, webhook_secret, x_hub_signature_256)

    # 4. Parse the JSON payload
    payload = await request.json()

    # 5. Event routing — only process PR open/sync events
    action = payload.get("action", "")

    if x_github_event == "pull_request" and action in REVIEWABLE_ACTIONS:
        logger.info(
            "Accepted PR event: action=%s, repo=%s, PR=#%s",
            action,
            payload.get("repository", {}).get("full_name", "unknown"),
            payload.get("pull_request", {}).get("number", "?"),
        )
        # 6. Offload to background task — this is the timeout bypass
        background_tasks.add_task(process_pull_request, payload)

        return {
            "message": "Accepted",
            "status": "processing in background",
            "event": x_github_event,
            "action": action,
        }

    # Non-reviewable event — acknowledge but don't process
    logger.debug(
        "Ignoring event: %s (action: %s)", x_github_event, action
    )
    return {
        "message": "Acknowledged",
        "status": "event ignored",
        "event": x_github_event,
        "action": action,
    }
