"""
CSRF Protection

Provides CSRF token generation and validation for form submissions.
"""

import os
import logging
import secrets
from typing import Optional
from fastapi import Request, HTTPException
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

logger = logging.getLogger(__name__)

# CSRF configuration
CSRF_SECRET = os.getenv("CSRF_SECRET", os.getenv("SECRET_KEY", "dev-csrf-secret-change-me"))
CSRF_TOKEN_MAX_AGE = 2 * 60 * 60  # 2 hours in seconds
CSRF_COOKIE_NAME = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"

csrf_serializer = URLSafeTimedSerializer(CSRF_SECRET, salt="csrf")


def generate_csrf_token() -> str:
    """Generate a new CSRF token."""
    # Include a random component for uniqueness
    data = {"nonce": secrets.token_hex(16)}
    return csrf_serializer.dumps(data)


def validate_csrf_token(token: str) -> bool:
    """
    Validate a CSRF token.
    Returns True if valid, False otherwise.
    """
    if not token:
        return False
    try:
        csrf_serializer.loads(token, max_age=CSRF_TOKEN_MAX_AGE)
        return True
    except SignatureExpired:
        logger.debug("CSRF token expired")
        return False
    except BadSignature:
        logger.warning("Invalid CSRF token signature")
        return False
    except Exception as e:
        logger.warning(f"CSRF validation error: {e}")
        return False


def get_csrf_token(request: Request) -> str:
    """
    Get or generate a CSRF token for the request.
    Stores the token in a cookie for subsequent validation.
    """
    # Check if we already have a valid token in cookies
    existing_token = request.cookies.get(CSRF_COOKIE_NAME)
    if existing_token and validate_csrf_token(existing_token):
        return existing_token

    # Generate a new token
    return generate_csrf_token()


def set_csrf_cookie(response, token: str):
    """Set the CSRF token cookie on a response."""
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=CSRF_TOKEN_MAX_AGE,
    )


async def verify_csrf(request: Request, form_token: Optional[str] = None) -> bool:
    """
    Verify CSRF token from form submission against cookie.

    Args:
        request: The FastAPI request
        form_token: The token from the form (if already extracted)

    Returns:
        True if valid, raises HTTPException if invalid
    """
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)

    if not cookie_token:
        logger.warning("CSRF cookie missing")
        raise HTTPException(status_code=403, detail="CSRF validation failed - please refresh and try again")

    if not form_token:
        # Try to get from form data
        form_data = await request.form()
        form_token = form_data.get(CSRF_FORM_FIELD)

    if not form_token:
        logger.warning("CSRF form token missing")
        raise HTTPException(status_code=403, detail="CSRF validation failed - please refresh and try again")

    # Validate both tokens are valid signed tokens
    if not validate_csrf_token(cookie_token):
        logger.warning("CSRF cookie token invalid")
        raise HTTPException(status_code=403, detail="CSRF validation failed - please refresh and try again")

    if not validate_csrf_token(form_token):
        logger.warning("CSRF form token invalid")
        raise HTTPException(status_code=403, detail="CSRF validation failed - please refresh and try again")

    # Tokens should match
    if cookie_token != form_token:
        logger.warning("CSRF token mismatch")
        raise HTTPException(status_code=403, detail="CSRF validation failed - please refresh and try again")

    return True
