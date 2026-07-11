from __future__ import annotations

from app.core.config import get_settings
from app.database import SessionLocal
from app.models.media import MediaType
from app.models.seed import SeedRun
from app.services.seed_service import SeedService


async def run_seed_page(*, provider: str, media_type: MediaType, seed_kind: str, cursor: str | None = None, limit: int = 20) -> SeedRun:
    """Queue-compatible worker function. Calls are idempotent per provider/type/kind/cursor."""
    db = SessionLocal()
    try:
        return await SeedService(db, get_settings()).process_page(
            provider=provider, media_type=media_type, seed_kind=seed_kind, cursor=cursor, limit=limit,
        )
    finally:
        db.close()
