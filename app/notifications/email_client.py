"""Client e-mail SMTP asynchrone avec mode de simulation."""

from __future__ import annotations

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


class EmailClient:
    async def send(self, to: str, subject: str, body: str) -> dict:
        if settings.email_mock or not settings.smtp_host:
            logger.info("[EMAIL_MOCK] to=%s subject=%s", to, subject)
            return {"ok": True, "mock": True, "to": to, "subject": subject}
        if not settings.smtp_from_email:
            return {"ok": False, "error": "SMTP_FROM_EMAIL manquant"}

        message = EmailMessage()
        message["From"] = settings.smtp_from_email
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        try:
            await asyncio.to_thread(self._send_sync, message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.exception("Échec d'envoi e-mail vers %s", to)
            return {"ok": False, "error": type(exc).__name__}
        return {"ok": True, "mock": False, "to": to, "subject": subject}

    @staticmethod
    def _send_sync(message: EmailMessage) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if settings.smtp_use_tls:
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if settings.smtp_username:
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
