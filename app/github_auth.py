"""
GitHub App Authentication Engine

Implements the two-step authentication flow for GitHub Apps:
1. Generate a short-lived RS256 JWT signed with the App's private key.
2. Exchange the JWT for an Installation Access Token scoped to a specific repo/org.
"""

import logging
import time

import jwt
import requests
from github import Github

from app.secrets import get_secret

logger = logging.getLogger(__name__)

# GitHub API base URL
GITHUB_API_BASE = "https://api.github.com"


def generate_jwt() -> str:
    """
    Generate a JSON Web Token (JWT) for authenticating as the GitHub App.

    The JWT is signed using RS256 with the App's private key fetched from
    GCP Secret Manager. It has a maximum lifetime of 10 minutes and accounts
    for clock drift by backdating the `iat` claim by 60 seconds.

    Returns:
        The encoded JWT string.
    """
    app_id = get_secret("github-app-id")
    private_key = get_secret("github-private-key")

    now = int(time.time())
    payload = {
        # Issued at time — backdated 60s for clock drift tolerance
        "iat": now - 60,
        # Expiration — GitHub enforces a 10-minute maximum
        "exp": now + (10 * 60),
        # Issuer — the GitHub App ID
        "iss": app_id,
    }

    token = jwt.encode(payload, private_key, algorithm="RS256")
    logger.info("Generated JWT for GitHub App ID: %s", app_id)
    return token


def get_installation_token(installation_id: int) -> str:
    """
    Exchange a JWT for a short-lived Installation Access Token.

    POSTs to GitHub's installation token endpoint using the JWT as a Bearer
    token. The returned token is scoped to the specific installation (repo/org)
    and is valid for 1 hour.

    Args:
        installation_id: The GitHub App installation ID from the webhook payload.

    Returns:
        The installation access token string.

    Raises:
        requests.HTTPError: If the token exchange fails (e.g., invalid JWT,
            expired key, or incorrect installation ID).
    """
    jwt_token = generate_jwt()

    url = f"{GITHUB_API_BASE}/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    response = requests.post(url, headers=headers, timeout=10)
    response.raise_for_status()

    token = response.json()["token"]
    logger.info(
        "Obtained installation token for installation ID: %d", installation_id
    )
    return token


def get_github_client(installation_id: int) -> Github:
    """
    Create an authenticated PyGithub client for a specific installation.

    Convenience wrapper that generates an Installation Access Token and
    returns a fully authenticated Github instance ready for API calls.

    Args:
        installation_id: The GitHub App installation ID from the webhook payload.

    Returns:
        An authenticated PyGithub Github instance.
    """
    token = get_installation_token(installation_id)
    return Github(token)
