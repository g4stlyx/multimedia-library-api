from __future__ import annotations

import uuid

from pydantic import BaseModel


class FollowUserPublic(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str | None

    model_config = {"from_attributes": True}
