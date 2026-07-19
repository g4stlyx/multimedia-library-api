from __future__ import annotations

import argparse
import logging
import socket
import time
import uuid

from app.core.config import get_settings
from app.database import SessionLocal
from app.repositories.backup_repository import BackupRepository
from app.services.backup_service import BackupService

logger = logging.getLogger(__name__)


def _worker_id() -> str:
    return f"{socket.gethostname()}-{uuid.uuid4()}"


def run_backup_worker(*, once: bool = False) -> None:
    """Poll persisted backup jobs; deploy this separately from the API process."""
    settings = get_settings()
    worker_id = _worker_id()
    logger.info("backup_worker_started", extra={"worker_id": worker_id})

    while True:
        db = SessionLocal()
        claimed_backup_id: uuid.UUID | None = None
        try:
            backup = BackupRepository(db).claim_next_backup(
                worker_id=worker_id,
                lease_seconds=settings.backup_worker_lease_seconds,
            )
            if backup is not None:
                claimed_backup_id = backup.id
                db.commit()
                BackupService(db, settings).run_backup(
                    backup_id=backup.id,
                    worker_id=worker_id,
                )
            else:
                db.rollback()
        except Exception:
            db.rollback()
            logger.exception("backup_worker_iteration_failed", extra={"worker_id": worker_id})
        finally:
            db.close()

        if once:
            return
        if claimed_backup_id is None:
            time.sleep(settings.backup_worker_poll_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the durable multimedia backup worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued backup and exit")
    args = parser.parse_args()
    run_backup_worker(once=args.once)
