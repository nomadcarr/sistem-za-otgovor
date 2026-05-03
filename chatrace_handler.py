import httpx
from fastapi import APIRouter, Request, HTTPException
from database import init_db
from order_manager import handle_message
import os

router = APIRouter()

CHATRACE_API_KEY = os.environ.get("CHATRACE_API_KEY", "")
CHATRACE_API_URL = "https://api.chatrace.com"


async def send_chatrace_reply(contact_id: str, text: str, channel: str = "messenger"):
    headers = {"api-key": CHATRACE_API_KEY, "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{CHATRACE_API_URL}/contacts/{contact_id}/send/text",
            headers=headers,
            json={"text": text, "channel": channel},
        )
        r.raise_for_status()


@router.post("/webhook")
async def chatrace_webhook(request: Request):
    """
    Извиква се от Chatrace flow при ново съобщение от клиент.

    Очакван payload:
    {
      "contact_id": "12345",
      "message":    "текст от клиента",
      "channel":    "messenger"   (незадължително, default: messenger)
    }
    """
    body = await request.json()

    contact_id = str(body.get("contact_id", "")).strip()
    message    = str(body.get("message", "")).strip()
    channel    = str(body.get("channel", "messenger")).strip()

    if not contact_id or not message:
        raise HTTPException(status_code=400, detail="contact_id and message are required")

    platform_map = {
        "messenger":  "facebook_messenger",
        "instagram":  "instagram",
        "tiktok":     "tiktok_dm",
        "whatsapp":   "whatsapp",
    }
    platform = platform_map.get(channel, channel)

    reply = handle_message(
        platform=platform,
        platform_user_id=contact_id,
        platform_conversation_id=contact_id,
        user_text=message,
    )

    await send_chatrace_reply(contact_id, reply, channel)

    return {"success": True, "reply": reply}
