from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas import UserCreate
from ..fio_client import FIOClient, FIOAuthError, build_production_map

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Show the login/registration page."""
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "title": "Connect with FIO"},
    )


@router.post("/connect")
async def connect_fio(
    request: Request,
    fio_username: str = Form(...),
    fio_api_key: str = Form(...),
    db: Session = Depends(get_db),
):
    """
    Connect/verify a FIO account.
    Creates or updates the user in our database.
    """
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
    existing_user = db.query(User).filter(User.fio_username == fio_username).first()

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
