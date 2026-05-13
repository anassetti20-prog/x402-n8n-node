"""
x402 Purchase System – API Key Management + USDC Payment Verification
SQLite-based, zero external dependencies.
"""
import os
import json
import time
import uuid
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "purchase.db"

SERVICES = {
    "halal-check":  {"name": "Halal Screening",    "price": 0.01, "desc": "Check crypto Sharia compliance"},
    "search":       {"name": "Web Search",          "price": 0.01, "desc": "Search the web for information"},
    "analyze-code": {"name": "Code Analysis",       "price": 0.05, "desc": "Analyze source code for bugs"},
    "process-data": {"name": "Data Processing",     "price": 0.02, "desc": "Transform, filter, validate data"},
    "translate":    {"name": "Translation",         "price": 0.01, "desc": "Translate text between languages"},
    "generate-text":{"name": "Text Generation",     "price": 0.02, "desc": "Generate AI text in various styles"},
    "scrape":       {"name": "Web Scraping",        "price": 0.02, "desc": "Clean text extraction with Halal filter (Firecrawl alt)"},
    "search-ai":    {"name": "AI Search",           "price": 0.01, "desc": "Top 5 websites via DuckDuckGo (Tavily alt)"},
    "execute-code": {"name": "Code Execution",      "price": 0.05, "desc": "Secure Python sandbox execution (E2B alt)"},
    "deep-research":{"name": "Deep Research",       "price": 0.05, "desc": "5 sources + structured report"},
    "maas-campaign":{"name": "Marketing as a Service","price": 0.50,"desc": "7-day marketing plan + posts"},
    "url-to-mcp":   {"name": "URL to MCP Bridge","price": 0.05,"desc": "Convert any webpage to MCP-compatible tool schemas"},
    # ── PHASE 2 — Sequoia Expansion ──
    "legal-ai":     {"name": "Legal AI — Contract Analysis","price": 0.25,"desc": "AI-powered contract review (OpenRouter)"},
    "ai-tutor":     {"name": "AI Tutor — Education Assistant","price": 0.10,"desc": "AI tutoring on any subject"},
    "resume-analyzer":{"name": "Resume Analyzer — HR & Recruiting","price": 0.20,"desc": "AI resume analysis & job matching"},
}

# Pre-paid bundles
BUNDLES = {
    "starter":  {"requests": 500,  "price_usd": 5.00,  "desc": "500 requests — $5"},
    "pro":      {"requests": 3000, "price_usd": 20.00, "desc": "3000 requests — $20 (33% discount)"},
    "enterprise":{"requests": 10000,"price_usd": 50.00, "desc": "10000 requests — $50 (50% discount)"},
}

