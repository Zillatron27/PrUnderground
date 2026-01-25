import os
import logging
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..database import get_db
from ..models import User
from ..fio_client import FIOClient, FIOAuthError, FIOError
from ..audit import log_audit, AuditAction
from ..csrf import verify_csrf
from ..template_utils import render_template

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Session cookie configuration
SESSION_SECRET = os.getenv("SESSION_SECRET", os.getenv("SECRET_KEY", "dev-secret-change-me"))
SESSION_MAX_AGE = 30 * 24 * 60 * 60  # 30 days in seconds
session_serializer = URLSafeTimedSerializer(SESSION_SECRET, salt="session")


def sign_session(user_id: int) -> str:
    """Create a signed session token for a user."""
    return session_serializer.dumps({"user_id": user_id})


def verify_session(token: str) -> Optional[int]:
    """
    Verify a signed session token and return the user_id.
    Returns None if token is invalid or expired.
    """
    try:
        data = session_serializer.loads(token, max_age=SESSION_MAX_AGE)
        return data.get("user_id")
    except SignatureExpired:
        logger.debug("Session token expired")
        return None
    except BadSignature:
        logger.warning("Invalid session signature detected")
        return None
    except Exception as e:
        logger.warning(f"Session verification error: {e}")
        return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show the login page - just asks for username first."""
    return render_template(
        request,
        "auth/login.html",
        {"request": request, "title": "Login", "step": "username"},
    )


@router.post("/check-user")
@limiter.limit("10/minute")
async def check_user(
    request: Request,
    fio_username: str = Form(...),
    csrf_token: str = Form(None),
    db: Session = Depends(get_db),
):
    """
    Step 1: Check if user exists with a stored API key.
    If yes and key is valid → log them in.
    If no or key is invalid → prompt for API key.
    """
    await verify_csrf(request, csrf_token)
    fio_username = fio_username.strip()

    # Check if user exists in our database
    existing_user = db.query(User).filter(
        User.fio_username.ilike(fio_username)
    ).first()

    if existing_user and existing_user.fio_api_key:
        # Try to validate the stored API key
        client = FIOClient(api_key=existing_user.fio_api_key)
        try:
            await client.verify_api_key(existing_user.fio_username)
            # Key is still valid - update company info and log them in
            user_info = await client.get_user_info(existing_user.fio_username)
            if user_info:
                if user_info.get("CompanyCode"):
                    existing_user.company_code = user_info["CompanyCode"]
                if user_info.get("CompanyName"):
                    existing_user.company_name = user_info["CompanyName"]
                db.commit()

            # Audit log successful login
            log_audit(db, AuditAction.USER_LOGIN, user_id=existing_user.id)

            response = RedirectResponse(url="/dashboard", status_code=303)
            response.set_cookie(
                key="session",
                value=sign_session(existing_user.id),
                httponly=True,
                max_age=SESSION_MAX_AGE,
                samesite="lax",
            )
            return response
        except FIOAuthError:
            # Stored key is no longer valid - need a new one
            pass
        except Exception as e:
            # Network error, timeout, or other issue - prompt for new key
            logger.warning(f"FIO check failed for {fio_username}: {e}")
            pass
        finally:
            await client.close()

    # Either new user or stored key is invalid - prompt for API key
    return render_template(
        request,
        "auth/login.html",
        {
            "request": request,
            "title": "Connect with FIO",
            "step": "api_key",
            "fio_username": fio_username,
            "is_new_user": existing_user is None,
        },
    )


@router.post("/connect")
@limiter.limit("10/minute")
async def connect_fio(
    request: Request,
    fio_username: str = Form(...),
    fio_api_key: str = Form(...),
    csrf_token: str = Form(None),
    db: Session = Depends(get_db),
):
    """
    Step 2: Verify API key and create/update user.
    """
    await verify_csrf(request, csrf_token)
    fio_username = fio_username.strip()

    # Verify the API key with FIO
    client = FIOClient(api_key=fio_api_key)

    try:
        user_data = await client.verify_api_key(fio_username)
        # Fetch user info for company details
        user_info = await client.get_user_info(fio_username)
    except FIOAuthError as e:
        return render_template(
            request,
            "auth/login.html",
            {
                "request": request,
                "title": "Connect with FIO",
                "step": "api_key",
                "error": str(e),
                "fio_username": fio_username,
            },
            status_code=400,
        )
    except FIOError as e:
        return render_template(
            request,
            "auth/login.html",
            {
                "request": request,
                "title": "Connect with FIO",
                "step": "api_key",
                "error": f"FIO API error: {e}",
                "fio_username": fio_username,
            },
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Unexpected error connecting to FIO for {fio_username}: {e}")
        return render_template(
            request,
            "auth/login.html",
            {
                "request": request,
                "title": "Connect with FIO",
                "step": "api_key",
                "error": "Could not connect to FIO. Please check your API key and try again.",
                "fio_username": fio_username,
            },
            status_code=400,
        )
    finally:
        await client.close()

    # Extract company info from user data
    company_code = user_info.get("CompanyCode") if user_info else None
    company_name = user_info.get("CompanyName") if user_info else None

    # Check if user exists
    existing_user = db.query(User).filter(
        User.fio_username.ilike(fio_username)
    ).first()

    if existing_user:
        # Update existing user
        existing_user.fio_api_key = fio_api_key
        if company_code:
            existing_user.company_code = company_code
        if company_name:
            existing_user.company_name = company_name
        db.commit()
        user = existing_user
        log_audit(db, AuditAction.USER_LOGIN, user_id=user.id, details={"reconnected": True})
    else:
        # Create new user
        user = User(
            fio_username=fio_username,
            fio_api_key=fio_api_key,
            company_code=company_code,
            company_name=company_name,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        log_audit(db, AuditAction.USER_LOGIN, user_id=user.id, details={"new_user": True})

    # Store signed session token
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        key="session",
        value=sign_session(user.id),
        httponly=True,
        max_age=SESSION_MAX_AGE,
        samesite="lax",
    )
    return response


@router.get("/account", response_class=HTMLResponse)
async def account_page(
    request: Request,
    db: Session = Depends(get_db),
):
    """Show account settings and stored info."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Mask the API key for display (show first 8 and last 4 chars)
    masked_key = None
    if user.fio_api_key:
        key = user.fio_api_key
        if len(key) > 12:
            masked_key = f"{key[:8]}...{key[-4:]}"
        else:
            masked_key = "****"

    return render_template(
        request,
        "auth/account.html",
        {
            "request": request,
            "title": "Account Settings",
            "user": user,
            "current_user": user,
            "masked_key": masked_key,
        },
    )


