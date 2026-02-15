"""Send digest email via SMTP."""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


def send_email(subject: str, html_body: str, recipient: str = None) -> bool:
    """Send an HTML email via SMTP_SSL."""
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASSWORD", "")
    recipient = recipient or os.environ.get("DIGEST_RECIPIENT", "")

    if not all([user, password, recipient]):
        logger.error("SMTP credentials or recipient not configured. Set SMTP_USER, SMTP_PASSWORD, DIGEST_RECIPIENT.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = recipient

    # Plain text fallback
    plain = f"{subject}\n\nView this email in an HTML-capable client for the best experience."
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL(host, port) as server:
            server.login(user, password)
            server.sendmail(user, [recipient], msg.as_string())
        logger.info(f"Digest email sent to {recipient}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email: {e}")
        return False
