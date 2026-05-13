"""
Workflow Execution Endpoint — /v1/execute-workflow
Minimaler Wrapper: Auth-Pruefung + Prompt-Building -> Delegation an inference_handler.
Kein eigenes Payment, kein eigenes Routing, keine neuen Agenten.
"""
import time as _time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from .config import INTERNAL_KEY
from .inference_router import inference as inference_handler

router = APIRouter(prefix="/v1", tags=["Workflow"])


@router.post("/execute-workflow")
async def execute_workflow(request: Request):
    """
    POST /v1/execute-workflow

    JSON Body:
        - task (string)
        - context (object, optional)
        - priority (string, optional)
        - max_cost (float, optional)

    Auth: identisch zu /v1/inference (X-Api-Key, X-Internal-Key, Free Tier)
    """
    # ─── AUTH (identisch zu inference_router._x402_check_inference) ───
    if request.headers.get("X-Internal-Key") != INTERNAL_KEY:
        api_key = request.headers.get("X-Api-Key", "")
        if api_key:
            from purchase_system import verify_api_key, use_api_key
            from .rate_limiter import get_client_ip
            info = verify_api_key(api_key)
            if info and info["remaining"] >= 5:
                use_api_key(api_key, "workflow", get_client_ip(request))
            else:
                return JSONResponse(
                    status_code=402,
                    content={"error": "Insufficient credits", "message": "Workflow costs 5 credits."},
                )
        else:
            from .rate_limiter import get_remaining, consume, get_client_ip
            ip = get_client_ip(request)
            remaining = get_remaining(ip)
            if remaining > 0:
                consume(ip)
            else:
                return JSONResponse(
                    status_code=429,
                    content={"error": "Free tier exceeded", "message": "Use X-Api-Key or X-Internal-Key"},
                )

    # ─── PARSE BODY ───
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    task = body.get("task", "").strip()
    if not task:
        return JSONResponse(status_code=400, content={"error": "Missing 'task' field"})

    # Build prompt from task + optional context
    context = body.get("context")
    if context and isinstance(context, dict):
        context_lines = "\n".join(f"{k}: {v}" for k, v in context.items())
        prompt = f"Task: {task}\n\nContext:\n{context_lines}"
    else:
        prompt = task

    # Map priority to preferred_model
    priority = body.get("priority", "auto").lower()
    if priority in ("fast", "cheap"):
        preferred_model = "deepseek"
    elif priority == "quality":
        preferred_model = "deepseek"  # only provider available
    else:
        preferred_model = "auto"

    # ─── CONSTRUCT INTERNAL REQUEST ───
    # We build a real dict and call inference handler via a lightweight wrapper
    # to avoid Mock objects. Instead we call _call_openrouter directly.
    from .inference_router import _call_openrouter, PROVIDER_WHITELIST, MAX_TOKENS_HARD, MAX_TOKENS_DEFAULT, MAX_COST_HARD, RETRY_MAX
    from .routing_policy import routing_decision_function
    from .observability import ErrorType, RequestStatus, classify_error, determine_status, generate_request_id, build_observability_log
    from pathlib import Path
    from datetime import datetime, timezone
    import json, re, logging

    LOG_DIR = Path("/root/.hermes/logs")
    LOG_FILE = LOG_DIR / "inference-router.jsonl"
    logger = logging.getLogger("inference-router")

    start_total = _time.monotonic()
    request_id = generate_request_id()

    # Sanitize
    max_tokens = min(int(body.get("max_tokens", MAX_TOKENS_DEFAULT)), MAX_TOKENS_HARD)
    max_cost = min(float(body.get("max_cost", MAX_COST_HARD)), MAX_COST_HARD)
    prompt = re.sub(r"\s+", " ", prompt).strip()

    # Routing decision (observability)
    routing_decision = routing_decision_function(prompt=prompt, preferred_model=preferred_model, max_cost=max_cost)

    # Single-provider: deepseek only
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
            break
        else:
            last_error = result["error"]
            failure_reason = result["error"]
            retries += 1
            provider_error_type = classify_error(result["error"])

    total_elapsed_ms = int((_time.monotonic() - start_total) * 1000)

    # Observability log (same format as inference_router)
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
    log_entry["routing_decision"] = {
        "task_type": routing_decision["task_type"],
        "decision_reason": routing_decision["decision_reason"],
        "estimated_cost": routing_decision["estimated_cost"],
        "estimated_latency_ms": routing_decision["estimated_latency_ms"],
        "task_confidence": routing_decision["confidence"],
    }
    log_entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(LOG_FILE, "a") as f:
            f.write(json.dumps(log_entry, default=str) + "\n")
    except Exception:
        pass

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

    return {
        "model_used": model_used,
        "tokens_used": tokens_used,
        "estimated_cost": estimated_cost,
        "response": response_text,
        "latency_ms": total_elapsed_ms,
        "workflow_meta": {
            "task": task[:100],
            "priority": priority,
            "context_included": context is not None,
        },
    }
