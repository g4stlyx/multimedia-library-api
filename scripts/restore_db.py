"""Restore the database from an encrypted database backup file.

Example: python -m scripts.restore_db --file tmp_backup/backup_xxx.sql.gz.enc
"""
from __future__ import annotations

import argparse
import os
import sys

from app.core.config import get_settings
from app.database import SessionLocal
from app.services.backup_service import BackupService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Restore database from encrypted backup")
    parser.add_argument("--file", help="Path to the encrypted backup file (.sql.gz.enc)", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    file_path = args.file

    if not os.path.exists(file_path):
        print(f"Error: Backup file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading encrypted backup file from {file_path}...")
    with open(file_path, "rb") as f:
        encrypted_bytes = f.read()

    settings = get_settings()
    db = SessionLocal()
    try:
        service = BackupService(db, settings)
        print("Decrypting and decompressing backup data...")
        try:
            sql_content = service.restore_backup(encrypted_bytes=encrypted_bytes)
        except Exception as decrypt_err:
            print(f"Error: Failed to decrypt backup. Ensure your BACKUP_ENCRYPTION_KEY or JWT_SECRET_KEY is correct. Details: {decrypt_err}", file=sys.stderr)
            sys.exit(1)

        print(f"Restoring SQL dump ({len(sql_content)} bytes of SQL code) to database...")
        service.run_restore(sql_content=sql_content)
        print("Database restore completed successfully!")

    except Exception as err:
        print(f"Error during database restore: {err}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
