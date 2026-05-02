"""
Вътрешно API — извиква се от n8n workflows.

Endpoints:
  POST /internal/message        — входящо съобщение от клиент
  GET  /internal/pending        — съобщения за изпращане (inactivity check)
  POST /internal/pending/ack    — потвърди че съобщението е изпратено
"""
import asyncio
from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from order_manager import handle_message

router = APIRouter()


# ─── Модели ───────────────────────────────────────────────────────────────────

class IncomingMessage(BaseModel):
    platform: str           # "facebook_messenger", "facebook_comment", "olx_email"
    user_id: str            # ID на потребителя в съответната платформа
    conversation_id: str    # ID на разговора (за коментари: postId_userId)
    message: str            # Текстът на съобщението
    reply_to_comment_id: Optional[str] = None  # само за коментари


class MessageResponse(BaseModel):
    reply: str


class AckRequest(BaseModel):
    message_id: int


# ─── Входящо съобщение ────────────────────────────────────────────────────────

@router.post("/message", response_model=MessageResponse)
async def receive_message(data: IncomingMessage):
    """
    n8n извиква този endpoint при всяко ново съобщение от клиент.
    Връща AI отговора, който n8n изпраща обратно на клиента.
    """
    reply = await asyncio.to_thread(
        handle_message,
        platform=data.platform,
        platform_user_id=data.user_id,
        platform_conversation_id=data.conversation_id,
        user_text=data.message,
        reply_to_comment_id=data.reply_to_comment_id,
    )
    return {"reply": reply}


# ─── Pending outbound съобщения (за inactivity check) ────────────────────────

@router.get("/pending")
async def get_pending_messages():
    """
    n8n извиква на всеки 5 минути.
    Връща списък от съобщения, които трябва да се изпратят
    (напр. след час без отговор от клиента).
    """
    from database import get_pending_outbound
    messages = get_pending_outbound()
    return {"messages": messages}


@router.post("/pending/ack")
async def ack_message(data: AckRequest):
    """
    n8n извиква след като изпрати съобщението успешно.
    Маркира го като изпратено за да не се изпраща пак.
    """
    from database import mark_outbound_sent
    mark_outbound_sent(data.message_id)
    return {"status": "ok"}
