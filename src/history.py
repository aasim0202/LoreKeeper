"""
LoreKeeper 3.0 — Query History Persistence (SQLite)
Lightweight, zero-dependency persistence for past queries.
"""
import sqlite3
import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("HISTORY_DB_PATH", "lorekeeper_history.db")


def _get_conn():
    """Returns a new connection with WAL mode for concurrent reads."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Creates the history table if it doesn't exist."""
    try:
        conn = _get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS query_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                user_message TEXT NOT NULL,
                reply TEXT,
                action_items TEXT,
                latency TEXT,
                source TEXT DEFAULT 'web'
            )
        """)
        conn.commit()
        conn.close()
        logger.info("Query history database initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize history DB: {e}")


def log_query(user_message: str, reply: str, action_items: list, latency: dict, source: str = "web"):
    """
    Writes a completed query to the history table.
    Designed to be called as a non-blocking background task — failures are logged but never raised.
    """
    try:
        conn = _get_conn()
        conn.execute(
            "INSERT INTO query_history (timestamp, user_message, reply, action_items, latency, source) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                user_message,
                reply,
                json.dumps(action_items),
                json.dumps(latency),
                source
            )
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to log query to history: {e}")


def get_history(limit: int = 20, offset: int = 0) -> list:
    """Returns recent query history, newest first."""
    try:
        conn = _get_conn()
        rows = conn.execute(
            "SELECT * FROM query_history ORDER BY id DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        conn.close()
        result = []
        for row in rows:
            entry = dict(row)
            # Parse JSON fields back
            try:
                entry["action_items"] = json.loads(entry["action_items"]) if entry["action_items"] else []
            except (json.JSONDecodeError, TypeError):
                entry["action_items"] = []
            try:
                entry["latency"] = json.loads(entry["latency"]) if entry["latency"] else {}
            except (json.JSONDecodeError, TypeError):
                entry["latency"] = {}
            result.append(entry)
        return result
    except Exception as e:
        logger.error(f"Failed to read history: {e}")
        return []
