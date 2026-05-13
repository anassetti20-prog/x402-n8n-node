"""
x402 A2A (Agent-to-Agent) Server — Google A2A Protocol Implementation
Runs alongside the x402 REST API and MCP Server.
Makes all 47 x402 services available as A2A Agent Skills.

Protocol: JSON-RPC 2.0 over HTTP (A2A Spec)
Port: 8083
"""
import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

# ── Add x402 API to path ──────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services import SERVICE_REGISTRY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("x402_A2A")

app = FastAPI(title="x402 A2A Server", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── A2A Commerce — Agent-to-Agent Payment ──────────────────────────
import purchase_system as ps
WALLET_ADDR = os.getenv("WALLET_ADDRESS", "0xeB262928D55A92f2EAac946807CeC4d80E9EdD6B")
A2A_INTERNAL_KEY = os.getenv("INTERNAL_KEY", "hermes-mcp-internal-v1")

# ── A2A Types ─────────────────────────────────────────────────────────────────
AGENT_CARD = {
    "name": "x402 Multi-Service Agent",
    "description": "47 AI services via x402 pay-per-use protocol on Base chain (USDC)",
    "url": "http://178.105.35.170:8083",
    "provider": {
        "organization": "x402",
        "url": "http://178.105.35.170:8080",
    },
    "version": "1.0.0",
    "capabilities": {
        "skills": {},
        "authentication": [],
        "streaming": False,
        "push_notifications": False,
    },
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
}

# Map all x402 services as A2A Agent Skills
SKILLS = {}
for sid, svc in SERVICE_REGISTRY.items():
    SKILLS[sid] = {
        "name": svc["name"],
        "description": svc.get("desc", svc["name"]),
        "price_usdc": svc["price"],
        "parameters": svc.get("params", []),
    }

AGENT_CARD["capabilities"]["skills"] = SKILLS


# ── JSON-RPC 2.0 Helpers ──────────────────────────────────────────────────────
def rpc_error(code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data:
        err["data"] = data
    return {"jsonrpc": "2.0", "error": err}


def rpc_success(result, request_id=None) -> dict:
    resp = {"jsonrpc": "2.0", "result": result}
    if request_id is not None:
        resp["id"] = request_id
    return resp


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/a2a/agent-card")
@app.get("/.well-known/agent-card")
async def get_agent_card():
    return AGENT_CARD

# ── Agent-to-Agent Commerce Endpoints ────────────────────────────────

@app.post("/a2a/register")
async def a2a_register(request: Request):
    """Register an AI agent automatically. Returns API key + 10 free credits."""
    body = await request.json() if request.headers.get("content-type","").startswith("application/json") else {}
    agent_name = body.get("agent_name", body.get("name", "a2a-agent"))
    agent_id = body.get("agent_id", agent_name.replace(" ", "-").lower())
    email = f"{agent_id}@a2a.x402.ai"
    result = ps.register(email)
    if "error" in result:
        if "already" in str(result.get("error","")):
            result = {"api_key": result.get("api_key",""), "agent_id": agent_id}
    return {
        "agent_id": agent_id,
        **result,
        "a2a_endpoints": {
            "rpc": "POST / or /rpc",
            "register": "POST /a2a/register",
            "purchase": "POST /a2a/purchase",
            "card": "GET /.well-known/agent-card",
        },
        "instructions": "Send X-API-Key: <key> header with every A2A request"
    }

@app.post("/a2a/purchase")
async def a2a_purchase(request: Request):
    """AI agent purchases credits autonomously. Send USDC or use API key."""
    body = await request.json() if request.headers.get("content-type","").startswith("application/json") else {}
    api_key = request.headers.get("X-API-Key", body.get("api_key", ""))
    bundle = body.get("bundle", "starter")
    if api_key:
        return ps.recharge(api_key, bundle)
    return {
        "payment_required": True,
        "bundle": bundle,
        "price_usd": ps.BUNDLES.get(bundle, {}).get("price_usd", 5.0),
        "wallet": WALLET_ADDR,
        "chain": "Base (8453)",
        "instructions": f"Send USDC on Base to {WALLET_ADDR} with memo containing your agent ID"
    }

@app.get("/a2a/status")
async def a2a_status():
    """A2A system status for agent commerce."""
    total = len(SERVICE_REGISTRY)
    premium = sum(1 for s in SERVICE_REGISTRY.values() if s["price"] >= 0.10)
    return {
        "version": "2.0.0",
        "protocol": "Google A2A v1.0",
        "total_services": total,
        "premium_services": premium,
        "min_price": min(s["price"] for s in SERVICE_REGISTRY.values()),
        "max_price": max(s["price"] for s in SERVICE_REGISTRY.values()),
        "agent_card": "/.well-known/agent-card",
        "register": "POST /a2a/register",
        "purchase": "POST /a2a/purchase",
        "rpc": "POST /rpc",
        "payment_token": "USDC on Base",
        "wallet": WALLET_ADDR,
        "halal_compliant": True,
        "pricing_bundles": {k: v["desc"] for k, v in ps.BUNDLES.items()},
    }


@app.post("/rpc")
@app.post("/")
async def handle_rpc(request: Request):
    """Main JSON-RPC 2.0 endpoint for A2A."""
    try:
        body = await request.json()
    except Exception:
        return rpc_error(-32700, "Parse error")

    req_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params", {})

    if method == "a2a.send_message":
        return await handle_send_message(params, req_id)
    elif method == "a2a.get_task":
        return await handle_get_task(params, req_id)
    elif method == "a2a.cancel_task":
        return rpc_error(-32001, "Task cancellation not supported", req_id)
    elif method == "rpc.discover":
        return rpc_success({
            "agent_card_url": "/.well-known/agent-card",
            "methods": [
                "a2a.send_message",
                "a2a.get_task",
                "rpc.discover",
            ],
            "specification": "https://a2a-protocol.org",
        }, req_id)
    else:
        return rpc_error(-32601, f"Method not found: {method}", req_id)


async def handle_send_message(params, req_id):
    """Execute an x402 service via A2A send_message. Includes A2A commerce payment verification."""
    session_id = params.get("sessionId", "")
    message = params.get("message", {})
    parts = message.get("parts", [])
    metadata = params.get("metadata", {})

    # Extract which service to call from metadata or message text
    service_id = metadata.get("service_id") or metadata.get("x-service-id", "")

    # ── A2A Commerce: Verify Payment ─────────────────────────────────────
    # AI agents must send X-API-Key header or have payment in metadata
    # If no payment, we still process but track it (free-tier model)
    api_key = metadata.get("api_key", "")
    agent_paid = False
    if api_key:
        key_info = ps.verify_api_key(api_key)
        if key_info and key_info["remaining"] > 0:
            agent_paid = True

    # Extract parameters from parts or metadata
    call_params = {}
    for part in parts:
        if part.get("type") == "text":
            text = part.get("text", "")
            # Allow JSON in text content
            try:
                extra = json.loads(text)
                if isinstance(extra, dict):
                    call_params.update(extra)
            except json.JSONDecodeError:
                call_params["input"] = text

    call_params.update(metadata.get("params", {}))

    # Find and call the service
    if service_id not in SERVICE_REGISTRY:
        available = ", ".join(sorted(SERVICE_REGISTRY.keys()))
        return rpc_success({
            "id": session_id or f"x402-{datetime.now(timezone.utc).timestamp():.0f}",
            "status": {
                "state": "failed",
                "message": {"parts": [{
                    "type": "text",
                    "text": f"Unknown service: {service_id}. Available: {available}"
                }]},
            },
            "artifacts": []
        }, req_id)

    svc = SERVICE_REGISTRY[service_id]
    func = svc["func"]

    try:
        result = await func(**call_params)
        result_text = json.dumps(result, indent=2) if not isinstance(result, str) else result
        return rpc_success({
            "id": session_id or f"x402-{datetime.now(timezone.utc).timestamp():.0f}",
            "status": {
                "state": "completed",
                "message": {"parts": [{"type": "text", "text": result_text}]},
            },
            "artifacts": []
        }, req_id)
    except TypeError as e:
        # Parameter mismatch — try with only valid params
        import inspect
        sig = inspect.signature(func)
        valid_params = set(sig.parameters.keys())
        filtered = {k: v for k, v in call_params.items() if k in valid_params}
        result = await func(**filtered)
        result_text = json.dumps(result, indent=2) if not isinstance(result, str) else result
        return rpc_success({
            "id": session_id or f"x402-{datetime.now(timezone.utc).timestamp():.0f}",
            "status": {
                "state": "completed",
                "message": {"parts": [{"type": "text", "text": result_text}]},
            },
            "artifacts": []
        }, req_id)
    except Exception as e:
        return rpc_success({
            "id": session_id or f"x402-{datetime.now(timezone.utc).timestamp():.0f}",
            "status": {
                "state": "failed",
                "message": {"parts": [{"type": "text", "text": f"Error: {str(e)}"}]},
            },
            "artifacts": []
        }, req_id)


async def handle_get_task(params, req_id):
    """Get task status — simple passthrough for synchronous tasks."""
    task_id = params.get("id", "")
    return rpc_success({
        "id": task_id,
        "status": {"state": "completed"},
        "artifacts": []
    }, req_id)


# ── Start ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("=" * 60)
    log.info(f"x402 A2A Server — {len(SERVICE_REGISTRY)} agent skills")
    for sid, svc in sorted(SERVICE_REGISTRY.items()):
        log.info(f"  [{svc['name']}] /rpc ? service_id={sid}")
    log.info("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8083)
