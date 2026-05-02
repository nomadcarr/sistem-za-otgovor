from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


class Platform(str, Enum):
    FACEBOOK_MESSENGER = "facebook_messenger"
    FACEBOOK_COMMENT = "facebook_comment"
    TIKTOK_DM = "tiktok_dm"
    TIKTOK_COMMENT = "tiktok_comment"
    OLX_EMAIL = "olx_email"


class ConversationState(str, Enum):
    BROWSING = "browsing"                  # Разглеждане / въпроси за продукти
    COLLECTING_ORDER = "collecting_order"  # Събиране на данни за поръчка
    ORDER_CONFIRMED = "order_confirmed"    # Поръчката е потвърдена
    ABANDONED_CHECK = "abandoned_check"    # Изпратено питане за отказ
    ABANDONED = "abandoned"                # Клиентът се е отказал
    CONCLUDED = "concluded"                # Разговорът е приключил нормално


@dataclass
class OrderInfo:
    product_name: Optional[str] = None
    quantity: Optional[int] = None
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    delivery_type: Optional[str] = None   # "econt_office" или "home_address"
    delivery_address: Optional[str] = None
    total_price: Optional[str] = None

    def is_complete(self) -> bool:
        return all([
            self.product_name,
            self.quantity,
            self.customer_name,
            self.phone,
            self.delivery_type,
            self.delivery_address,
        ])

    def to_dict(self) -> dict:
        return {
            "product_name": self.product_name,
            "quantity": self.quantity,
            "customer_name": self.customer_name,
            "phone": self.phone,
            "delivery_type": self.delivery_type,
            "delivery_address": self.delivery_address,
            "total_price": self.total_price,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OrderInfo":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Message:
    role: str        # "user" или "assistant"
    content: str
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Conversation:
    id: int
    platform: Platform
    platform_user_id: str
    platform_conversation_id: str
    state: ConversationState
    order_info: OrderInfo
    messages: list
    last_message_time: datetime
    created_at: datetime
    abandoned_reason: Optional[str] = None
    reply_to_comment_id: Optional[str] = None  # За отговор в коментар


@dataclass
class Order:
    id: int
    conversation_id: int
    platform: Platform
    customer_name: str
    phone: str
    product_name: str
    quantity: int
    delivery_type: str
    delivery_address: str
    total_price: str
    created_at: datetime
