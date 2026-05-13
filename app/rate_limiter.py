"""
x402 Rate Limiter — IP-based free tier
10 free calls per IP per day, resets at 00:00 UTC.
SQLite-backed, zero external dependencies.
"""
import os
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent / "rate_limiter.db"
DAILY_LIMIT = 10


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ip_usage (
            ip TEXT NOT NULL,
            date TEXT NOT NULL,
            count INTEGER DEFAULT 0,
            PRIMARY KEY (ip, date)
        );
    """)
    conn.commit()
    conn.close()


def _today() -> str:
    """Return today's date as YYYY-MM-DD in UTC."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_remaining(ip: str) -> int:
    """Get remaining free calls for this IP today."""
    conn = _get_db()
    row = conn.execute(
        "SELECT count FROM ip_usage WHERE ip = ? AND date = ?",
        (ip, _today()),
    ).fetchone()
    conn.close()
    used = row["count"] if row else 0
    return max(0, DAILY_LIMIT - used)


def consume(ip: str) -> bool:
    """
    Consume one free call for this IP.
    Returns True if under limit, False if exceeded.
    """
    today = _today()
    conn = _get_db()
    row = conn.execute(
        "SELECT count FROM ip_usage WHERE ip = ? AND date = ?",
        (ip, today),
    ).fetchone()

    if row:
        used = row["count"]
        if used >= DAILY_LIMIT:
            conn.close()
            return False
        conn.execute(
            "UPDATE ip_usage SET count = count + 1 WHERE ip = ? AND date = ?",
            (ip, today),
        )
    else:
        conn.execute(
            "INSERT INTO ip_usage (ip, date, count) VALUES (?, ?, 1)",
            (ip, today),
        )

    conn.commit()
    conn.close()
    return True


def get_client_ip(request) -> str:
    """Extract client IP from request, respecting X-Forwarded-For."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    if client:
        return client.host
    return "unknown"


# Initialize on import
if not DB_PATH.exists():
    init_db()
