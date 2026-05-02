"""
TikTok Business API handler — Коментари и директни съобщения (DMs).

ВАЖНО: TikTok DM API изисква специално одобрение от TikTok for Business.
       Подайте заявка на: https://ads.tiktok.com/marketing_api/homepage
       Коментарите са достъпни чрез Comment Management API.
"""
import asyncio
import hashlib
import hmac
import json
import httpx
from fastapi import APIRouter, Request, HTTPException
from config import settings
from models import Platform
from order_manager import handle_message

router = APIRouter()

TIKTOK_API = "https://business-api.tiktok.com/open_api/v1.3"


# ─── Webhook вход ─────────────────────────────────────────────────────────────

@router.post("")
async def receive_webhook(request: Request):
    body_bytes = await request.body()
    _verify_tiktok_signature(request.headers, body_bytes)

    payload = json.loads(body_bytes)
    event_type = payload.get("type", "")

    if event_type == "comment":
        asyncio.create_task(_process_comment(payload))
    elif event_type == "direct_message":
        asyncio.create_task(_process_dm(payload))

    return {"code": 0}


# ─── Коментари ────────────────────────────────────────────────────────────────

async def _process_comment(payload: dict):
    data = payload.get("data", {})
    comment_id = str(data.get("comment_id", ""))
    video_id = str(data.get("video_id", ""))
    user_id = str(data.get("user_id", ""))
    text = data.get("text", "").strip()

    if not text or not user_id:
        return

    conv_id = f"tiktok_comment_{video_id}_{user_id}"

    reply = await asyncio.to_thread(
        handle_message,
        platform=Platform.TIKTOK_COMMENT,
        platform_user_id=user_id,
        platform_conversation_id=conv_id,
        user_text=text,
        reply_to_comment_id=comment_id,
    )

    await _reply_to_comment(video_id, comment_id, reply)


async def _reply_to_comment(video_id: str, comment_id: str, text: str):
    url = f"{TIKTOK_API}/comment/reply/create/"
    headers = {
        "Access-Token": settings.tiktok_access_token,
        "Content-Type": "application/json",
    }
    body = {
        "advertiser_id": settings.tiktok_advertiser_id,
        "video_id": video_id,
        "comment_id": comment_id,
        "text": text,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()


# ─── Директни съобщения (DMs) ─────────────────────────────────────────────────

async def _process_dm(payload: dict):
    data = payload.get("data", {})
    conversation_id = str(data.get("conversation_id", ""))
    sender_id = str(data.get("sender_open_id", ""))
    text = data.get("content", {}).get("text", "").strip()

    if not text or not sender_id:
        return

    reply = await asyncio.to_thread(
        handle_message,
        platform=Platform.TIKTOK_DM,
        platform_user_id=sender_id,
        platform_conversation_id=conversation_id,
        user_text=text,
    )

    await _send_dm(conversation_id, reply)


async def _send_dm(conversation_id: str, text: str):
    url = f"{TIKTOK_API}/customer_service/conversation/message/send/"
    headers = {
        "Access-Token": settings.tiktok_access_token,
        "Content-Type": "application/json",
    }
    body = {
        "advertiser_id": settings.tiktok_advertiser_id,
        "conversation_id": conversation_id,
        "message_type": "TEXT",
        "content": {"text": text},
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()


# ─── Подпис ───────────────────────────────────────────────────────────────────

def _verify_tiktok_signature(headers, body: bytes):
    signature = headers.get("X-TikTok-Signature", "")
    if not signature:
        return  # TikTok не винаги изпраща подпис в dev среда
    expected = hmac.new(
        settings.tiktok_app_secret.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=400, detail="Invalid TikTok signature")
