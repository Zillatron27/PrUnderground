from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import User
from ..schemas import UserCreate
from ..fio_client import FIOClient, FIOAuthError, build_production_map

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show the login page - just asks for username first."""
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "title": "Login", "step": "username"},
    )


@router.post("/check-user")
async def check_user(
    request: Request,
    fio_username: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Step 1: Check if user exists with a stored API key.
    If yes and key is valid → log them in.
    If no or key is invalid → prompt for API key.
    """
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

            response = RedirectResponse(url="/dashboard", status_code=303)
            response.set_cookie(key="user_id", value=str(existing_user.id), httponly=True)
            return response
        except FIOAuthError:
            # Stored key is no longer valid - need a new one
            pass
        finally:
            await client.close()

    # Either new user or stored key is invalid - prompt for API key
    return templates.TemplateResponse(
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
async def connect_fio(
    request: Request,
    fio_username: str = Form(...),
    fio_api_key: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Step 2: Verify API key and create/update user.
    """
    fio_username = fio_username.strip()

    # Verify the API key with FIO
    client = FIOClient(api_key=fio_api_key)

    try:
        user_data = await client.verify_api_key(fio_username)
        # Fetch user info for company details
        user_info = await client.get_user_info(fio_username)
    except FIOAuthError as e:
        return templates.TemplateResponse(
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

    # Store user ID in session (simple cookie for now)
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(key="user_id", value=str(user.id), httponly=True)
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

    return templates.TemplateResponse(
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
async def refresh_api_key(
    request: Request,
    fio_api_key: str = Form(...),
    db: Session = Depends(get_db),
):
    """Update the stored API key."""
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

        return RedirectResponse(url="/auth/account?updated=1", status_code=303)
    except FIOAuthError as e:
        return templates.TemplateResponse(
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
    finally:
        await client.close()


@router.get("/logout")
async def logout():
    """Log out the current user."""
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(key="user_id")
    return response


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Get the current logged-in user from the session cookie."""
    user_id = request.cookies.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Require a logged-in user, redirect to login if not."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/auth/login"})
    return user
