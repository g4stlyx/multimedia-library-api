from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import get_current_active_user
from app.core.rate_limit import rate_limit
from app.core.request_context import request_id_context
from app.database import get_db
from app.models.user import User
from app.schemas.upload import UploadPublic
from app.services.image_service import ImageValidationError
from app.services.upload_service import UploadService
from app.storage.r2 import CloudflareR2Storage, ObjectStorage, ObjectStorageError

router = APIRouter(prefix="/uploads", tags=["uploads"])


def get_object_storage(settings: Settings = Depends(get_settings)) -> ObjectStorage:
    return CloudflareR2Storage(settings)


async def _read_profile_image(upload: UploadFile, max_bytes: int) -> bytes:
    if upload.content_type and upload.content_type.lower() not in {"image/jpeg", "image/png", "image/webp"}:
        raise ImageValidationError("Only JPEG, PNG, and WebP images are allowed")
    content_length = upload.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > max_bytes:
        raise ImageValidationError("Image exceeds the maximum allowed size")
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ImageValidationError("Image exceeds the maximum allowed size")
    return content


@router.post(
    "/profile-image", response_model=UploadPublic, status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("uploads:profile-image", limit=10, window_seconds=3600))],
)
async def upload_profile_image(
    file: UploadFile = File(...), current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
    storage: ObjectStorage = Depends(get_object_storage),
) -> UploadPublic:
    try:
        content = await _read_profile_image(file, settings.profile_image_max_bytes)
        return UploadService(db, settings, storage).upload_profile_image(
            user=current_user, file_content=content, filename=file.filename, request_id=request_id_context.get(),
        )
    except ImageValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from None
    except ObjectStorageError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Image storage is unavailable") from None
    finally:
        await file.close()


@router.get("/{upload_id}/content")
def get_upload_content(
    upload_id: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings), storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    import uuid
    try:
        parsed_id = uuid.UUID(upload_id)
        _, content, content_type = UploadService(db, settings, storage).read_owned_upload(user=current_user, upload_id=parsed_id)
        return Response(content=content, media_type=content_type, headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"})
    except (ValueError, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found") from None
    except ObjectStorageError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Image storage is unavailable") from None


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_upload(
    upload_id: str, current_user: User = Depends(get_current_active_user), db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings), storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    import uuid
    try:
        UploadService(db, settings, storage).delete_owned_upload(user=current_user, upload_id=uuid.UUID(upload_id), request_id=request_id_context.get())
    except (ValueError, LookupError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found") from None
    except ObjectStorageError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Image storage is unavailable") from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
