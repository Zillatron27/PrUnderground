"""
Data import/export endpoints.
"""

import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..csrf import verify_csrf
from ..services.json_io import (
    export_backup,
    import_json,
    get_export_filename,
    ImportMode,
)
from .auth import require_user

router = APIRouter(prefix="/data", tags=["data"])


# --- Export Endpoints ---


@router.get("/export/backup")
async def export_backup_endpoint(
    request: Request,
    db: Session = Depends(get_db),
):
    """Export full user backup (profile + listings) as JSON file."""
    user = require_user(request, db)

    data = export_backup(user)
    filename = get_export_filename("prunderground-backup", user.fio_username)

    return Response(
        content=json.dumps(data, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Import Endpoints ---


@router.post("/import")
async def import_data_endpoint(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("merge_update"),
    csrf_token: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """
    Import data from JSON file.

    Mode options:
    - replace: Delete all existing listings, import new ones
    - merge_add: Only add listings for materials not already listed
    - merge_update: Update existing listings + add new ones
    """
    await verify_csrf(request, csrf_token)
    user = require_user(request, db)

    # Validate mode
    try:
        import_mode = ImportMode(mode)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {mode}")

    # Read and parse file
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Perform import
    result = import_json(data, user, db, import_mode)

    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return JSONResponse(content=result.to_dict())
