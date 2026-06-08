import os

import psycopg
from psycopg.rows import dict_row


def get_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL не знайдено у Railway Variables")
    return psycopg.connect(database_url, row_factory=dict_row)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id SERIAL PRIMARY KEY,
                    telegram_chat_id BIGINT NOT NULL,
                    user_message TEXT NOT NULL,
                    category TEXT,
                    priority TEXT,
                    status TEXT DEFAULT 'open',
                    ai_summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS support_messages (
                    id SERIAL PRIMARY KEY,
                    telegram_chat_id BIGINT NOT NULL,
                    user_message TEXT NOT NULL,
                    ai_answer TEXT,
                    category TEXT,
                    confidence TEXT,
                    used_kb BOOLEAN DEFAULT FALSE,
                    ticket_id INTEGER REFERENCES support_tickets(id) ON DELETE SET NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.commit()


def save_message(telegram_chat_id, user_message, ai_answer, category, confidence, used_kb, ticket_id=None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO support_messages (
                    telegram_chat_id, user_message, ai_answer, category, confidence, used_kb, ticket_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
                """,
                (telegram_chat_id, user_message, ai_answer, category, confidence, used_kb, ticket_id),
            )
            row = cur.fetchone()
            conn.commit()
            return row["id"]


def create_ticket(telegram_chat_id, user_message, category, priority, ai_summary):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO support_tickets (
                    telegram_chat_id, user_message, category, priority, ai_summary, status
                ) VALUES (%s, %s, %s, %s, %s, 'open') RETURNING id;
                """,
                (telegram_chat_id, user_message, category, priority, ai_summary),
            )
            row = cur.fetchone()
            conn.commit()
            return row["id"]


def list_tickets(telegram_chat_id, limit=20):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM support_tickets WHERE telegram_chat_id = %s ORDER BY id DESC LIMIT %s;",
                (telegram_chat_id, limit),
            )
            return cur.fetchall()


def get_ticket(ticket_id, telegram_chat_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM support_tickets WHERE id = %s AND telegram_chat_id = %s;",
                (ticket_id, telegram_chat_id),
            )
            return cur.fetchone()


def update_ticket_status(ticket_id, telegram_chat_id, status):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE support_tickets
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND telegram_chat_id = %s
                RETURNING id;
                """,
                (status, ticket_id, telegram_chat_id),
            )
            row = cur.fetchone()
            conn.commit()
            return row is not None


def list_messages(telegram_chat_id, limit=20):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM support_messages WHERE telegram_chat_id = %s ORDER BY id DESC LIMIT %s;",
                (telegram_chat_id, limit),
            )
            return cur.fetchall()


def get_report(telegram_chat_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, COUNT(*) AS count FROM support_tickets WHERE telegram_chat_id = %s GROUP BY status ORDER BY status;",
                (telegram_chat_id,),
            )
            tickets_by_status = cur.fetchall()
            cur.execute(
                "SELECT category, COUNT(*) AS count FROM support_messages WHERE telegram_chat_id = %s GROUP BY category ORDER BY category;",
                (telegram_chat_id,),
            )
            messages_by_category = cur.fetchall()
            cur.execute(
                "SELECT COUNT(*) AS count FROM support_messages WHERE telegram_chat_id = %s;",
                (telegram_chat_id,),
            )
            total_messages = cur.fetchone()["count"]
            return {
                "tickets_by_status": tickets_by_status,
                "messages_by_category": messages_by_category,
                "total_messages": total_messages,
            }


def clear_all(telegram_chat_id):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM support_messages WHERE telegram_chat_id = %s;", (telegram_chat_id,))
            cur.execute("DELETE FROM support_tickets WHERE telegram_chat_id = %s;", (telegram_chat_id,))
            conn.commit()
