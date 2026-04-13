"""
GCP Secret Manager Client

Provides cached access to secrets stored in Google Cloud Secret Manager.
Uses LRU caching to avoid repeated API calls within the same container lifecycle.
"""

import logging
from functools import lru_cache

from google.cloud import secretmanager

logger = logging.getLogger(__name__)

# GCP Project ID — the single source of truth for all secret lookups
GCP_PROJECT_ID = "code-review-493116"


@lru_cache(maxsize=1)
def _get_client() -> secretmanager.SecretManagerServiceClient:
    """Lazily initialize and cache the Secret Manager client."""
    return secretmanager.SecretManagerServiceClient()


@lru_cache(maxsize=16)
def get_secret(secret_id: str, version: str = "latest") -> str:
    """
    Fetch a secret payload from GCP Secret Manager.

    Results are cached in-memory per (secret_id, version) pair for the
    lifetime of the container instance. This prevents redundant API calls
    when processing multiple webhooks on the same Cloud Run instance.

    Args:
        secret_id: The secret's ID in Secret Manager (e.g., "github-webhook-secret").
        version: The version to access. Defaults to "latest".

    Returns:
        The decoded secret payload as a UTF-8 string.

    Raises:
        google.api_core.exceptions.NotFound: If the secret or version doesn't exist.
        google.api_core.exceptions.PermissionDenied: If the service account lacks
            roles/secretmanager.secretAccessor.
    """
    client = _get_client()
    name = f"projects/{GCP_PROJECT_ID}/secrets/{secret_id}/versions/{version}"

    logger.info("Fetching secret: %s (version: %s)", secret_id, version)
    response = client.access_secret_version(request={"name": name})

    return response.payload.data.decode("utf-8")
