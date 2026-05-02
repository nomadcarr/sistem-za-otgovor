import json
import re
from typing import Optional
import anthropic
from config import settings
from models import OrderInfo

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

with open("catalog.json", "r", encoding="utf-8") as f:
    _CATALOG_RAW = json.load(f)

_CATALOG_TEXT = ""
for p in _CATALOG_RAW["products"]:
    status = "НАЛИЧЕН" if p["available"] else "ИЗЧЕРПАН"
    variants = f" | Варианти: {', '.join(p['variants'])}" if p.get("variants") else ""
    _CATALOG_TEXT += (
        f"- {p['name']} — {p['price']} {p['currency']} [{status}]{variants}\n"
        f"  {p['description']}\n"
    )

_SHIPPING = _CATALOG_RAW.get("shipping", {})
_SHIPPING_TEXT = (
    f"Доставка до офис на Еконт: {_SHIPPING.get('econt_office', '?')} лв. | "
    f"Доставка до адрес: {_SHIPPING.get('home_address', '?')} лв. | "
    f"Безплатна доставка при поръчка над {_SHIPPING.get('free_over', '?')} лв."
)

_SYSTEM_PROMPT = f"""Ти си AI асистент за обслужване на клиенти на онлайн магазин. Отговаряш САМО на български език. Бъди кратък, учтив и конкретен.

== КАТАЛОГ ==
{_CATALOG_TEXT}
== ДОСТАВКА ==
{_SHIPPING_TEXT}

== ПРАВИЛА ==
1. Отговаряй само за продукти от каталога. При въпрос за нещо друго, учтиво кажи, че можеш да помагаш само с поръчки.
2. Когато клиент иска да поръча, събирай СТЪПКА ПО СТЪПКА (не всичко наведнъж):
   a) Продукт и количество (ако вече не е ясно)
   b) Две имена (собствено и фамилно)
   c) Телефон за връзка
   d) Начин на доставка — офис на Еконт (клиентът казва адреса на офиса) или домашен адрес
3. Когато ВСИЧКИТЕ данни са събрани, изпрати резюме на поръчката и поискай потвърждение.
4. При потвърждение от клиента, завърши съобщението с точно тази структура:

###ORDER_CONFIRMED###
{{
  "product_name": "...",
  "quantity": 1,
  "customer_name": "...",
  "phone": "...",
  "delivery_type": "econt_office или home_address",
  "delivery_address": "...",
  "total_price": "... лв."
}}
###END_ORDER###

5. Ако клиентът се отказва или изразява недоволство, САМО включи в отговора:
###ORDER_DECLINED###
{{
  "reason": "причина с думите на клиента"
}}
###END_DECLINED###

Никога не включвай ###ORDER_CONFIRMED### и ###ORDER_DECLINED### в един и същи отговор.
"""


def _extract_json_block(text: str, start_tag: str, end_tag: str) -> Optional[dict]:
    pattern = re.compile(re.escape(start_tag) + r"\s*(\{.*?\})\s*" + re.escape(end_tag), re.DOTALL)
    match = pattern.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def clean_response(text: str) -> str:
    """Премахва JSON блоковете от видимия отговор към клиента."""
    text = re.sub(r"###ORDER_CONFIRMED###.*?###END_ORDER###", "", text, flags=re.DOTALL)
    text = re.sub(r"###ORDER_DECLINED###.*?###END_DECLINED###", "", text, flags=re.DOTALL)
    return text.strip()


def get_ai_response(
    messages_history: list,
    current_order: Optional[OrderInfo] = None,
) -> tuple[str, Optional[OrderInfo], Optional[str]]:
    """
    Връща (visible_text, confirmed_order_or_None, declined_reason_or_None).
    messages_history е списък от {"role": ..., "content": ...}.
    """
    order_context = ""
    if current_order:
        filled = {k: v for k, v in current_order.to_dict().items() if v is not None}
        if filled:
            order_context = f"\n\n== СЪБРАНА ИНФОРМАЦИЯ ЗА ПОРЪЧКАТА ДО МОМЕНТА ==\n{json.dumps(filled, ensure_ascii=False, indent=2)}"

    system = _SYSTEM_PROMPT + order_context

    # Взимаме само role/content за Anthropic API
    api_messages = [{"role": m["role"], "content": m["content"]} for m in messages_history]

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system,
        messages=api_messages,
    )

    raw_text = response.content[0].text

    # Проверяваме за потвърдена поръчка
    confirmed_data = _extract_json_block(raw_text, "###ORDER_CONFIRMED###", "###END_ORDER###")
    confirmed_order = None
    if confirmed_data:
        confirmed_order = OrderInfo(
            product_name=confirmed_data.get("product_name"),
            quantity=int(confirmed_data.get("quantity", 1)),
            customer_name=confirmed_data.get("customer_name"),
            phone=confirmed_data.get("phone"),
            delivery_type=confirmed_data.get("delivery_type"),
            delivery_address=confirmed_data.get("delivery_address"),
            total_price=confirmed_data.get("total_price"),
        )

    # Проверяваме за отказ
    declined_data = _extract_json_block(raw_text, "###ORDER_DECLINED###", "###END_DECLINED###")
    declined_reason = declined_data.get("reason") if declined_data else None

    visible_text = clean_response(raw_text)
    return visible_text, confirmed_order, declined_reason
