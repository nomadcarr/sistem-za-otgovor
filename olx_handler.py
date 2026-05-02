"""
OLX.bg handler — следи Gmail/IMAP за имейли от OLX и отговаря по SMTP.

OLX изпраща имейл с нотификация до твоя имейл когато клиент ти пише.
Отговорът към клиента минава обратно през OLX като reply на същия thread.
"""
import asyncio
import email
import re
from email.header import decode_header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import aiosmtplib
import aioimaplib

from config import settings
from models import Platform
from order_manager import handle_message


def _decode_str(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    parts = decode_header(str(value))
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def _extract_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        if payload:
            return payload.decode(charset, errors="replace")
    return ""


def _is_olx_email(msg: email.message.Message) -> bool:
    from_header = _decode_str(msg.get("From", ""))
    subject = _decode_str(msg.get("Subject", ""))
    filter_kw = settings.olx_email_filter.lower()
    return filter_kw in from_header.lower() or filter_kw in subject.lower()


def _get_reply_to(msg: email.message.Message) -> Optional[str]:
    return msg.get("Reply-To") or msg.get("From")


def _extract_message_id(msg: email.message.Message) -> str:
    return msg.get("Message-ID", "").strip()


def _extract_conversation_id(msg: email.message.Message) -> str:
    """Използваме References или In-Reply-To за thread ID, иначе Message-ID."""
    refs = msg.get("References", "") or msg.get("In-Reply-To", "")
    if refs:
        first_ref = refs.strip().split()[0]
        return first_ref
    return _extract_message_id(msg)


def _extract_sender_id(msg: email.message.Message) -> str:
    reply_to = _get_reply_to(msg)
    # Вземи само email адреса
    match = re.search(r"<([^>]+)>", reply_to or "")
    if match:
        return match.group(1)
    return (reply_to or "unknown").strip()


async def _send_email_reply(to_address: str, subject: str, body: str, in_reply_to: str):
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.email_address
    msg["To"] = to_address
    msg["Subject"] = subject if subject.startswith("Re:") else f"Re: {subject}"
    msg["In-Reply-To"] = in_reply_to
    msg["References"] = in_reply_to
    msg.attach(MIMEText(body, "plain", "utf-8"))

    await aiosmtplib.send(
        msg,
        hostname=settings.email_smtp_server,
        port=settings.email_smtp_port,
        username=settings.email_address,
        password=settings.email_password,
        start_tls=True,
    )


async def _process_email(raw_email: bytes, uid: str):
    msg = email.message_from_bytes(raw_email)
    if not _is_olx_email(msg):
        return

    body = _extract_body(msg).strip()
    if not body:
        return

    subject = _decode_str(msg.get("Subject", ""))
    reply_to = _get_reply_to(msg)
    sender_id = _extract_sender_id(msg)
    conv_id = _extract_conversation_id(msg)
    message_id = _extract_message_id(msg)

    reply_text = await asyncio.to_thread(
        handle_message,
        platform=Platform.OLX_EMAIL,
        platform_user_id=sender_id,
        platform_conversation_id=conv_id,
        user_text=body,
    )

    if reply_to:
        await _send_email_reply(
            to_address=reply_to,
            subject=subject,
            body=reply_text,
            in_reply_to=message_id,
        )


async def start_email_monitor():
    """Безкрайна задача, която следи входящата поща за OLX имейли."""
    print("[OLX] Стартиране на IMAP монитор...")
    while True:
        try:
            imap = aioimaplib.IMAP4_SSL(settings.email_imap_server)
            await imap.wait_hello_from_server()
            await imap.login(settings.email_address, settings.email_password)
            await imap.select("INBOX")

            # Търси непрочетени
            _, data = await imap.search("UNSEEN")
            uids = data[0].split() if data and data[0] else []

            for uid in uids:
                uid_str = uid.decode() if isinstance(uid, bytes) else uid
                _, msg_data = await imap.fetch(uid_str, "(RFC822)")
                if msg_data and len(msg_data) > 1:
                    raw = msg_data[1]
                    if isinstance(raw, tuple):
                        raw = raw[1]
                    await _process_email(raw, uid_str)
                    # Маркирай като прочетен
                    await imap.store(uid_str, "+FLAGS", "\\Seen")

            await imap.logout()

        except Exception as e:
            print(f"[OLX] Грешка при проверка на поща: {e}")

        # Проверка на всеки 2 минути
        await asyncio.sleep(120)
