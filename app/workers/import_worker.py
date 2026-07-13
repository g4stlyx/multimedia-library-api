from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database import SessionLocal
from app.services.import_service import ImportService

logger = logging.getLogger(__name__)


async def run_import_job_in_session(db: Session, import_job_id: str, settings=None) -> None:
    """In-process async dispatcher for local deployments and the API fallback path."""
    try:
        job_id = uuid.UUID(import_job_id)
    except ValueError:
        logger.warning("invalid_import_job_id", extra={"import_job_id": import_job_id})
        return
    await ImportService(db, settings or get_settings()).process_job(job_id)


def run_import_job(import_job_id: str) -> None:
    """DB-backed import worker entry point; replace this dispatcher with a queue consumer in production."""
    try:
        job_id = uuid.UUID(import_job_id)
    except ValueError:
        logger.warning("invalid_import_job_id", extra={"import_job_id": import_job_id})
        return
    db = SessionLocal()
    try:
        asyncio.run(ImportService(db, get_settings()).process_job(job_id))
    finally:
        db.close()
