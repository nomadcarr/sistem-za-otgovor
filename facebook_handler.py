"""
Facebook Messenger + Page Comments webhook handler.
Документация: https://developers.facebook.com/docs/messenger-platform/webhooks
"""
import hashlib
import hmac
import json
import asyncio
import httpx
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import PlainTextResponse
from config import settings
from models import Platform
from order_manager import handle_message

router = APIRouter()

GRAPH_API = "https://graph.facebook.com/v19.0"


# ─── Верификация на webhook ───────────────────────────────────────────────────

@router.get("")
async def verify_webhook(
    hub_mode: str = Query(alias="hub.mode", default=""),
    hub_verify_token: str = Query(alias="hub.verify_token", default=""),
    hub_challenge: str = Query(alias="hub.challenge", default=""),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.fb_verify_token:
        return PlainTextResponse(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")


# ─── Получаване на събития ────────────────────────────────────────────────────

@router.post("")
async def receive_webhook(request: Request):
    body_bytes = await request.body()
    _verify_signature(request.headers.get("X-Hub-Signature-256", ""), body_bytes)

    payload = json.loads(body_bytes)
    if payload.get("object") != "page":
        return {"status": "ignored"}

    for entry in payload.get("entry", []):
        # Messenger съобщения
        for event in entry.get("messaging", []):
            asyncio.create_task(_process_messenger_event(event))

        # Коментари под постове
        for change in entry.get("changes", []):
            if change.get("field") == "feed":
                asyncio.create_task(_process_comment_change(change["value"]))

    return {"status": "ok"}


# ─── Обработка на Messenger ───────────────────────────────────────────────────

async def _process_messenger_event(event: dict):
    sender_id = event.get("sender", {}).get("id")
    if not sender_id or sender_id == settings.fb_page_id:
        return  # Игнорираме ехо на наши съобщения

    message = event.get("message", {})
    text = message.get("text", "").strip()
    if not text:
        return

    reply = await asyncio.to_thread(
        handle_message,
        platform=Platform.FACEBOOK_MESSENGER,
        platform_user_id=sender_id,
        platform_conversation_id=sender_id,
        user_text=text,
    )

    await _send_messenger_message(sender_id, reply)


async def _send_messenger_message(recipient_id: str, text: str):
    url = f"{GRAPH_API}/me/messages"
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
    }
    async with httpx.AsyncClient() as client:
        await client.post(
            url,
            params={"access_token": settings.fb_page_access_token},
            json=payload,
            timeout=10,
        )


# ─── Обработка на коментари ───────────────────────────────────────────────────

async def _process_comment_change(value: dict):
    item = value.get("item")
    verb = value.get("verb")

    # Само нови коментари (не редакции, не изтривания)
    if item not in ("comment",) or verb not in ("add",):
        return

    comment_id = value.get("comment_id") or value.get("value", {}).get("comment_id")
    sender_id = value.get("sender_id") or str(value.get("from", {}).get("id", ""))
    text = value.get("message", "").strip()
    post_id = value.get("post_id", "")

    if not text or not sender_id or sender_id == settings.fb_page_id:
        return

    # conversation_id = post_id + sender_id (1 нишка на потребител на пост)
    conv_id = f"fb_comment_{post_id}_{sender_id}"

    reply = await asyncio.to_thread(
        handle_message,
        platform=Platform.FACEBOOK_COMMENT,
        platform_user_id=sender_id,
        platform_conversation_id=conv_id,
        user_text=text,
        reply_to_comment_id=comment_id,
    )

    await _reply_to_comment(comment_id, reply)


async def _reply_to_comment(comment_id: str, text: str):
    url = f"{GRAPH_API}/{comment_id}/comments"
    async with httpx.AsyncClient() as client:
        await client.post(
            url,
            params={"access_token": settings.fb_page_access_token},
            json={"message": text},
            timeout=10,
        )


# ─── Помощни ─────────────────────────────────────────────────────────────────

def _verify_signature(signature_header: str, body: bytes):
    expected = "sha256=" + hmac.new(
        settings.fb_app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature_header, expected):
        raise HTTPException(status_code=400, detail="Invalid signature")