WALLET_ADDRESS = os.environ.get("WALLET_ADDRESS", "0xeB262928D55A92f2EAac946807CeC4d80E9EdD6B")


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Initialize the database tables."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_id TEXT PRIMARY KEY,
            api_key TEXT UNIQUE NOT NULL,
            owner TEXT,
            email TEXT DEFAULT '',
            requests_total INTEGER DEFAULT 0,
            requests_used INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at REAL,
            expires_at REAL
        );
        CREATE TABLE IF NOT EXISTS purchases (
            tx_id TEXT PRIMARY KEY,
            api_key TEXT,
            bundle TEXT,
            amount_usdc REAL,
            status TEXT DEFAULT 'pending',
            created_at REAL,
            verified_at REAL
        );
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            api_key TEXT,
            service TEXT,
            timestamp REAL,
            ip TEXT
        );
    """)
    conn.commit()
    conn.close()


def generate_api_key() -> str:
    """Generate a unique API key in format x402_<uuid>."""
    return f"x402_{uuid.uuid4().hex}"


def register(email: str) -> dict:
    """Register a new user by email. Returns a free trial API key with 10 free credits."""
    conn = _get_db()
    # Check if email already registered
    existing = conn.execute("SELECT api_key FROM api_keys WHERE email = ?", (email.lower(),)).fetchone()
    if existing:
        conn.close()
        return {"error": "Email already registered", "api_key": existing["api_key"]}

    api_key = generate_api_key()
    key_id = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    now = time.time()

    # Free trial: 10 requests
    conn.execute(
        "INSERT INTO api_keys (key_id, api_key, owner, email, requests_total, requests_used, status, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, 10, 0, 'active', ?, ?)",
        (key_id, api_key, email, email.lower(), now, now + 365 * 86400),
    )
    conn.commit()
    conn.close()

    return {
        "api_key": api_key,
        "email": email.lower(),
        "free_credits": 10,
        "plans": {k: v for k, v in BUNDLES.items()},
        "message": "✅ Free account created! Use X-API-Key header to authenticate.",
    }


def recharge(api_key: str, bundle: str) -> dict:
    """Add credits to an existing API key. Returns payment instructions."""
    bundle_info = BUNDLES.get(bundle)
    if not bundle_info:
        return {"error": f"Unknown bundle: {bundle}"}

    conn = _get_db()
    row = conn.execute("SELECT * FROM api_keys WHERE api_key = ?", (api_key,)).fetchone()
    conn.close()

    if not row:
        return {"error": "API key not found"}

    return {
        "bundle": bundle,
        "requests": bundle_info["requests"],
        "price_usd": bundle_info["price_usd"],
        "api_key": api_key,
        "payment": {
            "method": "PayPal (manuell)",
            "instructions": f"Sende ${bundle_info['price_usd']:.2f} an anas_setti@gmx.de via PayPal mit Nachricht 'x402 {bundle} {api_key}'",
            "alternative": f"Oder sende ${bundle_info['price_usd']:.2f} USDC on Base an {WALLET_ADDRESS} mit memo: {api_key[:8]}",
            "status": "pending_manual",
        },
        "message": "Nach Zahlungseingang wird dein Konto manuell freigeschaltet.",
    }


def confirm_recharge(api_key: str, bundle: str) -> dict:
    """INTERNAL: Called by admin after payment confirmation. Adds credits."""
    bundle_info = BUNDLES.get(bundle)
    if not bundle_info:
        return {"error": f"Unknown bundle: {bundle}"}

    conn = _get_db()
    conn.execute(
        "UPDATE api_keys SET requests_total = requests_total + ? WHERE api_key = ?",
        (bundle_info["requests"], api_key),
    )
    conn.commit()
    conn.close()
    return {"success": True, "api_key": api_key, "added": bundle_info["requests"], "bundle": bundle}


def get_credits(api_key: str) -> dict:
    """Check remaining credits for an API key."""
    info = verify_api_key(api_key)
    if not info:
        return {"error": "Invalid or exhausted API key"}

    return {
        "api_key": api_key[:12] + "...",
        "email": info.get("owner", ""),
        "credits_remaining": info["remaining"],
        "credits_total": info["requests_total"],
        "credits_used": info["requests_used"],
        "plans": {k: v["desc"] for k, v in BUNDLES.items()},
        "recharge_endpoint": "POST /recharge",
    }


def create_api_key(bundle: str, owner: str = "telegram") -> dict:
    """Create a new API key with request credits."""
    bundle_info = BUNDLES.get(bundle)
    if not bundle_info:
        return {"error": f"Unknown bundle: {bundle}"}

    api_key = generate_api_key()
    key_id = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    now = time.time()

    conn = _get_db()
    conn.execute(
        "INSERT INTO api_keys (key_id, api_key, owner, requests_total, requests_used, status, created_at, expires_at) "
        "VALUES (?, ?, ?, ?, 0, 'active', ?, ?)",
        (key_id, api_key, owner, bundle_info["requests"], now, now + 365 * 86400),
    )
    conn.commit()
    conn.close()

    return {
        "api_key": api_key,
        "requests": bundle_info["requests"],
        "bundle": bundle,
        "price_paid": bundle_info["price_usdc"],
        "created_at": now,
    }


def verify_api_key(api_key: str) -> Optional[dict]:
    """Verify an API key and return its info. Returns None if invalid."""
    conn = _get_db()
    row = conn.execute(
        "SELECT * FROM api_keys WHERE api_key = ? AND status = 'active'",
        (api_key,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    now = time.time()
    if row["expires_at"] and now > row["expires_at"]:
        return None

    remaining = row["requests_total"] - row["requests_used"]
    if remaining <= 0:
        return None

    return {
        "key_id": row["key_id"],
        "owner": row["owner"],
        "email": row["email"] if "email" in row.keys() else "",
        "requests_total": row["requests_total"],
        "requests_used": row["requests_used"],
        "remaining": remaining,
    }


def use_api_key(api_key: str, service: str, ip: str = "") -> bool:
    """Consume one request from an API key. Returns True if successful."""
    info = verify_api_key(api_key)
    if not info:
        return False

    conn = _get_db()
    conn.execute(
        "UPDATE api_keys SET requests_used = requests_used + 1 WHERE api_key = ?",
        (api_key,),
    )
    conn.execute(
        "INSERT INTO usage_log (api_key, service, timestamp, ip) VALUES (?, ?, ?, ?)",
        (api_key, service, time.time(), ip),
    )
    conn.commit()
    conn.close()
    return True


def record_purchase(tx_hash: str, api_key: str, bundle: str, amount_usdc: float) -> dict:
    """Record a purchase."""
    conn = _get_db()
    conn.execute(
        "INSERT OR REPLACE INTO purchases (tx_id, api_key, bundle, amount_usdc, status, created_at, verified_at) "
        "VALUES (?, ?, ?, ?, 'verified', ?, ?)",
        (tx_hash, api_key, bundle, amount_usdc, time.time(), time.time()),
    )
    conn.commit()
    conn.close()
    return {"tx_hash": tx_hash, "api_key": api_key, "bundle": bundle, "amount": amount_usdc}


def get_status() -> dict:
    """Get system status."""
    conn = _get_db()
    keys = conn.execute("SELECT COUNT(*) as c FROM api_keys").fetchone()["c"]
    active = conn.execute("SELECT COUNT(*) as c FROM api_keys WHERE status='active'").fetchone()["c"]
    total_req = conn.execute("SELECT COALESCE(SUM(requests_total), 0) as s FROM api_keys").fetchone()["s"]
    used_req = conn.execute("SELECT COALESCE(SUM(requests_used), 0) as s FROM api_keys").fetchone()["s"]
    purchases = conn.execute("SELECT COUNT(*) as c FROM purchases WHERE status='verified'").fetchone()["c"]
    revenue = conn.execute("SELECT COALESCE(SUM(amount_usdc), 0) as s FROM purchases WHERE status='verified'").fetchone()["s"]
    conn.close()
    return {
        "api_keys_created": keys,
        "api_keys_active": active,
        "total_requests_purchased": total_req,
        "total_requests_used": used_req,
        "total_purchases": purchases,
        "total_revenue_usdc": revenue,
        "wallet": WALLET_ADDRESS,
    }


# Initialize on import
if not DB_PATH.exists():
    init_db()