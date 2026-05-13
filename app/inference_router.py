"""
Inference Router — /v1/inference endpoint.
Statisches cheapest-first Routing: Deepseek primary, OpenAI fallback.
Kein AI-Routing, keine Loops, keine dynamischen Entscheidungen.
"""
import os
import re
import time
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import httpx

from .config import INTERNAL_KEY
from .rate_limiter import get_remaining, consume, get_client_ip
from .observability import (
    ErrorType, RequestStatus, classify_error, determine_status,
    generate_request_id, build_observability_log,
)
from .routing_policy import routing_decision_function
from purchase_system import verify_api_key, use_api_key

# ─── A2A BILLING ───
# Inline billing module for A2A agent-to-agent request accounting.
# Uses SQLite for atomic reservations, charges, and balance tracking.
import sqlite3
import threading
from pathlib import Path

_BILLING_DB = Path(__file__).parent / "a2a_billing.db"
_billing_lock = threading.Lock()


def _get_billing_db() -> sqlite3.Connection:
    """Get thread-local SQLite connection for A2A billing."""
    conn = sqlite3.connect(str(_BILLING_DB), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_accounts (
            agent_id TEXT PRIMARY KEY,
            balance REAL NOT NULL DEFAULT 0.0,
            reserved REAL NOT NULL DEFAULT 0.0,
            total_charged REAL NOT NULL DEFAULT 0.0,
            request_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key_hash TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            name TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            last_used_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS billing_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            actual_cost REAL,
            request_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def billing_reserve(agent_id: str, max_cost: float) -> dict:
    """
    Reserve budget for an A2A request.
    Returns {"ok": bool, "error": str|None, "reserved": float}.
    Auto-creates agent account with $10.00 starting balance if not exists.
    """
    with _billing_lock:
        conn = _get_billing_db()
        try:
            # Auto-create agent with starting balance
            conn.execute("""
                INSERT OR IGNORE INTO agent_accounts (agent_id, balance, reserved)
                VALUES (?, 10.0, 0.0)
            """, (agent_id,))

            # Check available balance (balance - reserved)
            row = conn.execute(
                "SELECT balance, reserved FROM agent_accounts WHERE agent_id = ?",
                (agent_id,)
            ).fetchone()
            available = row[0] - row[1]

            if available < max_cost:
                conn.close()
                return {"ok": False, "error": "INSUFFICIENT_BALANCE", "reserved": 0.0}

            # Reserve the amount
            conn.execute("""
                UPDATE agent_accounts
                SET reserved = reserved + ?, updated_at = datetime('now')
                WHERE agent_id = ?
            """, (max_cost, agent_id))

            # Log reservation
            conn.execute("""
                INSERT INTO billing_transactions (agent_id, type, amount, status)
                VALUES (?, 'reserve', ?, 'reserved')
            """, (agent_id, max_cost))

            conn.commit()
            conn.close()
            return {"ok": True, "error": None, "reserved": max_cost}
        except Exception as e:
            conn.close()
            return {"ok": False, "error": str(e), "reserved": 0.0}


def billing_charge(agent_id: str, actual_cost: float, request_id: str = None) -> dict:
    """
    Charge actual cost after A2A request execution.
    Releases unused reservation (max_cost - actual_cost).
    Returns {"ok": bool, "payment_status": str, "charged": float}.
    """
    with _billing_lock:
        conn = _get_billing_db()
        try:
            row = conn.execute(
                "SELECT balance, reserved FROM agent_accounts WHERE agent_id = ?",
                (agent_id,)
            ).fetchone()
            if not row:
                conn.close()
                return {"ok": False, "payment_status": "error", "charged": 0.0}

            balance, reserved = row

            # Calculate unused reservation to release
            unused = max(0.0, reserved - actual_cost)
            new_balance = balance - actual_cost
            new_reserved = reserved - actual_cost - unused

            # Update account
            conn.execute("""
                UPDATE agent_accounts
                SET balance = ?, reserved = ?,
                    total_charged = total_charged + ?,
                    request_count = request_count + 1,
                    updated_at = datetime('now')
                WHERE agent_id = ?
            """, (new_balance, max(0.0, new_reserved), actual_cost, agent_id))

            # Log charge
            conn.execute("""
                INSERT INTO billing_transactions
                (agent_id, type, amount, actual_cost, request_id, status)
                VALUES (?, 'charge', ?, ?, ?, 'charged')
            """, (agent_id, actual_cost, actual_cost, request_id))

            conn.commit()
            conn.close()
            return {"ok": True, "payment_status": "charged", "charged": actual_cost}
        except Exception as e:
            conn.close()
            return {"ok": False, "payment_status": "error", "charged": 0.0}


def billing_get_account(agent_id: str) -> dict:
    """Get account status for an agent."""
    conn = _get_billing_db()
    row = conn.execute(
        "SELECT agent_id, balance, reserved, total_charged, request_count FROM agent_accounts WHERE agent_id = ?",
        (agent_id,)
    ).fetchone()
    conn.close()
    if not row:
        return {"agent_id": agent_id, "balance": 0.0, "reserved": 0.0, "total_charged": 0.0, "request_count": 0}
    return {
        "agent_id": row[0], "balance": row[1], "reserved": row[2],
        "total_charged": row[3], "request_count": row[4]
    }


# ─── USAGE CONTROL ───

def _get_usage_db() -> sqlite3.Connection:
    """Get SQLite connection with usage limits table."""
    conn = sqlite3.connect(str(_BILLING_DB), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_usage_limits (
            agent_id TEXT PRIMARY KEY,
            requests_per_minute INTEGER NOT NULL DEFAULT 30,
            daily_spend_limit REAL NOT NULL DEFAULT 5.0,
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            request_id TEXT,
            cost REAL NOT NULL DEFAULT 0.0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def _ensure_usage_limit(agent_id: str) -> None:
    """Auto-create default usage limit for agent if not exists."""
    conn = _get_usage_db()
    conn.execute("""
        INSERT OR IGNORE INTO agent_usage_limits (agent_id, requests_per_minute, daily_spend_limit)
        VALUES (?, 30, 5.0)
    """, (agent_id,))
    conn.commit()
    conn.close()


def check_usage_limits(agent_id: str, estimated_cost: float = 0.0) -> dict:
    """
    Check RPM and daily spend limits for an agent.
    Returns {"ok": bool, "limit_type": str|None, "current_usage": dict}.
    """
    _ensure_usage_limit(agent_id)
    conn = _get_usage_db()
    try:
        # Get limits
        row = conn.execute(
            "SELECT requests_per_minute, daily_spend_limit FROM agent_usage_limits WHERE agent_id = ? AND is_active = 1",
            (agent_id,)
        ).fetchone()
        if not row:
            conn.close()
            return {"ok": True, "limit_type": None, "current_usage": {}}

        rpm_limit, daily_limit = row

        # RPM check: count requests in last 60 seconds
        rpm_row = conn.execute(
            "SELECT COUNT(*) FROM agent_usage_log WHERE agent_id = ? AND created_at >= datetime('now', '-60 seconds')",
            (agent_id,)
        ).fetchone()
        current_rpm = rpm_row[0] if rpm_row else 0

        if current_rpm >= rpm_limit:
            conn.close()
            return {
                "ok": False,
                "limit_type": "RPM",
                "current_usage": {"requests_last_60s": current_rpm, "rpm_limit": rpm_limit},
            }

        # Daily spend check
        daily_row = conn.execute(
            "SELECT COALESCE(SUM(cost), 0.0) FROM agent_usage_log WHERE agent_id = ? AND date(created_at) = date('now')",
            (agent_id,)
        ).fetchone()
        current_daily = daily_row[0] if daily_row else 0.0

        if current_daily + estimated_cost > daily_limit:
            conn.close()
            return {
                "ok": False,
                "limit_type": "DAILY_SPEND",
                "current_usage": {"daily_spent": current_daily, "daily_limit": daily_limit, "estimated_cost": estimated_cost},
            }

        conn.close()
        return {
            "ok": True,
            "limit_type": None,
            "current_usage": {"requests_last_60s": current_rpm, "rpm_limit": rpm_limit, "daily_spent": current_daily, "daily_limit": daily_limit},
        }
    except Exception:
        conn.close()
        return {"ok": True, "limit_type": None, "current_usage": {}}


def log_usage(agent_id: str, request_id: str, cost: float = 0.0) -> None:
    """Log a usage entry for rate tracking."""
    conn = _get_usage_db()
    conn.execute(
        "INSERT INTO agent_usage_log (agent_id, request_id, cost) VALUES (?, ?, ?)",
        (agent_id, request_id, cost)
    )
    conn.commit()
    conn.close()


def _resolve_api_key_to_agent(api_key: str) -> str | None:
    """
    Validate API key and return mapped agent_id.
    Uses SHA-256 hash lookup. Returns None if invalid/inactive.
    Updates last_used_at on success.
    """
    import hashlib
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    conn = _get_billing_db()
    try:
        row = conn.execute(
            "SELECT agent_id FROM api_keys WHERE key_hash = ? AND is_active = 1",
            (key_hash,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE api_keys SET last_used_at = datetime('now') WHERE key_hash = ?",
                (key_hash,)
            )
            conn.commit()
            conn.close()
            return row[0]
        conn.close()
        return None
    except Exception:
        conn.close()
        return None


def billing_create_api_key(agent_id: str, name: str = "default") -> str:
    """
    Create a new API key for an agent. Returns the raw key (shown once).
    Auto-creates agent account if not exists.
    """
    import hashlib, secrets
    raw_key = "a2a_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    conn = _get_billing_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO agent_accounts (agent_id, balance, reserved) VALUES (?, 10.0, 0.0)",
            (agent_id,)
        )
        conn.execute(
            "INSERT INTO api_keys (key_hash, agent_id, name) VALUES (?, ?, ?)",
            (key_hash, agent_id, name)
        )
        conn.commit()
        conn.close()
        return raw_key
    except Exception as e:
        conn.close()
        raise

# ─── LOGGING ───
LOG_DIR = Path("/root/.hermes/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "inference-router.jsonl"

logger = logging.getLogger("inference-router")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.FileHandler(LOG_DIR / "inference-router.log")
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(_handler)

# ─── ASYNC LOG BUFFER ───
_log_buffer: list[str] = []
_LOG_BUFFER_SIZE = 5  # Flush alle 5 Einträge

def _log_entry(entry: dict):
    """Buffer log entries and flush periodically (non-blocking)."""
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    _log_buffer.append(json.dumps(entry, default=str))
    if len(_log_buffer) >= _LOG_BUFFER_SIZE:
        _flush_log_buffer()

def _flush_log_buffer():
    """Flush buffered log entries to disk."""
    global _log_buffer
    if not _log_buffer:
        return
    try:
        with open(LOG_FILE, "a") as f:
            f.write("\n".join(_log_buffer) + "\n")
    except Exception:
        pass  # Logging darf den Request nicht bremsen
    _log_buffer = []

# ─── PROVIDER CONFIG (Single-Provider Mode: DeepSeek only) ───
PROVIDER_WHITELIST = {
    "deepseek": {
        "model_id": "deepseek/deepseek-chat",
        "base_url": "https://openrouter.ai/api/v1",
        "timeout_s": 60,
        "connect_timeout_s": 5,
        "primary": True,
    },
}

# ─── SAFETY LIMITS (hardcoded) ───
MAX_TOKENS_HARD = 2048           # hart absolute Obergrenze
MAX_TOKENS_DEFAULT = 512         # default wenn nicht angegeben
MAX_COST_HARD = 0.05             # hart absolute Kostenobergrenze in $
RETRY_MAX = 0                    # KEIN Retry — Single-Provider, kein Fallback
REQUEST_TIMEOUT_S = 65           # Gesamttimeout (60s provider + 5s overhead)

# Get OpenRouter API key
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
if not OPENROUTER_API_KEY:
    # Fallback: try to load from .env file directly
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line.startswith("OPENROUTER_API_KEY="):
                    OPENROUTER_API_KEY = line.split("=", 1)[1].strip()
                    break

router = APIRouter(prefix="/v1", tags=["Inference"])

# ─── DEMAND PRIORITY LAYER ───

def calculate_demand_score(
    body: dict,
    pricing_tier: str,
) -> float:
    """
    Calculate a demand priority score (0.0 - 1.0) for an A2A request.

    Scoring:
        Request type (inferred from body structure):
            workflow:    +0.4  (body has "workflow" key with list)
            auto-execute: +0.3  (body has "task" key with "required_capability")
            execute:     +0.2  (body has "task" key, no "required_capability")
        Pricing tier:
            high:   +0.2
            medium: +0.1
            simple: +0.05
    """
    score = 0.0

    # Detect request type from body structure
    if isinstance(body.get("workflow"), list) and len(body["workflow"]) > 0:
        score += 0.4  # workflow
    elif isinstance(body.get("task"), dict):
        task = body["task"]
        if task.get("required_capability"):
            score += 0.3  # auto-execute
        else:
            score += 0.2  # direct execute
    else:
        score += 0.2  # fallback: treat as direct execute

    # Pricing tier bonus
    tier_scores = {"high": 0.2, "medium": 0.1, "simple": 0.05}
    score += tier_scores.get(pricing_tier, 0.05)

    return min(score, 1.0)


# ─── GLOBAL HTTP CLIENT (Connection Reuse + Keep-Alive) ───
# Wird einmal beim Import erstellt und für alle Requests wiederverwendet.
# Eliminiert TCP-Handshake + TLS-Overhead bei jedem Request.
_http_client: httpx.AsyncClient | None = None

async def _get_http_client() -> httpx.AsyncClient:
    """Return global httpx.AsyncClient with connection pooling."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=5.0,
                read=60.0,
                write=10.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5,
                keepalive_expiry=30.0,
            ),
            http2=False,
        )
    return _http_client


def _x402_check_inference(request: Request) -> Optional[JSONResponse]:
    """Check if request is authorized (internal key, API key, or free tier)."""
    # Internal bypass
    if request.headers.get("X-Internal-Key") == INTERNAL_KEY:
        return None

    # API Key check
    api_key = request.headers.get("X-Api-Key", "")
    if api_key:
        info = verify_api_key(api_key)
        if info and info["remaining"] >= 5:  # inference costs 5 credits
            ip = get_client_ip(request)
            use_api_key(api_key, "inference", ip)
            return None
        return JSONResponse(
            status_code=402,
            content={"error": "Insufficient credits", "message": "Inference costs 5 credits. Buy more at /pricing"},
        )

    # Free tier: 5 inference calls per day
    ip = get_client_ip(request)
    remaining = get_remaining(ip)
    if remaining > 0:
        consume(ip)
        return None

    return JSONResponse(
        status_code=429,
        content={"error": "Free tier exceeded", "message": "Use X-Api-Key header or X-Internal-Key for testing"},
    )


async def _call_openrouter(model_id: str, prompt: str, max_tokens: int, timeout_s: int) -> dict:
    """Call OpenRouter API. Returns dict with response, tokens, cost, latency."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://178.105.35.170",
        "X-Title": "Inference Router",
    }
    # Payload minimization: nur required fields
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }

    start = time.monotonic()
    client = await _get_http_client()
    resp = await client.post(url, headers=headers, json=payload)
    latency_ms = int((time.monotonic() - start) * 1000)

    if resp.status_code != 200:
        return {
            "success": False,
            "error": f"HTTP {resp.status_code}: {resp.text[:500]}",
            "latency_ms": latency_ms,
            "model_id": model_id,
        }

    data = resp.json()
    usage = data.get("usage", {})
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

    # OpenRouter gibt Usage-Cost im Header oder Body zurück
    # Wir schätzen die Kosten basierend auf den Tokens (nach Verifikation)
    # Deepseek: ~$0.0002/1K, OpenAI: ~$0.0015/1K
    estimated_cost = _estimate_cost(model_id, total_tokens)

    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        content = str(data)

    return {
        "success": True,
        "response": content,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": estimated_cost,
        "latency_ms": latency_ms,
        "model_id": model_id,
    }


def _estimate_cost(model_id: str, total_tokens: int) -> float:
    """Estimate cost based on known pricing."""
    # Rates per 1K tokens (input+output combined average)
    rates = {
        "deepseek": 0.0002,
        "openai": 0.0015,
    }
    # Determine provider from model_id
    provider = "deepseek" if "deepseek" in model_id.lower() else "openai"
    rate = rates.get(provider, 0.0005)
    return round((total_tokens / 1000) * rate, 6)


@router.post("/inference")
async def inference(request: Request):
    """
    POST /v1/inference

    Minimaler Inference Endpoint mit statischem Routing.
    Single-Provider Mode: DeepSeek only, kein Fallback.
    """
    start_total = time.monotonic()
    request_id = generate_request_id()

    # Auth check
    auth = _x402_check_inference(request)
    # If request has valid A2A API key, inject agent_id into body.meta
    # and skip x402 billing (A2A billing handles its own charges)
    _a2a_api_key = request.headers.get("X-API-KEY", "")
    _a2a_agent_id = None
    if _a2a_api_key:
        _a2a_agent_id = _resolve_api_key_to_agent(_a2a_api_key)
        if _a2a_agent_id:
            logger.info(f"A2A_AUTH_SUCCESS agent_id={_a2a_agent_id} request_id={request_id}")
            # Skip x402 auth for A2A requests (A2A billing is separate)
            auth = None
        else:
            logger.warning(f"A2A_AUTH_FAIL key={_a2a_api_key[:8]}... request_id={request_id}")
            return JSONResponse(
                status_code=401,
                content={"error": "Unauthorized", "message": "Invalid X-API-KEY"},
            )
    if auth:
        auth_error_type = ErrorType.NONE
        auth_http_status = 200
        # Klassifiziere Auth-Fehler basierend auf Response
        auth_body = auth.body.decode() if hasattr(auth, 'body') else ""
        if "rate" in auth_body.lower() or "429" in str(auth.status_code):
            auth_error_type = ErrorType.RATE_LIMIT
            auth_http_status = 429
        elif "credit" in auth_body.lower() or "402" in str(auth.status_code):
            auth_error_type = ErrorType.AUTH_ERROR
            auth_http_status = 402
        elif "exceeded" in auth_body.lower():
            auth_error_type = ErrorType.RATE_LIMIT
            auth_http_status = 429

        # Log auth rejection
        log_entry = build_observability_log(
            request_id=request_id,
            provider_used=None,
            model_used=None,
            latency_ms=int((time.monotonic() - start_total) * 1000),
            cost_estimate=0,
            tokens_used=0,
            prompt_length=0,
            success=False,
            error_type=auth_error_type,
            status=determine_status(False, auth_error_type),
            error_detail=auth_body[:300],
            http_status=auth_http_status,
            preferred_model="unknown",
        )
        _log_entry(log_entry)
        return auth

    # Parse body
    try:
        body = await request.json()
    except Exception as e:
        log_entry = build_observability_log(
            request_id=request_id,
            provider_used=None,
            model_used=None,
            latency_ms=int((time.monotonic() - start_total) * 1000),
            cost_estimate=0,
            tokens_used=0,
            prompt_length=0,
            success=False,
            error_type=ErrorType.VALIDATION_ERROR,
            status=RequestStatus.VALIDATION_ERROR,
            error_detail=f"JSON parse error: {str(e)[:200]}",
            http_status=400,
            preferred_model="unknown",
        )
        _log_entry(log_entry)
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    prompt = body.get("prompt", "").strip()
    # Prompt minimization: collapse whitespace, trim to max
    prompt = re.sub(r"\s+", " ", prompt).strip()
    if not prompt:
        log_entry = build_observability_log(
            request_id=request_id,
            provider_used=None,
            model_used=None,
            latency_ms=int((time.monotonic() - start_total) * 1000),
            cost_estimate=0,
            tokens_used=0,
            prompt_length=0,
            success=False,
            error_type=ErrorType.VALIDATION_ERROR,
            status=RequestStatus.VALIDATION_ERROR,
            error_detail="Missing 'prompt' field",
            http_status=400,
            preferred_model=body.get("preferred_model", "unknown"),
        )
        _log_entry(log_entry)
        return JSONResponse(status_code=400, content={"error": "Missing 'prompt' field"})

    # Sanitize inputs
    preferred_model = body.get("preferred_model", "deepseek").lower()
    if preferred_model not in ("deepseek", "openai"):
        preferred_model = "deepseek"

    max_tokens = min(int(body.get("max_tokens", MAX_TOKENS_HARD)), MAX_TOKENS_HARD)
    max_cost = min(float(body.get("max_cost", MAX_COST_HARD)), MAX_COST_HARD)

    # ─── DYNAMIC PRICING LAYER ───
    def _resolve_price(request_body: dict, a2a_agent_id: str | None = None) -> tuple[float, str]:
        """
        Determine price per request based on A2A context.
        Returns (price, complexity).
        """
        base_price = 0.02
        meta = request_body.get("meta", {})
        if isinstance(meta, dict) and (meta.get("agent_id") or a2a_agent_id):
            task = request_body.get("task", {})
            complexity = task.get("complexity", "simple") if isinstance(task, dict) else "simple"
            if complexity == "high":
                return base_price * 4, complexity
            if complexity == "medium":
                return base_price * 2, complexity
            return base_price, complexity
        return base_price, "simple"

    price, resolved_complexity = _resolve_price(body, _a2a_agent_id)
    agent_for_log = _a2a_agent_id or (body.get("meta", {}).get("agent_id", "none") if isinstance(body.get("meta"), dict) else "none")
    logger.info(f"PRICING_RESOLVED price={price:.4f} complexity={resolved_complexity} agent_id={agent_for_log}")
    # Override max_cost with dynamic price for A2A requests
    max_cost = min(max_cost, price)

    # ─── INJECT A2A AGENT_ID FROM API KEY (set during auth phase) ───
    if _a2a_agent_id:
        if "meta" not in body or not isinstance(body["meta"], dict):
            body["meta"] = {}
        body["meta"]["agent_id"] = _a2a_agent_id

    # ─── A2A DETECTION (before routing, non-blocking) ───
    def _is_a2a_request(body: dict) -> bool:
        """Return True if request.meta.agent_id exists (A2A protocol)."""
        meta = body.get("meta")
        return isinstance(meta, dict) and "agent_id" in meta

    is_a2a = _is_a2a_request(body)
    if is_a2a:
        agent_id = body["meta"]["agent_id"]
        logger.info(f"A2A_REQUEST_DETECTED agent_id={agent_id} request_id={request_id}")

    # ─── A2A PRE-EXECUTION USAGE CHECK (before billing) ───
    if is_a2a:
        usage_check = check_usage_limits(agent_id, estimated_cost=price)
        if not usage_check["ok"]:
            limit_type = usage_check["limit_type"]
            current = usage_check["current_usage"]
            logger.warning(
                f"{limit_type}_EXCEEDED agent_id={agent_id} "
                f"current={current} request_id={request_id}"
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": f"{limit_type} limit exceeded",
                    "limit_type": limit_type,
                    "current_usage": current,
                },
            )

    # ─── EXECUTION CONTINUITY LAYER ───
    # Determine execution mode: internal orchestration vs external entry
    is_internal_execution = (
        request.headers.get("X-INTERNAL-ORIGIN") == "service_registry"
        or (
            isinstance(body.get("meta"), dict)
            and body["meta"].get("internal_call") is True
        )
    )
    _execution_mode = "internal" if is_internal_execution else "external"
    _demand_scope = "skipped_internal" if is_internal_execution else "external_only"
    logger.info(
        f"EXECUTION_MODE = {_execution_mode} "
        f"DEMAND_SCORE_SCOPE = {_demand_scope} "
        f"agent_id={agent_id} request_id={request_id}"
    )

    # ─── A2A PRE-EXECUTION DEMAND SCORE CHECK (before value flow) ───
    # SKIPPED for internal execution — only external requests are demand-gated
    if is_a2a and not is_internal_execution:
        _demand_score = calculate_demand_score(body, resolved_complexity)
        if _demand_score < 0.3:
            logger.warning(
                f"DEMAND_SCORE_CALCULATED value={_demand_score:.2f} REJECTED "
                f"agent_id={agent_id} tier={resolved_complexity} request_id={request_id}"
            )
            return JSONResponse(
                status_code=403,
                content={
                    "error": "LOW_DEMAND_REQUEST",
                    "demand_score": round(_demand_score, 2),
                },
            )
        logger.info(
            f"DEMAND_SCORE_CALCULATED value={_demand_score:.2f} ACCEPTED "
            f"agent_id={agent_id} tier={resolved_complexity} request_id={request_id}"
        )

    # ─── A2A PRE-EXECUTION VALUE FLOW CHECK (before billing) ───
    # SKIPPED for internal execution — only external requests are economically gated
    if is_a2a and not is_internal_execution:
        _tier_cost_estimates = {"simple": 0.00002, "medium": 0.00003, "high": 0.00005}
        _expected_cost = _tier_cost_estimates.get(resolved_complexity, 0.00002)
        _expected_revenue = price
        _expected_profit = _expected_revenue - _expected_cost
        if _expected_profit <= 0:
            logger.warning(
                f"VALUE_FLOW_CHECK BLOCKED agent_id={agent_id} "
                f"expected_profit={_expected_profit:.6f} "
                f"tier={resolved_complexity} request_id={request_id}"
            )
            return JSONResponse(
                status_code=402,
                content={
                    "error": "UNVIABLE_REQUEST",
                    "expected_profit": round(_expected_profit, 6),
                    "reason": "Request is not economically viable",
                },
            )
        logger.info(
            f"VALUE_FLOW_CHECK PASSED agent_id={agent_id} "
            f"expected_profit={_expected_profit:.6f} "
            f"tier={resolved_complexity} request_id={request_id}"
        )

    # ─── A2A PRE-EXECUTION BILLING HOOK ───
    a2a_reserve_result = None
    if is_a2a:
        # Use dynamic price as max_cost for reservation
        reserve_amount = price
        a2a_reserve_result = billing_reserve(agent_id, reserve_amount)
        if not a2a_reserve_result["ok"]:
            logger.warning(f"A2A_BILLING_RESERVE_FAILED agent_id={agent_id} error={a2a_reserve_result['error']}")
            return JSONResponse(
                status_code=402,
                content={
                    "error": "A2A billing reserve failed",
                    "detail": a2a_reserve_result["error"],
                    "agent_id": agent_id,
                },
            )
        logger.info(f"A2A_BILLING_RESERVED agent_id={agent_id} reserved={a2a_reserve_result['reserved']}")

    # ─── ROUTING DECISION (Observability) ───
    routing_decision = routing_decision_function(
        prompt=prompt,
        preferred_model=preferred_model,
        max_cost=max_cost,
    )

    # Single-Provider Routing: nur DeepSeek, kein Fallback
    routing_order = [routing_decision["provider"]]

    last_error = None
    total_latency_ms = 0
    model_used = None
    tokens_used = 0
    response_text = ""
    estimated_cost = 0.0
    retries = 0
    success = False
    failure_reason = None
    provider_response = None
    provider_error_type = ErrorType.NONE
    charge_result = None  # A2A billing result, initialized for post-execution hook

    for provider_name in routing_order[: RETRY_MAX + 1]:
        provider = PROVIDER_WHITELIST.get(provider_name)
        if not provider:
            failure_reason = f"Provider '{provider_name}' not in whitelist"
            last_error = failure_reason
            provider_error_type = ErrorType.CONFIG_ERROR
            continue

        model_id = provider["model_id"]
        timeout_s = provider["timeout_s"]

        result = await _call_openrouter(model_id, prompt, max_tokens, timeout_s)
        total_latency_ms += result["latency_ms"]

        if result["success"]:
            estimated_cost = result["estimated_cost"]
            if estimated_cost > max_cost:
                failure_reason = f"Cost ${estimated_cost:.6f} exceeds max_cost ${max_cost:.4f}"
                last_error = failure_reason
                retries += 1
                provider_error_type = ErrorType.COST_EXCEEDED
                continue

            model_used = provider_name
            tokens_used = result["total_tokens"]
            response_text = result["response"]
            provider_response = result
            success = True

            # ─── A2A POST-EXECUTION BILLING HOOK ───
            if is_a2a:
                actual_cost = result["estimated_cost"]
                charge_result = billing_charge(agent_id, actual_cost, request_id)
                # Log usage for rate tracking
                log_usage(agent_id, request_id, actual_cost)
                logger.info(
                    f"A2A_BILLING_CHARGED agent_id={agent_id} "
                    f"actual_cost={actual_cost:.6f} "
                    f"status={charge_result.get('payment_status')} "
                    f"request_id={request_id}"
                )
            break
        else:
            last_error = result["error"]
            failure_reason = result["error"]
            retries += 1
            provider_error_type = classify_error(result["error"])

    total_elapsed_ms = int((time.monotonic() - start_total) * 1000)

    # ─── OBSERVABILITY LOG ───
    log_entry = build_observability_log(
        request_id=request_id,
        provider_used=model_used or (routing_order[0] if routing_order else None),
        model_used=provider_response.get("model_id") if provider_response else None,
        latency_ms=total_elapsed_ms,
        cost_estimate=estimated_cost,
        tokens_used=tokens_used,
        prompt_length=len(prompt),
        success=success,
        error_type=provider_error_type if not success else ErrorType.NONE,
        status=determine_status(success, provider_error_type),
        error_detail=failure_reason,
        http_status=200 if success else 503,
        preferred_model=preferred_model,
    )
    # Routing Decision Logging
    log_entry["routing_decision"] = {
        "task_type": routing_decision["task_type"],
        "decision_reason": routing_decision["decision_reason"],
        "estimated_cost": routing_decision["estimated_cost"],
        "estimated_latency_ms": routing_decision["estimated_latency_ms"],
        "task_confidence": routing_decision["confidence"],
    }
    _log_entry(log_entry)

    if not success:
        return JSONResponse(
            status_code=503,
            content={
                "error": "All providers failed",
                "last_error": last_error,
                "model_used": None,
                "tokens_used": 0,
                "estimated_cost": estimated_cost,
                "response": None,
                "latency_ms": total_elapsed_ms,
            },
        )

    response_payload = {
        "model_used": model_used,
        "tokens_used": tokens_used,
        "estimated_cost": estimated_cost,
        "response": response_text,
        "latency_ms": total_elapsed_ms,
    }

    # ─── A2A RESPONSE EXTENSION ───
    if is_a2a:
        response_payload["payment_status"] = charge_result.get("payment_status", "unknown")
        response_payload["cost_usd"] = charge_result.get("charged", estimated_cost)
        response_payload["pricing"] = {
            "base_price": 0.02,
            "final_price": price,
            "complexity": resolved_complexity,
        }

    return response_payload


@router.get("/inference/health")
async def inference_health():
    """Health check for inference router."""
    return {
        "status": "ok",
        "providers": {k: v["primary"] for k, v in PROVIDER_WHITELIST.items()},
        "max_tokens": MAX_TOKENS_HARD,
        "max_cost": MAX_COST_HARD,
        "retry_max": RETRY_MAX,
        "openrouter_configured": bool(OPENROUTER_API_KEY),
    }
