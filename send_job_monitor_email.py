"""Send a job-monitor report through SMTP using environment configuration."""

from __future__ import annotations

import argparse
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Email a job-monitor Markdown report.")
    parser.add_argument("--subject", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    host = os.environ.get("SMTP_HOST", "").strip() or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT", "").strip() or "465")
    username = _required("SMTP_USERNAME")
    password = _required("SMTP_PASSWORD")
    recipient = _required("JOB_MONITOR_EMAIL_TO")
    sender = os.environ.get("JOB_MONITOR_EMAIL_FROM", username).strip()

    report = args.report.read_text()
    message = EmailMessage()
    message["Subject"] = args.subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(report)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as smtp:
        smtp.login(username, password)
        smtp.send_message(message)


if __name__ == "__main__":
    main()
