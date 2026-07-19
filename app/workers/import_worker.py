from __future__ import annotations

import argparse
import asyncio
import logging
import socket
import time
import uuid

from app.core.config import get_settings
from app.database import SessionLocal
from app.repositories.import_repository import ImportRepository
from app.services.import_service import ImportService

logger = logging.getLogger(__name__)


def _worker_id() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4()}"


def run_import_job(import_job_id: str, *, worker_id: str | None = None) -> bool:
    """Claim and process one durable import job in a dedicated worker session."""
    try:
        job_id = uuid.UUID(import_job_id)
    except ValueError:
        logger.warning("invalid_import_job_id", extra={"import_job_id": import_job_id})
        return False

    settings = get_settings()
    claimed_by = worker_id or _worker_id()
    db = SessionLocal()
    try:
        service = ImportService(db, settings)
        asyncio.run(service.process_job(job_id, worker_id=claimed_by))
        return True
    finally:
        db.close()


def run_import_worker(*, once: bool = False) -> None:
    """Poll the database for queued imports; run this in a dedicated worker process."""
    settings = get_settings()
    worker_id = _worker_id()
    logger.info("import_worker_started", extra={"worker_id": worker_id})

    while True:
        db = SessionLocal()
        claimed_job_id: uuid.UUID | None = None
        try:
            job = ImportRepository(db).claim_next_job(
                worker_id=worker_id,
                lease_seconds=settings.import_worker_lease_seconds,
            )
            if job is not None:
                claimed_job_id = job.id
                db.commit()
                asyncio.run(ImportService(db, settings).process_claimed_job(job.id, worker_id=worker_id))
            else:
                db.rollback()
        except Exception:
            db.rollback()
            logger.exception("import_worker_iteration_failed", extra={"worker_id": worker_id})
        finally:
            db.close()

        if once:
            return
        if claimed_job_id is None:
            time.sleep(settings.import_worker_poll_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the durable multimedia import worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job and exit")
    args = parser.parse_args()
    run_import_worker(once=args.once)
