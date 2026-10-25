"""SQLite log of every dictation: raw transcript, cleaned text, timestamp."""

import sqlite3
import time

import config

DB_PATH = config.PROJECT_DIR / "history.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL NOT NULL,
            raw TEXT NOT NULL,
            cleaned TEXT NOT NULL
        )
        """
    )
    return conn


def add_entry(raw: str, cleaned: str):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO entries (ts, raw, cleaned) VALUES (?, ?, ?)",
            (time.time(), raw, cleaned),
        )


def fetch_entries(limit: int = 2000) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT ts, raw, cleaned FROM entries ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [{"ts": ts, "raw": raw, "cleaned": cleaned} for ts, raw, cleaned in rows]
