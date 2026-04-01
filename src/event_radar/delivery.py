from __future__ import annotations

import smtplib
from email.message import EmailMessage

from event_radar.config import AppConfig


class DeliveryError(RuntimeError):
    """Raised when sending email fails."""


def send_email(config: AppConfig, subject: str, body: str, smtp_password: str) -> None:
    smtp_config = config.delivery.smtp

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_config.from_address
    message["To"] = ", ".join(smtp_config.to)
    message.set_content(body)

    try:
        if smtp_config.port == 465:
            with smtplib.SMTP_SSL(smtp_config.host, smtp_config.port, timeout=20) as smtp:
                smtp.login(smtp_config.username, smtp_password)
                smtp.send_message(message)
            return

        with smtplib.SMTP(smtp_config.host, smtp_config.port, timeout=20) as smtp:
            smtp.starttls()
            smtp.login(smtp_config.username, smtp_password)
            smtp.send_message(message)
    except Exception as exc:
        raise DeliveryError(f"failed to send email: {exc}") from exc
