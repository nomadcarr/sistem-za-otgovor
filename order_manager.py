"""
Централна логика: получава съобщение от клиент, пуска AI,
обновява базата и връща текст за изпращане обратно.
"""
import json
from typing import Optional
from models import ConversationState, OrderInfo, Platform
from database import (
    upsert_conversation,
    get_conversation,
    update_conversation,
    add_message,
    save_order,
    save_declined,
)
from ai_engine import get_ai_response


def handle_message(
    platform: str,
    platform_user_id: str,
    platform_conversation_id: str,
    user_text: str,
    reply_to_comment_id: Optional[str] = None,
) -> str:
    """
    Обработва входящо съобщение и връща отговора, който трябва да се изпрати.
    """
    # Вземи или създай разговор
    upsert_conversation(platform, platform_user_id, platform_conversation_id, reply_to_comment_id)
    conv = get_conversation(platform, platform_conversation_id)
    conv_id = conv["id"]
    state = conv["state"]

    # Ако разговорът е вече приключил — нулиране за нов старт
    if state in (ConversationState.ORDER_CONFIRMED, ConversationState.CONCLUDED):
        update_conversation(
            conv_id,
            state=ConversationState.BROWSING,
            order_info_json="{}",
        )
        conv = get_conversation(platform, platform_conversation_id)
        state = conv["state"]

    # Ако чакаме отговор за отказ (ABANDONED_CHECK) и клиентът пише пак — продължаваме
    if state == ConversationState.ABANDONED_CHECK:
        update_conversation(conv_id, state=ConversationState.COLLECTING_ORDER)
        state = ConversationState.COLLECTING_ORDER

    # Запис на съобщението на потребителя
    add_message(conv_id, "user", user_text)

    # Зареди история и текуща поръчка
    conv = get_conversation(platform, platform_conversation_id)
    messages_history = json.loads(conv["messages_json"])
    order_info_dict = json.loads(conv["order_info_json"])
    current_order = OrderInfo.from_dict(order_info_dict) if order_info_dict else OrderInfo()

    # Извикай AI
    visible_text, confirmed_order, declined_reason = get_ai_response(
        messages_history=messages_history,
        current_order=current_order,
    )

    # Запис на отговора на AI
    add_message(conv_id, "assistant", visible_text)

    # Обработка на резултата
    if confirmed_order:
        save_order(conv_id, platform, confirmed_order)
        update_conversation(
            conv_id,
            state=ConversationState.ORDER_CONFIRMED,
            order_info_json=json.dumps(confirmed_order.to_dict(), ensure_ascii=False),
        )

    elif declined_reason:
        product = current_order.product_name or order_info_dict.get("product_name")
        save_declined(conv_id, platform, product, declined_reason)
        update_conversation(conv_id, state=ConversationState.ABANDONED)

    else:
        # Обнови частичните данни за поръчката ако AI е събрал нещо ново
        # (AI не ги изпраща директно, но ги съхраняваме чрез разговора)
        # Актуализирай само state ако сме в collecting фаза
        if state == ConversationState.BROWSING and _seems_ordering(user_text):
            update_conversation(conv_id, state=ConversationState.COLLECTING_ORDER)

    return visible_text


def handle_inactivity(conv_id: int, platform: str, platform_conversation_id: str) -> str:
    """
    Изпраща съобщение след час без отговор. Връща текста.
    """
    msg = (
        "Здравейте, забелязах, че не сте отговорили от известно време. "
        "Все още ли се интересувате от поръчка? "
        "Ако сте решили да не продължите, ще се радвам да знам защо — "
        "вашето мнение ни помага да се подобрим. 🙏"
    )
    update_conversation(conv_id, state=ConversationState.ABANDONED_CHECK)
    add_message(conv_id, "assistant", msg)
    return msg


def handle_abandonment_reply(conv_id: int, platform: str, platform_conversation_id: str, user_text: str):
    """
    Обработва отговора на клиента след питането за отказ.
    """
    conv = get_conversation(platform, platform_conversation_id)
    order_info_dict = json.loads(conv["order_info_json"])
    product = order_info_dict.get("product_name")

    add_message(conv_id, "user", user_text)

    # Питаме AI дали клиентът дава причина или иска да продължи
    messages = json.loads(conv["messages_json"])
    visible_text, confirmed_order, declined_reason = get_ai_response(messages_history=messages)

    add_message(conv_id, "assistant", visible_text)

    if confirmed_order:
        save_order(conv_id, platform, confirmed_order)
        update_conversation(conv_id, state=ConversationState.ORDER_CONFIRMED)
    else:
        save_declined(conv_id, platform, product, declined_reason or user_text)
        update_conversation(conv_id, state=ConversationState.ABANDONED)

    return visible_text


def _seems_ordering(text: str) -> bool:
    keywords = ["искам", "поръчам", "поръчка", "купя", "вземи", "запиши"]
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)
