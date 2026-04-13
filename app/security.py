from __future__ import annotations
from typing import Optional

"""
Webhook Security Module

Validates GitHub webhook payloads using HMAC-SHA256 signature verification.
Uses hmac.compare_digest() to prevent timing attacks.
"""

import hashlib
import hmac

from fastapi import HTTPException


def verify_signature(
    payload_body: bytes,
    secret_token: str,
    signature_header: Optional[str],
) -> None:
    """
    Verify that a GitHub webhook payload was signed with the expected secret.

    Computes HMAC-SHA256 of the raw payload body using the webhook secret,
    then compares it against the signature provided in the x-hub-signature-256
    header using a constant-time comparison to prevent timing attacks.

    Args:
        payload_body: The raw bytes of the incoming request body.
        secret_token: The webhook secret from GCP Secret Manager.
        signature_header: The value of the x-hub-signature-256 header.

    Raises:
        HTTPException(401): If the signature is missing or doesn't match.
    """
    if not signature_header:
        raise HTTPException(
            status_code=401,
            detail="Missing x-hub-signature-256 header",
        )

    hash_object = hmac.new(
        secret_token.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256,
    )
    expected_signature = "sha256=" + hash_object.hexdigest()

    if not hmac.compare_digest(expected_signature, signature_header):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )
