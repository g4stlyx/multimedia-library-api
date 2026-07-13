from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import get_current_active_user
from app.core.rate_limit import rate_limit
from app.database import get_db
from app.models.import_job import ImportSource
from app.models.media import MediaType
from app.models.user import User
from app.repositories.import_repository import ImportRepository
from app.schemas.import_job import ImportConflictResolution, ImportJobPublic
from app.services.import_parser import ImportParseError
from app.services.import_service import ImportService
from app.workers.import_worker import run_import_job_in_session

router = APIRouter(prefix="/imports", tags=["imports"])


async def _read_csv(upload: UploadFile, max_bytes: int) -> bytes:
    if upload.content_type and upload.content_type.lower() not in {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain"}:
        raise ImportParseError("Only CSV files are accepted")
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ImportParseError("CSV file exceeds the maximum allowed size")
    return content


@router.post("", response_model=ImportJobPublic, status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit("imports:create", limit=10, window_seconds=3600))])
async def create_import(
    background_tasks: BackgroundTasks, file: UploadFile = File(...), source: ImportSource = Form(...),
    generic_media_type: MediaType | None = Form(None), current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> ImportJobPublic:
    try:
        content = await _read_csv(file, settings.import_max_file_bytes)
        job, created = ImportService(db, settings).create_csv_job(
            user_id=current_user.id, source=source, filename=file.filename, content=content, default_media_type=generic_media_type,
        )
        if created:
            background_tasks.add_task(run_import_job_in_session, db, str(job.id), settings)
        return job
    except ImportParseError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from None
    except RuntimeError as error:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(error)) from None
    finally:
        await file.close()


@router.get("", response_model=list[ImportJobPublic])
def list_imports(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100), current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
) -> list[ImportJobPublic]:
    return ImportRepository(db).list_owned(user_id=current_user.id, limit=limit, offset=(page - 1) * limit)


@router.get("/{import_job_id}", response_model=ImportJobPublic)
def get_import(import_job_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db)) -> ImportJobPublic:
    job = ImportRepository(db).get_job_owned(job_id=import_job_id, user_id=current_user.id, include_items=True)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return job


@router.post("/{import_job_id}/cancel", response_model=ImportJobPublic)
def cancel_import(import_job_id: uuid.UUID, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> ImportJobPublic:
    try:
        return ImportService(db, settings).cancel_job(user_id=current_user.id, job_id=import_job_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from None


@router.post("/{import_job_id}/items/{item_id}/resolve", response_model=ImportJobPublic)
def resolve_import_conflict(
    import_job_id: uuid.UUID, item_id: uuid.UUID, body: ImportConflictResolution,
    current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
) -> ImportJobPublic:
    try:
        return ImportService(db, settings).resolve_item(
            user_id=current_user.id, job_id=import_job_id, item_id=item_id, action=body.action,
            matched_media_id=body.matched_media_id, status=body.status, rating_value=body.rating_value,
        )
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from None
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from None
