"""
x402 Multi-Service API
Main FastAPI application with x402 micropayment integration.
Offers: Halal Screening, Web Search, Code Analysis, Data Processing, Translation, Text Generation
"""

import os
import time
from typing import Optional
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from .config import (
    API_HOST,
    API_PORT,
    WALLET_ADDRESS,
    WALLET_PRIVATE_KEY,
    PRICE_USDC,
    BASE_CHAIN_ID,
    USDC_CONTRACT_ADDRESS,
)
from .x402_protocol import (
    get_x402_headers,
    verify_payment,
    create_wallet,
    get_wallet_balance,
)
from .halal_check import check_halal, KNOWN_HALAL, HALAL_CRITERIA

from purchase_system import (
    register as ps_register,
    get_credits as ps_credits,
    recharge as ps_recharge,
    confirm_recharge as ps_confirm,
    BUNDLES as PS_BUNDLES,
    get_status as ps_status,
    init_db as ps_init_db,
)

app = FastAPI(
    title="x402 Multi-Service API",
    description="Pay-per-request AI services via USDC micropayments on Base. Halal Screening, Web Search, Code Analysis, Data Processing, Translation, Text Generation.",
    version="2.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (for downloads)
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# In-memory request tracking
_request_count = 0
_paid_sessions: dict = {}

# Include inference router FIRST (before generic /{service_id} catch-all)
from .inference_router import router as inference_router
app.include_router(inference_router)

# Include workflow endpoint (before generic /{service_id} catch-all)
from .workflow_endpoint import router as workflow_router
app.include_router(workflow_router)

# Include service discovery registry (before generic /{service_id} catch-all)
from .service_registry import router as service_registry_router
app.include_router(service_registry_router)

# Include inter-agent execution router (before generic /{service_id} catch-all)
from .service_registry import agent_router as agent_execution_router
app.include_router(agent_execution_router)

# Include well-known discovery router (before generic /{service_id} catch-all)
from .service_registry import well_known_router
app.include_router(well_known_router)

# Include A2A manifest router (before generic /{service_id} catch-all)
from .service_registry import a2a_manifest_router
app.include_router(a2a_manifest_router)

# Include economics router
from .service_registry import economics_router
app.include_router(economics_router)

# Include analytics router
from .service_registry import analytics_router
app.include_router(analytics_router)

# Include execute API router (before generic catch-all)
from .execute_api import execute_router
app.include_router(execute_router)

# Serve landing page
from fastapi.responses import HTMLResponse
_landing_path = Path(__file__).parent / "templates" / "landing_page.html"

@app.get("/v1/execute/page", response_class=HTMLResponse, include_in_schema=False)
async def landing_page():
    if _landing_path.exists():
        return HTMLResponse(_landing_path.read_text())
    return HTMLResponse("<h1>HALIMA Execution API</h1><p>See /docs for API documentation.</p>")

# Include x402 service router (has generic /{service_id} catch-all)
from .routes import router as service_router
app.include_router(service_router)


@app.on_event("startup")
async def startup():
    """Startup tasks."""
    # Initialize purchase system DB
    from purchase_system import init_db
    init_db()

    print(f"\n{'='*60}")
    print("🚀 x402 Multi-Service API gestartet")
    print(f"{'='*60}")
    print(f"{'='*60}")
    print(f"📡 Server: http://{API_HOST}:{API_PORT}")
    print(f"💲 Preis: ${PRICE_USDC} USDC (Halal) / $0.01-$0.05 (Services)")
    print(f"⛓️  Chain: Base (Chain ID: {BASE_CHAIN_ID})")
    print(f"🪙 USDC: {USDC_CONTRACT_ADDRESS}")
    print(f"💳 Wallet: {WALLET_ADDRESS or '❌ NICHT KONFIGURIERT'}")
    print(f"📦 Services: Halal-Check, Web Search, Code Analysis, Data Processing, Translation, Text Generation")
    print(f"📥 Download: /static/x402-halal-api.tar.gz")
    print(f"{'='*60}\n")


@app.get("/")
async def root():
    """API root - shows all available services."""
    return {
        "name": "x402 Multi-Service API",
        "version": "2.0.0",
        "wallet": WALLET_ADDRESS,
        "payment": {
            "price_usdc": PRICE_USDC,
            "chain": "Base",
            "chain_id": BASE_CHAIN_ID,
            "token": "USDC",
            "token_contract": USDC_CONTRACT_ADDRESS,
            "recipient": WALLET_ADDRESS or "Not configured - use /wallet/create",
        },
        "services": [
            {
                "id": "halal-check",
                "name": "Halal Screening",
                "endpoint": "GET /halal-check?symbol=BTC",
                "price": PRICE_USDC,
                "description": "Check cryptocurrency Sharia compliance",
            },
            {
                "id": "search",
                "name": "Web Search",
                "endpoint": "POST /v1/search",
                "price": 0.01,
                "description": "Search the web for information",
            },
            {
                "id": "analyze-code",
                "name": "Code Analysis",
                "endpoint": "POST /v1/analyze-code",
                "price": 0.05,
                "description": "Analyze source code for bugs, security issues",
            },
            {
                "id": "process-data",
                "name": "Data Processing",
                "endpoint": "POST /v1/process-data",
                "price": 0.02,
                "description": "Transform, filter, validate structured data",
            },
            {
                "id": "translate",
                "name": "Translation",
                "endpoint": "POST /v1/translate",
                "price": 0.01,
                "description": "Translate text between languages",
            },
            {
                "id": "generate-text",
                "name": "Text Generation",
                "endpoint": "POST /v1/generate-text",
                "price": 0.02,
                "description": "Generate AI text in various styles",
            },
        ],
        "endpoints": {
            "GET /": "This page",
            "GET /health": "Health check",
            "GET /wallet": "Server wallet info",
            "GET /list": "All known halal/haram coins",
            "GET /llms.txt": "AI agent discovery file",
            "GET /llms-full.txt": "Full API documentation for AI agents",
            "GET /openapi.json": "OpenAPI 3.0 specification",
            "GET /static/x402-halal-api.tar.gz": "Download source code",
            "GET /v1/services": "All x402 services with pricing",
        },
        "download": "http://178.105.35.170:8080/static/x402-halal-api.tar.gz",
        "usage": {
            "total_requests": _request_count,
        },
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    wallet_balance = get_wallet_balance() if WALLET_ADDRESS else 0.0
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "wallet_configured": bool(WALLET_ADDRESS),
        "wallet_balance_usdc": wallet_balance,
        "total_requests": _request_count,
    }


@app.get("/wallet")
async def wallet_info():
    """Get server wallet information."""
    if not WALLET_ADDRESS:
        return {
            "configured": False,
            "message": "Keine Wallet konfiguriert. Verwende POST /wallet/create um eine zu erstellen.",
        }
    
    balance = get_wallet_balance()
    return {
        "configured": True,
        "address": WALLET_ADDRESS,
        "chain": "Base",
        "chain_id": BASE_CHAIN_ID,
        "rpc_url": "https://mainnet.base.org",
        "usdc_contract": USDC_CONTRACT_ADDRESS,
        "balance_usdc": balance,
        "price_per_request": PRICE_USDC,
    }


@app.post("/wallet/create")
async def wallet_create():
    """
    Create a new USDC wallet on Base blockchain.
    Returns the wallet address and private key.
    IMPORTANT: Store the private key securely!
    """
    wallet = create_wallet()
    
    # Save to .env for persistence
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    with open(env_path, "a") as f:
        f.write(f'\nWALLET_ADDRESS={wallet["address"]}\n')
        f.write(f'WALLET_PRIVATE_KEY={wallet["private_key"]}\n')
    
    # Reload config
    os.environ["WALLET_ADDRESS"] = wallet["address"]
    os.environ["WALLET_PRIVATE_KEY"] = wallet["private_key"]
    
    # Update module-level variables
    import app.config as cfg
    cfg.WALLET_ADDRESS = wallet["address"]
    cfg.WALLET_PRIVATE_KEY = wallet["private_key"]
    
    # Also update x402_protocol
    import app.x402_protocol as x402
    x402.WALLET_ADDRESS = wallet["address"]
    x402.WALLET_PRIVATE_KEY = wallet["private_key"]
    
    return {
        "success": True,
        "message": "✅ Wallet erfolgreich erstellt!",
        "wallet": {
            "address": wallet["address"],
            "private_key": wallet["private_key"],
            "chain": "Base",
            "chain_id": BASE_CHAIN_ID,
            "rpc_url": BASE_RPC_URL,
            "usdc_contract": USDC_CONTRACT_ADDRESS,
        },
        "next_steps": [
            f"Sende USDC auf Base an diese Adresse: {wallet['address']}",
            f"Alternativ: Kauthis auf Base Bridge (https://bridge.base.org/)",
            "Verwende GET /halal-check?symbol=BTC um die API zu testen (mit x402-Payment)",
        ],
        "warning": "⚠️ Private Key wird in .env gespeichert. Stelle sicher, dass der Server sicher ist!",
    }


@app.get("/list")
async def list_coins():
    """List all known halal/haram coins."""
    coins = {}
    for sym, data in KNOWN_HALAL.items():
        coins[sym.upper()] = {
            "name": data["name"],
            "halal": data["halal"],
            "confidence": data["confidence"],
        }
    return {
        "total_known": len(coins),
        "coins": coins,
        "criteria": HALAL_CRITERIA,
        "note": "Diese Liste ist nicht abschließend. Konsultiere immer einen Gelehrten.",
    }


@app.get("/llms.txt")
async def llms_txt():
    """AI agent discovery file (llms.txt format)."""
    path = Path(__file__).parent.parent / "llms.txt"
    if path.exists():
        return FileResponse(str(path), media_type="text/plain")
    return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/llms-full.txt")
async def llms_full_txt():
    """Full API documentation for AI agents."""
    path = Path(__file__).parent.parent / "llms-full.txt"
    if path.exists():
        return FileResponse(str(path), media_type="text/plain")
    return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/openapi.json")
async def openapi_json():
    """OpenAPI 3.0 specification for API discovery."""
    path = Path(__file__).parent.parent / "openapi.json"
    if path.exists():
        return FileResponse(str(path), media_type="application/json")
    return JSONResponse(status_code=404, content={"error": "Not found"})


@app.get("/halal-check")
async def halal_check(request: Request, symbol: Optional[str] = None):
    """
    Halal Screening Endpoint with x402 micropayments.
    
    Usage:
    1. GET /halal-check?symbol=BTC - with valid x402 payment
    2. Without payment: shows x402 headers for payment
    
    Payment: $0.01 USDC on Base to the server wallet
    Include header: X-402-Proof: <tx_hash>
    """
    global _request_count
    _request_count += 1
    
    # Validate symbol
    if not symbol or not symbol.strip():
        return JSONResponse(
            status_code=400,
            content={
                "error": "Symbol erforderlich",
                "usage": "GET /halal-check?symbol=BTC",
            },
        )
    
    symbol = symbol.strip().upper()
    
    # Check if wallet is configured
    if not WALLET_ADDRESS or not WALLET_PRIVATE_KEY:
        return JSONResponse(
            status_code=402,
            content={
                "error": "Server Wallet nicht konfiguriert",
                "message": "Bitte erstelle zuerst eine Wallet: POST /wallet/create",
                "endpoints": {
                    "create_wallet": "/wallet/create",
                },
            },
            headers={
                "X-402-Required": "wallet",
            },
        )
    
    # Check for payment proof
    payment_proof = request.headers.get("X-402-Proof", "")
    paid = False
    
    # Also accept X-API-Key (prepaid credits)
    api_key_header = request.headers.get("X-API-Key", "")
    if api_key_header:
        from purchase_system import verify_api_key, use_api_key
        key_info = verify_api_key(api_key_header)
        if key_info and key_info["remaining"] > 0:
            use_api_key(api_key_header, "halal-check", request.client.host if request.client else "")
            paid = True
    
    if not paid and payment_proof:
        paid = verify_payment(payment_proof)
    
    if not paid:
        # Return 402 Payment Required with x402 headers
        x402_headers = get_x402_headers()
        return JSONResponse(
            status_code=402,
            content={
                "error": "Payment Required",
                "message": f"Bitte sende ${PRICE_USDC} USDC auf Base an die Wallet-Adresse und wiederhole die Anfrage mit X-402-Proof Header.",
                "instruction": f"1. Sende {PRICE_USDC} USDC on Base an: {WALLET_ADDRESS}",
                "instruction_2": "2. Wiederhole die Anfrage mit Header: X-402-Proof: <transaction_hash>",
                "payment": {
                    "price_usdc": PRICE_USDC,
                    "chain": "Base (Chain ID: 8453)",
                    "token": "USDC",
                    "token_contract": USDC_CONTRACT_ADDRESS,
                    "recipient": WALLET_ADDRESS,
                },
                "example": f"curl -H 'X-402-Proof: 0xYOUR_TX_HASH' '{request.url}'",
            },
            headers=x402_headers,
        )
    
    # Payment verified - run halal check
    result = await check_halal(symbol)
    
    # Add payment info
    result["payment"] = {
        "paid": True,
        "amount_usdc": PRICE_USDC,
        "tx_hash": payment_proof,
    }
    
    # Cache the session
    _paid_sessions[payment_proof] = time.time()
    
    return result


@app.get("/halal-check/{symbol}")
async def halal_check_path(request: Request, symbol: str):
    """Path-based halal check (redirects to query param version)."""
    url = str(request.url).replace(f"/halal-check/{symbol}", f"/halal-check?symbol={symbol}")
    return await halal_check(request, symbol=symbol)


# ── API Key System (Web2 Prepaid) ──────────────────────────────────────────────

ADMIN_PASSWORD = "halima2026"  # simple password for admin endpoints

@app.get("/pricing")
async def pricing_page():
    """Show available pricing plans."""
    return {
        "plans": {
            "starter": {"price_usd": 5.00, "requests": 500, "description": "500 API calls — $5"},
            "pro": {"price_usd": 20.00, "requests": 3000, "description": "3000 API calls — $20"},
            "enterprise": {"price_usd": 50.00, "requests": 10000, "description": "10000 API calls — $50"},
        },
        "free_tier": {"requests_per_day": 10, "description": "Kostenlos: 10 Calls/Tag/IP"},
        "how_to_use": [
            "1. POST /register mit Email → API Key erhalten",
            "2. X-API-Key: <dein_key> Header bei jedem Request",
            "3. GET /credits → Restliche Calls prüfen",
            "4. POST /recharge → Credits kaufen (PayPal/USDC)",
        ],
        "endpoints": {
            "register": "POST /register",
            "credits": "GET /credits",
            "recharge": "POST /recharge",
        },
    }


@app.post("/register")
async def register_endpoint(request: Request):
    """Register with email. Returns a free trial API key (10 free credits)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON body required", "example": {"email": "user@example.com"}})
    
    email = body.get("email", "").strip().lower()
    if not email or "@" not in email or "." not in email:
        return JSONResponse(status_code=400, content={"error": "Valid email required"})
    
    result = ps_register(email)
    if "error" in result:
        return JSONResponse(status_code=409, content=result)
    
    return {"success": True, **result}


@app.get("/credits")
async def credits_endpoint(request: Request):
    """Check remaining credits for your API key."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        return JSONResponse(status_code=401, content={"error": "X-API-Key header required"})
    
    result = ps_credits(api_key)
    if "error" in result:
        return JSONResponse(status_code=402, content=result)
    
    return result


@app.post("/recharge")
async def recharge_endpoint(request: Request):
    """Request a credit recharge. Sends payment instructions."""
    api_key = request.headers.get("X-API-Key", "")
    if not api_key:
        return JSONResponse(status_code=401, content={"error": "X-API-Key header required"})
    
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON body required", "example": {"bundle": "starter"}})
    
    bundle = body.get("bundle", "").strip()
    if bundle not in PS_BUNDLES:
        return JSONResponse(status_code=400, content={
            "error": f"Unknown bundle: {bundle}",
            "available": {k: v["desc"] for k, v in PS_BUNDLES.items()},
        })
    
    result = ps_recharge(api_key, bundle)
    if "error" in result:
        return JSONResponse(status_code=400, content=result)
    
    return result


@app.post("/admin/confirm-recharge")
async def admin_confirm_recharge(request: Request):
    """ADMIN: Confirm payment and add credits. Protected by password."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "JSON body required"})
    
    if body.get("password") != ADMIN_PASSWORD:
        return JSONResponse(status_code=403, content={"error": "Invalid admin password"})
    
    api_key = body.get("api_key", "")
    bundle = body.get("bundle", "")
    
    if not api_key or not bundle:
        return JSONResponse(status_code=400, content={"error": "api_key and bundle required"})
    
    result = ps_confirm(api_key, bundle)
    return result


@app.get("/admin/status")
async def admin_status(request: Request):
    """ADMIN: View system status."""
    password = request.headers.get("X-Admin-Password", "")
    if password != ADMIN_PASSWORD:
        return JSONResponse(status_code=403, content={"error": "X-Admin-Password header required"})
    
    result = ps_status()
    return result


def main():
    """Entry point."""
    uvicorn.run(
        "app.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        log_level="info",
    )


if __name__ == "__main__":
    main()