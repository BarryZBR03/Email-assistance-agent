from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from email_draft_agent.config import AppConfig


@dataclass(frozen=True)
class ParsedDraft:
    recipient: str
    subject: str
    body: str


def _field_value(line: str, label: str) -> str | None:
    prefix = f"{label}:"
    if line.lower().startswith(prefix.lower()):
        return line[len(prefix) :].strip()
    return None


def parse_draft_markdown(markdown: str) -> ParsedDraft:
    recipient = ""
    subject = ""
    body_lines: list[str] = []
    in_body = False

    for line in markdown.splitlines():
        if not in_body:
            to_value = _field_value(line, "To")
            if to_value is not None:
                recipient = to_value
                continue

            subject_value = _field_value(line, "Subject")
            if subject_value is not None:
                subject = subject_value
                continue

            body_value = _field_value(line, "Body")
            if body_value is not None:
                in_body = True
                if body_value:
                    body_lines.append(body_value)
                continue
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    if not recipient:
        raise RuntimeError("Draft is missing a To: recipient.")
    if not subject:
        raise RuntimeError("Draft is missing a Subject: line.")
    if not body:
        raise RuntimeError("Draft is missing a Body: section.")
    return ParsedDraft(recipient=recipient, subject=subject, body=body)


def _validate_smtp_config(config: AppConfig) -> None:
    if not config.email_address:
        raise RuntimeError("Missing EMAIL_ADDRESS for SMTP sending.")
    if not config.smtp_host:
        raise RuntimeError("Missing SMTP_HOST for SMTP sending.")
    if not config.smtp_auth_code:
        raise RuntimeError("Missing SMTP_AUTH_CODE for SMTP sending.")


def send_draft_email(config: AppConfig, markdown: str) -> ParsedDraft:
    _validate_smtp_config(config)
    draft = parse_draft_markdown(markdown)

    message = EmailMessage()
    message["From"] = config.email_address
    message["To"] = draft.recipient
    message["Subject"] = draft.subject
    message.set_content(draft.body)

    try:
        if config.smtp_port == 465:
            server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=20)
        else:
            server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=20)
            server.starttls()
        with server:
            server.login(config.email_address, config.smtp_auth_code)
            server.send_message(message)
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError("SMTP login failed. Check the SMTP settings and authorization code.") from exc
    except (OSError, smtplib.SMTPException) as exc:
        raise RuntimeError("Could not send email through SMTP. Check the SMTP settings and recipient.") from exc

    return draft
