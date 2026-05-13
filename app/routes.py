"""
x402 Multi-Service API Router — All x402 paid service endpoints
Dynamically generates endpoints from SERVICE_REGISTRY (30+ services).
"""
import json
import time
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

from .config import WALLET_ADDRESS, PRICE_USDC, INTERNAL_KEY
from .x402_protocol import get_x402_headers, verify_payment
from .services import SERVICE_REGISTRY
from .rate_limiter import get_remaining, consume, get_client_ip
from purchase_system import verify_api_key, use_api_key, get_status as ps_status

router = APIRouter(prefix="/v1", tags=["x402 Services"])
_counters = {}


def _x402_check(request: Request, price: float = PRICE_USDC) -> Optional[JSONResponse]:
    """Check x402 payment. Returns None if paid, or 402 JSONResponse."""
    # Internal bypass for MCP server
    if request.headers.get("X-Internal-Key") == INTERNAL_KEY:
        return None

    # API Key check (prepaid credits)
    api_key = request.headers.get("X-Api-Key", "")
    if api_key:
        info = verify_api_key(api_key)
        if info and info["remaining"] > 0:
            ip = get_client_ip(request)
            use_api_key(api_key, "unknown", ip)
            return None
        return JSONResponse(
            status_code=402,
            content={"error": "API Key exhausted", "message": "Buy more credits at http://178.105.35.170:8080/pricing",
                     "upgrade": "http://178.105.35.170:8080/pricing"},
        )

    # x402 payment check (USDC on-chain)
    if WALLET_ADDRESS:
        proof = request.headers.get("X-402-Proof", "")
        if proof and verify_payment(proof):
            return None

    # Free-tier: 10 IP-based calls per day, no wallet needed
    ip = get_client_ip(request)
    remaining = get_remaining(ip)
    if remaining > 0:
        consume(ip)
        return None

    # All exhausted - 429 Upgrade Required
    x402_headers = {f"X-402-{k}": str(v) for k, v in {"Price": str(price), "Chain": "Base8453",
        "Token": "0x8335...2913",
        "Recipient": WALLET_ADDRESS or "unconfigured"}.items()}
    return JSONResponse(
        status_code=429,
        content={
            "error": "Free tier exceeded",
            "message": "Upgrade for unlimited access",
            "upgrade": "http://178.105.35.170:8080/pricing",
            "free_tier_remaining": 0,
            "payment": {"price_usdc": price, "chain": "Base (8453)", "recipient": WALLET_ADDRESS} if WALLET_ADDRESS else None,
        },
        headers=x402_headers,
    )


@router.get("/services")
async def list_services():
    """List ALL available x402 services with pricing."""
    services_list = []
    total_served = sum(_counters.values())
    for sid, svc in SERVICE_REGISTRY.items():
        services_list.append({
            "id": sid,
            "name": svc["name"],
            "price": svc["price"],
            "endpoint": f"POST /v1/{sid}",
            "description": svc["desc"],
            "parameters": svc.get("params", []),
            "requests_served": _counters.get(sid, 0),
        })
    return {
        "name": "x402 Multi-Service API v3.0",
        "wallet": WALLET_ADDRESS,
        "chain": "Base (8453)",
        "total_services": len(services_list),
        "total_requests_served": total_served,
        "services": services_list,
        "payment_info": {
            "how_to_pay": "Send USDC on Base + include X-402-Proof header",
            "network": "Base Mainnet (8453)",
            "usdc_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        },
    }


@router.post("/{service_id}")
async def execute_service(service_id: str, request: Request):
    """
    Execute ANY service from the registry dynamically.
    Services: uuid, hash, base64, password, text-stats, json-process,
              markdown, qrcode, barcode, url-fetch, rss-read, pdf-extract,
              ip-lookup, weather, currency, color, email-validate, ua-parse,
              random-data, time-tools, file-hash, sentiment, html-strip,
              text-diff, csv-json, url-ping, country-info, number-tools,
              lorem-ipsum, string-tools, search, analyze-code, process-data,
              translate, generate-text, halal-check
    """
    if service_id not in SERVICE_REGISTRY:
        valid = ", ".join(sorted(SERVICE_REGISTRY.keys()))
        return JSONResponse(status_code=404, content={
            "error": f"Unknown service: {service_id}",
            "available_services": valid,
        })

    svc = SERVICE_REGISTRY[service_id]
    price = svc["price"]

    # Check payment
    payment = _x402_check(request, price)
    if payment:
        return payment

    # Track
    _counters[service_id] = _counters.get(service_id, 0) + 1

    # Extract parameters from body (JSON) or query params
    try:
        body = await request.json()
    except Exception:
        body = {}

    # Merge query params (url?key=val) into body (body takes priority)
    params = dict(request.query_params)
    params.update(body)

    # Call the service function with matched params
    func = svc["func"]
    try:
        result = await func(**params)
        return {
            "service": service_id,
            "price_paid": price,
            "data": result,
        }
    except TypeError as e:
        # Parameter mismatch - try with only valid params
        import inspect
        sig = inspect.signature(func)
        valid_params = set(sig.parameters.keys())
        filtered = {k: v for k, v in params.items() if k in valid_params}
        result = await func(**filtered)
        return {
            "service": service_id,
            "price_paid": price,
            "note": f"Invalid params ignored: {[k for k in params if k not in valid_params]}",
            "data": result,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "error": f"Service error: {str(e)}",
            "service": service_id,
        })