@router.post("/refresh-key")
@limiter.limit("10/minute")
async def refresh_api_key(
    request: Request,
    fio_api_key: str = Form(...),
    csrf_token: str = Form(None),
    db: Session = Depends(get_db),
):
    """Update the stored API key."""
    await verify_csrf(request, csrf_token)
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    # Verify the new key works
    client = FIOClient(api_key=fio_api_key)
    try:
        await client.verify_api_key(user.fio_username)
        user_info = await client.get_user_info(user.fio_username)

        # Update user record
        user.fio_api_key = fio_api_key
        if user_info:
            if user_info.get("CompanyCode"):
                user.company_code = user_info["CompanyCode"]
            if user_info.get("CompanyName"):
                user.company_name = user_info["CompanyName"]
        db.commit()

        log_audit(db, AuditAction.API_KEY_UPDATED, user_id=user.id)

        return RedirectResponse(url="/auth/account?updated=1", status_code=303)
    except FIOAuthError as e:
        return render_template(
            request,
            "auth/account.html",
            {
                "request": request,
                "title": "Account Settings",
                "user": user,
                "current_user": user,
                "masked_key": f"{fio_api_key[:8]}..." if len(fio_api_key) > 8 else "****",
                "error": str(e),
            },
            status_code=400,
        )
    except Exception as e:
        logger.error(f"Unexpected error refreshing API key for {user.fio_username}: {e}")
        return render_template(
            request,
            "auth/account.html",
            {
                "request": request,
                "title": "Account Settings",
                "user": user,
                "current_user": user,
                "masked_key": f"{fio_api_key[:8]}..." if len(fio_api_key) > 8 else "****",
                "error": "Could not connect to FIO. Please try again.",
            },
            status_code=400,
        )
    finally:
        await client.close()


@router.get("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    """Log out the current user."""
    # Log the logout before clearing the session
    user = get_current_user(request, db)
    if user:
        log_audit(db, AuditAction.USER_LOGOUT, user_id=user.id)

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="session")
    # Also delete old cookie name for migration
    response.delete_cookie(key="user_id")
    return response


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Get the current logged-in user from the signed session cookie."""
    session_token = request.cookies.get("session")
    if not session_token:
        # Check for old unsigned cookie (migration support)
        old_user_id = request.cookies.get("user_id")
        if old_user_id:
            try:
                user_id = int(old_user_id)
                return db.query(User).filter(User.id == user_id).first()
            except (ValueError, TypeError):
                logger.warning(f"Malformed old user_id cookie: {old_user_id!r}")
                return None
        return None

    user_id = verify_session(session_token)
    if not user_id:
        return None

    try:
        return db.query(User).filter(User.id == user_id).first()
    except Exception as e:
        logger.error(f"Database error looking up user {user_id}: {e}")
        return None


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Require a logged-in user, redirect to login if not."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user
