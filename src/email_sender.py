"""Envía el informe y la transcripción de una reunión por email vía SMTP
(por defecto, Gmail con una 'contraseña de aplicación')."""

import os
import smtplib
from email.message import EmailMessage


def is_enabled() -> bool:
    return os.environ.get("EMAIL_ENABLED", "false").strip().lower() in ("1", "true", "yes", "si", "sí")


def send_meeting_email(report_path: str, transcript_path: str, spec_path: str = None) -> None:
    """Envía report.md (como cuerpo), transcript.txt y — si se pasa — spec.md
    (adjuntos) por email. No hace nada si EMAIL_ENABLED no está activado."""
    if not is_enabled():
        return

    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    email_from = os.environ.get("EMAIL_FROM")
    email_from = email_from.strip() if email_from else email_from
    # Google muestra la contraseña de aplicación como "xxxx xxxx xxxx xxxx";
    # aceptamos que la hayan pegado con esos espacios.
    email_password = os.environ.get("EMAIL_APP_PASSWORD")
    email_password = email_password.replace(" ", "").strip() if email_password else email_password
    email_to = os.environ.get("EMAIL_TO")

    missing = [
        name
        for name, value in [
            ("EMAIL_FROM", email_from),
            ("EMAIL_APP_PASSWORD", email_password),
            ("EMAIL_TO", email_to),
        ]
        if not value
    ]
    if missing:
        print(
            f"Aviso: EMAIL_ENABLED=true pero faltan estas variables en .env: {', '.join(missing)}. "
            "No se envió el email."
        )
        return

    recipients = [addr.strip() for addr in email_to.split(",") if addr.strip()]

    with open(report_path, "r", encoding="utf-8") as f:
        report_body = f.read()

    meeting_name = os.path.basename(os.path.dirname(os.path.abspath(report_path)))

    message = EmailMessage()
    message["Subject"] = f"Informe de reunión — {meeting_name}"
    message["From"] = email_from
    message["To"] = ", ".join(recipients)
    message.set_content(report_body)

    with open(transcript_path, "rb") as f:
        message.add_attachment(
            f.read(),
            maintype="text",
            subtype="plain",
            filename="transcript.txt",
        )

    if spec_path and os.path.exists(spec_path):
        with open(spec_path, "rb") as f:
            message.add_attachment(
                f.read(),
                maintype="text",
                subtype="markdown",
                filename="spec.md",
            )

    print(f"Enviando email a {', '.join(recipients)}...")
    with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as smtp:
        smtp.starttls()
        smtp.login(email_from, email_password)
        smtp.send_message(message)

    print("Email enviado.")
