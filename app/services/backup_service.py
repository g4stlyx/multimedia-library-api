from __future__ import annotations

import base64
import gzip
import hashlib
import logging
import os
import subprocess
import urllib.parse
from datetime import datetime, timezone
import uuid

from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.repositories.backup_repository import BackupRepository
from app.storage.r2 import CloudflareR2Storage
from app.services.email_service import EmailService
from app.models.backup import BackupMetadata

logger = logging.getLogger(__name__)


class BackupService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.repo = BackupRepository(db)
        self.emails = EmailService(settings)

    def _get_fernet(self) -> Fernet:
        """Derive a secure 32-byte Fernet key from settings by hashing."""
        raw_key = self.settings.backup_encryption_key or self.settings.jwt_secret_key
        # Hash raw key to get 32 bytes, then base64 urlsafe encode
        key_hash = hashlib.sha256(raw_key.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(key_hash)
        return Fernet(fernet_key)

    def run_backup(self, *, backup_id: uuid.UUID, worker_id: str) -> BackupMetadata:
        """Run database backup: dump, compress, encrypt, upload, and email status."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_record = self.repo.get_by_id(backup_id)
        if backup_record is None:
            raise LookupError("Backup record was not found")
        if backup_record.status != "processing" or backup_record.worker_id != worker_id:
            return backup_record

        # Workspace relative backup path
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        backup_dir = os.path.join(base_dir, "tmp_backup")
        os.makedirs(backup_dir, exist_ok=True)

        temp_sql = os.path.join(backup_dir, f"backup_{timestamp}.sql")
        temp_gz = temp_sql + ".gz"
        temp_enc = temp_gz + ".enc"

        db_url = str(self.settings.database_url)
        parsed = urllib.parse.urlparse(db_url)
        db_user = parsed.username or "g4stly"
        db_name = parsed.path.lstrip("/") or "multimedia_app"
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432

        r2_key = f"backups/backup_{timestamp}.sql.gz.enc"

        try:
            # 1. Run database dump (pg_dump)
            dump_success = False
            
            # A. Try host pg_dump
            try:
                clean_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
                subprocess.run(
                    ["pg_dump", "--dbname", clean_url, "-f", temp_sql],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                dump_success = True
                logger.info("Database dump successful using host pg_dump")
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                logger.warning("Host pg_dump failed or not found, falling back to Docker exec: %s", e)

            # B. Try Docker exec pg_dump fallback
            if not dump_success:
                try:
                    with open(temp_sql, "wb") as f_out:
                        subprocess.run(
                            ["docker", "exec", "-i", "multimedia-postgres", "pg_dump", "-U", db_user, db_name],
                            stdout=f_out,
                            check=True,
                        )
                    dump_success = True
                    logger.info("Database dump successful using Docker exec pg_dump")
                except Exception as docker_exc:
                    raise RuntimeError(f"Database dump failed on both host and Docker. Docker error: {docker_exc}")

            if not os.path.exists(temp_sql) or os.path.getsize(temp_sql) == 0:
                raise RuntimeError("Generated SQL dump file is empty or does not exist")

            # 2. Compress using gzip
            with open(temp_sql, "rb") as f_in:
                with gzip.open(temp_gz, "wb") as f_out:
                    # chunk copy
                    while chunk := f_in.read(65536):
                        f_out.write(chunk)

            # 3. Encrypt compressed backup
            with open(temp_gz, "rb") as f_gz:
                compressed_bytes = f_gz.read()

            fernet = self._get_fernet()
            encrypted_bytes = fernet.encrypt(compressed_bytes)

            with open(temp_enc, "wb") as f_enc:
                f_enc.write(encrypted_bytes)

            size_bytes = len(encrypted_bytes)
            sha256 = hashlib.sha256(encrypted_bytes).hexdigest()

            # 4. Upload to Cloudflare R2
            r2 = CloudflareR2Storage(self.settings)
            r2.client.put_object(
                Bucket=r2.bucket,
                Key=r2_key,
                Body=encrypted_bytes,
                ContentType="application/octet-stream",
            )
            logger.info("Encrypted database backup uploaded to R2: %s", r2_key)

            # 5. Update DB Record
            self.repo.update_backup_success(
                backup=backup_record,
                size_bytes=size_bytes,
                sha256=sha256,
                storage_key=r2_key,
            )
            self.db.commit()

            # 6. Email Status Notification
            recipient = self.settings.backup_email_recipient or self.settings.mail_from_email
            if recipient:
                self.emails.send_backup_notification(
                    to_email=recipient,
                    status="success",
                    filename=os.path.basename(temp_enc),
                    size_bytes=size_bytes,
                    sha256=sha256,
                    storage_key=r2_key,
                )

        except Exception as err:
            logger.exception("Database backup failed")
            # Update DB metadata record to failed
            self.db.rollback()
            self.repo.update_backup_failed(backup=backup_record, error_message=str(err))
            self.db.commit()

            # Email Failure Notification
            recipient = self.settings.backup_email_recipient or self.settings.mail_from_email
            if recipient:
                try:
                    self.emails.send_backup_notification(
                        to_email=recipient,
                        status="failed",
                        error_message=str(err),
                    )
                except Exception as email_err:
                    logger.error("Failed to send backup failure email notification: %s", email_err)
            
            raise
        
        finally:
            # Delete local backup temp files
            for path in [temp_sql, temp_gz, temp_enc]:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                    except OSError as e:
                        logger.error("Failed to delete temp backup file %s: %s", path, e)

        return backup_record

    def restore_backup(self, *, encrypted_bytes: bytes) -> bytes:
        """Decrypt and decompress database backup bytes."""
        fernet = self._get_fernet()
        decrypted = fernet.decrypt(encrypted_bytes)
        decompressed = gzip.decompress(decrypted)
        return decompressed

    def run_restore(self, *, sql_content: bytes) -> None:
        """Execute restore SQL script against database."""
        db_url = str(self.settings.database_url)
        parsed = urllib.parse.urlparse(db_url)
        db_user = parsed.username or "g4stly"
        db_name = parsed.path.lstrip("/") or "multimedia_app"
        db_password = parsed.password
        db_host = parsed.hostname or "localhost"
        db_port = parsed.port or 5432

        restore_success = False

        # A. Try host psql
        try:
            clean_url = db_url.replace("postgresql+psycopg2://", "postgresql://")
            subprocess.run(
                ["psql", "--dbname", clean_url],
                input=sql_content,
                check=True,
            )
            restore_success = True
            logger.info("Database restored successfully using host psql")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning("Host psql failed or not found, falling back to Docker exec: %s", e)

        # B. Try Docker exec psql fallback
        if not restore_success:
            try:
                subprocess.run(
                    ["docker", "exec", "-i", "multimedia-postgres", "psql", "-U", db_user, db_name],
                    input=sql_content,
                    check=True,
                )
                restore_success = True
                logger.info("Database restored successfully using Docker exec psql")
            except Exception as docker_exc:
                raise RuntimeError(f"Database restore failed on both host and Docker. Docker error: {docker_exc}")
