
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("webhooks.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")

        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            payload TEXT NOT NULL,
            webhook_url TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            next_attempt_at TEXT,
            cycle_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until TEXT
        );

        CREATE TABLE IF NOT EXISTS delivery_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            attempted_at TEXT NOT NULL,
            http_status INTEGER,
            outcome TEXT NOT NULL,
            FOREIGN KEY (event_id)
                REFERENCES events(id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_due
        ON events(status, next_attempt_at);
        """)


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
