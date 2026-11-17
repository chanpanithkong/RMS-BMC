"""MessageChannel adapter (SRS §12.12). SMTP when configured; otherwise logs the message (development)."""
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("rms.email")


class EmailSender:
    def __init__(self) -> None:
        self.host = os.environ.get("SMTP_HOST", "")
        self.port = int(os.environ.get("SMTP_PORT", "587"))
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")
        self.sender = os.environ.get("SMTP_FROM", "noreply@example.com")

    def send(self, to: str, subject: str, body: str) -> None:
        if not self.host:
            log.info("email (not sent, SMTP_HOST unset) to=%s subject=%s", to, subject)
            return
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender, to, subject
        msg.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=20) as s:
            s.starttls()
            if self.user:
                s.login(self.user, self.password)
            s.send_message(msg)
