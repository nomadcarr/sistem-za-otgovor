import json
import sqlite3
from datetime import datetime
from typing import Optional, List
from models import Platform, ConversationState, OrderInfo


DB_PATH = "orders.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            platform_user_id TEXT NOT NULL,
            platform_conversation_id TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'browsing',
            order_info_json TEXT NOT NULL DEFAULT '{}',
            messages_json TEXT NOT NULL DEFAULT '[]',
            last_message_time TEXT NOT NULL,
            created_at TEXT NOT NULL,
            abandoned_reason TEXT,
            reply_to_comment_id TEXT,
            UNIQUE(platform, platform_conversation_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            delivery_type TEXT NOT NULL,
            delivery_address TEXT NOT NULL,
            total_price TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS declined_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            platform TEXT NOT NULL,
            product_name TEXT,
            reason TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(conversation_id) REFERENCES conversations(id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pending_outbound (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            user_id TEXT NOT NULL,
            conversation_id TEXT NOT NULL,
            message TEXT NOT NULL,
            reply_to_comment_id TEXT,
            sent INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


def _now() -> str:
    return datetime.utcnow().isoformat()


def upsert_conversation(
    platform: str,
    platform_user_id: str,
    platform_conversation_id: str,
    reply_to_comment_id: Optional[str] = None,
) -> dict:
    conn = get_conn()
    c = conn.cursor()
    now = _now()

    c.execute("""
        INSERT INTO conversations
            (platform, platform_user_id, platform_conversation_id,
             state, order_info_json, messages_json,
             last_message_time, created_at, reply_to_comment_id)
        VALUES (?, ?, ?, 'browsing', '{}', '[]', ?, ?, ?)
        ON CONFLICT(platform, platform_conversation_id) DO NOTHING
    """, (platform, platform_user_id, platform_conversation_id, now, now, reply_to_comment_id))

    conn.commit()

    c.execute(
        "SELECT * FROM conversations WHERE platform=? AND platform_conversation_id=?",
        (platform, platform_conversation_id),
    )
    row = dict(c.fetchone())
    conn.close()
    return row


def get_conversation(platform: str, platform_conversation_id: str) -> Optional[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        "SELECT * FROM conversations WHERE platform=? AND platform_conversation_id=?",
        (platform, platform_conversation_id),
    )
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_conversation(conv_id: int, **kwargs):
    if not kwargs:
        return
    conn = get_conn()
    c = conn.cursor()
    sets = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [conv_id]
    c.execute(f"UPDATE conversations SET {sets} WHERE id=?", values)
    conn.commit()
    conn.close()


def add_message(conv_id: int, role: str, content: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT messages_json FROM conversations WHERE id=?", (conv_id,))
    row = c.fetchone()
    messages = json.loads(row["messages_json"]) if row else []
    messages.append({"role": role, "content": content, "ts": _now()})
    # Пазим само последните 40 съобщения за да не растат безкрайно
    messages = messages[-40:]
    c.execute(
        "UPDATE conversations SET messages_json=?, last_message_time=? WHERE id=?",
        (json.dumps(messages, ensure_ascii=False), _now(), conv_id),
    )
    conn.commit()
    conn.close()


def save_order(conv_id: int, platform: str, order: OrderInfo) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO orders
            (conversation_id, platform, customer_name, phone,
             product_name, quantity, delivery_type, delivery_address,
             total_price, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        conv_id, platform,
        order.customer_name, order.phone,
        order.product_name, order.quantity,
        order.delivery_type, order.delivery_address,
        order.total_price, _now(),
    ))
    order_id = c.lastrowid
    conn.commit()
    conn.close()
    return order_id


def save_declined(conv_id: int, platform: str, product_name: Optional[str], reason: Optional[str]):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO declined_orders
            (conversation_id, platform, product_name, reason, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (conv_id, platform, product_name, reason, _now()))
    conn.commit()
    conn.close()


def get_todays_orders() -> List[dict]:
    conn = get_conn()
    c = conn.cursor()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    c.execute("SELECT * FROM orders WHERE created_at LIKE ?", (f"{today}%",))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_todays_declined() -> List[dict]:
    conn = get_conn()
    c = conn.cursor()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    c.execute("SELECT * FROM declined_orders WHERE created_at LIKE ?", (f"{today}%",))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def add_pending_outbound(platform: str, user_id: str, conversation_id: str, message: str, reply_to_comment_id: Optional[str] = None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO pending_outbound
            (platform, user_id, conversation_id, message, reply_to_comment_id, sent, created_at)
        VALUES (?, ?, ?, ?, ?, 0, ?)
    """, (platform, user_id, conversation_id, message, reply_to_comment_id, _now()))
    conn.commit()
    conn.close()


def get_pending_outbound() -> List[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM pending_outbound WHERE sent=0 ORDER BY created_at")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def mark_outbound_sent(message_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE pending_outbound SET sent=1 WHERE id=?", (message_id,))
    conn.commit()
    conn.close()


def get_inactive_conversations(timeout_minutes: int) -> List[dict]:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM conversations
        WHERE state NOT IN ('order_confirmed', 'abandoned', 'concluded')
        AND (
            (julianday('now') - julianday(last_message_time)) * 1440
        ) >= ?
    """, (timeout_minutes,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows
