import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "chat_conversations.db"


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         TEXT PRIMARY KEY,
                community  TEXT NOT NULL,
                title      TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT    NOT NULL,
                role            TEXT    NOT NULL,
                content         TEXT    NOT NULL,
                timestamp       TEXT    NOT NULL,
                files           TEXT,
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def create_conversation(community: str, title: str) -> str:
    conv_id = str(uuid.uuid4())
    now = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO conversations (id, community, title, created_at, updated_at) VALUES (?,?,?,?,?)",
            (conv_id, community, title, now, now),
        )
        conn.commit()
    return conv_id


def get_conversations_by_community(community: str) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM conversations WHERE community = ? ORDER BY updated_at DESC",
            (community,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_messages(conversation_id: str) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id ASC",
            (conversation_id,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("files"):
            try:
                d["files"] = json.loads(d["files"])
            except Exception:
                d["files"] = None
        result.append(d)
    return result


def save_message(
    conversation_id: str,
    role: str,
    content: str,
    files: list[dict] | None = None,
) -> None:
    now = datetime.now().isoformat()
    files_json = json.dumps(files) if files else None
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, timestamp, files) VALUES (?,?,?,?,?)",
            (conversation_id, role, content, now, files_json),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        conn.commit()


def update_conversation_title(conversation_id: str, new_title: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (new_title, conversation_id),
        )
        conn.commit()


def delete_conversation(conversation_id: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()


def generate_title_from_message(message: str, max_length: int = 50) -> str:
    text = message.strip()
    if len(text) <= max_length:
        return text
    truncated = text[:max_length]
    last_space = truncated.rfind(" ")
    if last_space > 10:
        return truncated[:last_space] + "…"
    return truncated + "…"
