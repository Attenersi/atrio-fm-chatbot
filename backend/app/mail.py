from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any

from .config import (
    ADMIN_NOTIFY_EMAIL,
    MAIL_FROM,
    MAIL_NOTIFY_NEW_TICKETS,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


def _admin_recipients() -> list[str]:
    raw = (ADMIN_NOTIFY_EMAIL or "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def mail_configured() -> bool:
    return bool(SMTP_HOST and MAIL_FROM and _admin_recipients())


def send_plain_text(to_addrs: list[str], subject: str, body: str) -> None:
    if not to_addrs or not subject:
        return
    if not SMTP_HOST or not MAIL_FROM:
        logger.debug("Mail skipped: SMTP_HOST or MAIL_FROM not set")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = MAIL_FROM
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body, subtype="plain", charset="utf-8")
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
                if SMTP_USER and SMTP_PASSWORD:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
                smtp.ehlo()
                if SMTP_PORT != 25:
                    smtp.starttls()
                    smtp.ehlo()
                if SMTP_USER and SMTP_PASSWORD:
                    smtp.login(SMTP_USER, SMTP_PASSWORD)
                smtp.send_message(msg)
    except Exception:
        logger.exception("Failed to send email to %s", to_addrs)


def _should_notify_new_ticket(priority: str) -> bool:
    mode = (MAIL_NOTIFY_NEW_TICKETS or "all").strip().lower()
    if mode in {"0", "false", "off", "no"}:
        return False
    if mode in {"urgent", "urgent_only"}:
        return priority.upper() == "URGENT"
    return True


def notify_ticket_created(ticket: dict[str, Any], creator_username: str | None) -> None:
    if not mail_configured() or not _should_notify_new_ticket(str(ticket.get("priority", ""))):
        return
    tid = ticket.get("id")
    subj = f"[Atrio FM] New ticket #{tid} ({ticket.get('priority', '')})"
    who = creator_username or "unknown"
    body = (
        f"A new maintenance ticket was created.\n\n"
        f"ID: {tid}\n"
        f"Priority: {ticket.get('priority')}\n"
        f"Category: {ticket.get('category')}\n"
        f"Status: {ticket.get('status')}\n"
        f"Created by: {who}\n"
        f"Department: {ticket.get('department')}\n\n"
        f"Summary:\n{ticket.get('issue_summary', '')}\n\n"
        f"Message (excerpt):\n{str(ticket.get('message', ''))[:800]}\n"
    )
    send_plain_text(_admin_recipients(), subj, body)


def notify_ticket_status_changed(
    ticket_before: dict[str, Any],
    ticket_after: dict[str, Any],
    old_status: str,
    creator_email: str | None,
) -> None:
    new_status = str(ticket_after.get("status", ""))
    if old_status == new_status:
        return
    tid = ticket_after.get("id")
    subj = f"[Atrio FM] Ticket #{tid} status: {old_status} → {new_status}"
    body = (
        f"Ticket #{tid} status changed.\n\n"
        f"Was: {old_status}\n"
        f"Now: {new_status}\n"
        f"Category: {ticket_after.get('category')}\n"
        f"Priority: {ticket_after.get('priority')}\n"
        f"Summary: {ticket_after.get('issue_summary', '')}\n"
    )
    recipients: list[str] = []
    recipients.extend(_admin_recipients())
    if creator_email and creator_email.strip() and creator_email not in recipients:
        recipients.append(creator_email.strip())
    if not recipients:
        return
    if not SMTP_HOST or not MAIL_FROM:
        return
    send_plain_text(recipients, subj, body)
