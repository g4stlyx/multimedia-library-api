from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.upload import UploadStatus


class UploadPublic(BaseModel):
    id: uuid.UUID
    upload_type: str
    content_type: str
    byte_size: int
    width: int
    height: int
    status: UploadStatus
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
