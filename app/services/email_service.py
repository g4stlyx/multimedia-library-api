from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import urlencode

from app.core.config import Settings

logger = logging.getLogger("app.email")


class EmailDeliveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class EmailSendResult:
    sent: bool
    skipped: bool = False


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def is_configured(self) -> bool:
        return all(
            (
                self.settings.mail_host,
                self.settings.mail_port,
                self.settings.mail_username,
                self.settings.mail_password,
            )
        )

    def send_email_verification(self, *, to_email: str, token: str) -> EmailSendResult:
        verify_url = self._build_url(
            path=f"{self.settings.api_prefix}/auth/verify-email",
            token=token,
        )
        text = (
            "Verify your Project W email address.\n\n"
            f"Verification token:\n{token}\n\n"
            "If your client supports direct links, use this URL:\n"
            f"{verify_url}\n\n"
            "If you did not create this account, ignore this email."
        )
        return self._send(
            to_email=to_email,
            subject="Verify your Project W email",
            body=text,
        )

    def send_password_reset(self, *, to_email: str, token: str) -> EmailSendResult:
        reset_url = self._build_url(
            path=f"{self.settings.api_prefix}/auth/password-reset/confirm",
            token=token,
        )
        text = (
            "Reset your Project W password.\n\n"
            f"Password reset token:\n{token}\n\n"
            "If your client supports direct links, use this URL:\n"
            f"{reset_url}\n\n"
            "If you did not request a password reset, ignore this email."
        )
        return self._send(
            to_email=to_email,
            subject="Reset your Project W password",
            body=text,
        )

    def _send(self, *, to_email: str, subject: str, body: str) -> EmailSendResult:
        if not self.is_configured():
            logger.warning("email_delivery_skipped_not_configured")
            return EmailSendResult(sent=False, skipped=True)

        from_email = self.settings.mail_from_email or self.settings.mail_username
        if not from_email:
            logger.warning("email_delivery_skipped_missing_sender")
            return EmailSendResult(sent=False, skipped=True)

        message = EmailMessage()
        message["From"] = formataddr((self.settings.mail_from_name, from_email))
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(body)

        try:
            with smtplib.SMTP(
                self.settings.mail_host,
                self.settings.mail_port,
                timeout=self.settings.mail_timeout_seconds,
            ) as smtp:
                if self.settings.mail_starttls:
                    smtp.starttls()
                smtp.login(self.settings.mail_username, self._smtp_password())
                smtp.send_message(message)
        except Exception as exc:
            logger.exception("email_delivery_failed")
            raise EmailDeliveryError("email delivery failed") from exc

        logger.info("email_delivered")
        return EmailSendResult(sent=True)

    def _build_url(self, *, path: str, token: str) -> str:
        base_url = self.settings.app_base_url.rstrip("/")
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{base_url}{normalized_path}?{urlencode({'token': token})}"

    def _smtp_password(self) -> str:
        password = self.settings.mail_password or ""
        host = (self.settings.mail_host or "").casefold()
        if host in {"smtp.gmail.com", "gmail-smtp-in.l.google.com"}:
            return password.replace(" ", "")
        return password
