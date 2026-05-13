"""
HALIMA Execution API — POST /v1/execute
Einfacher externer Endpoint für 4 Task-Typen.
Nutzt intern: inference_router, billing, pricing, routing, observability.
Kein Refactoring. Nur additiv.
"""
import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.observability import generate_request_id, ErrorType, RequestStatus, classify_error, determine_status, build_observability_log
from app.inference_router import (
    _x402_check_inference,
    _call_openrouter,
    _estimate_cost,
    _resolve_api_key_to_agent,
    _get_http_client,
    PROVIDER_WHITELIST,
    MAX_TOKENS_HARD,
    MAX_TOKENS_DEFAULT,
    MAX_COST_HARD,
    RETRY_MAX,
    OPENROUTER_API_KEY,
    _log_entry,
)

logger = logging.getLogger("execute-api")

execute_router = APIRouter(prefix="/v1", tags=["Execute"])

# ─── Task Templates ───
TASK_TEMPLATES = {
    "summarize": {
        "system": "Summarize the following text concisely. Output only the summary, no preamble.",
        "max_tokens": 512,
    },
    "classify": {
        "system": "Classify the following text. Output only the category label, no explanation.",
        "max_tokens": 64,
    },
    "rewrite": {
        "system": "Rewrite the following text clearly and professionally. Output only the rewritten text.",
        "max_tokens": 1024,
    },
    "extract_json": {
        "system": "Extract structured data from the following text as valid JSON. Output only the JSON, no markdown.",
        "max_tokens": 2048,
    },
}

ALLOWED_TASKS = set(TASK_TEMPLATES.keys())


@execute_router.post("/execute")
async def execute_task(request: Request):
    """
    POST /v1/execute
    Einfacher Task-Endpoint. Unterstützt: summarize, classify, rewrite, extract_json.

    Auth: X-API-KEY oder X-Internal-Key
    """
    start_total = time.monotonic()
    request_id = generate_request_id()

    # ─── Auth (reuse existing) ───
    auth = _x402_check_inference(request)
    _a2a_api_key = request.headers.get("X-API-KEY", "")
    _a2a_agent_id = None
    if _a2a_api_key:
        _a2a_agent_id = _resolve_api_key_to_agent(_a2a_api_key)
        if _a2a_agent_id:
            auth = None
        else:
            return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": "Invalid X-API-KEY"})
    if auth:
        return auth

    # ─── Parse body ───
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    task = body.get("task", "").strip().lower()
    text = body.get("text", "").strip()

    if not task or task not in ALLOWED_TASKS:
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Invalid task. Allowed: {sorted(ALLOWED_TASKS)}",
                "example": {"task": "summarize", "text": "Your text here"},
            },
        )
    if not text:
        return JSONResponse(status_code=400, content={"error": "'text' field is required"})

    # ─── Build prompt from template ───
    tmpl = TASK_TEMPLATES[task]
    prompt = f"{tmpl['system']}\n\n---\n{text}"
    max_tokens = min(int(body.get("max_tokens", tmpl["max_tokens"])), MAX_TOKENS_HARD)

    # ─── Execute via existing inference router internals ───
    provider_name = "deepseek"
    provider = PROVIDER_WHITELIST.get(provider_name)
    if not provider:
        return JSONResponse(status_code=503, content={"error": "No provider available"})

    model_id = provider["model_id"]
    timeout_s = provider["timeout_s"]

    result = await _call_openrouter(model_id, prompt, max_tokens, timeout_s)
    total_elapsed_ms = int((time.monotonic() - start_total) * 1000)

    if not result["success"]:
        log_entry = build_observability_log(
            request_id=request_id,
            provider_used=provider_name,
            model_used=model_id,
            latency_ms=total_elapsed_ms,
            cost_estimate=0,
            tokens_used=0,
            prompt_length=len(prompt),
            success=False,
            error_type=classify_error(result["error"]),
            status=determine_status(False, classify_error(result["error"])),
            error_detail=result["error"][:300],
            http_status=503,
            preferred_model=provider_name,
        )
        _log_entry(log_entry)
        return JSONResponse(
            status_code=503,
            content={"error": "Execution failed", "detail": result["error"][:300]},
        )

    estimated_cost = result["estimated_cost"]
    tokens_used = result["total_tokens"]
    response_text = result["response"]

    # ─── Observability (reuse existing) ───
    log_entry = build_observability_log(
        request_id=request_id,
        provider_used=provider_name,
        model_used=model_id,
        latency_ms=total_elapsed_ms,
        cost_estimate=estimated_cost,
        tokens_used=tokens_used,
        prompt_length=len(prompt),
        success=True,
        error_type=ErrorType.NONE,
        status=determine_status(True, ErrorType.NONE),
        error_detail=None,
        http_status=200,
        preferred_model=provider_name,
    )
    _log_entry(log_entry)

    return {
        "task": task,
        "result": response_text,
        "usage": {
            "tokens": tokens_used,
            "cost_usd": estimated_cost,
            "latency_ms": total_elapsed_ms,
        },
    }


@execute_router.get("/execute/health")
async def execute_health():
    """Health check for execute API."""
    return {
        "status": "ok",
        "tasks": sorted(ALLOWED_TASKS),
        "model": "deepseek/deepseek-chat",
        "max_tokens": MAX_TOKENS_HARD,
        "max_cost": MAX_COST_HARD,
        "openrouter_configured": bool(OPENROUTER_API_KEY),
    }
