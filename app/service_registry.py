"""
Service Discovery Router — Agent Registry Layer.
GET  /v1/services          → list all active services
POST /v1/services/register → register a new service (API-Key required)
"""
import sqlite3
import threading
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

# ─── RESOLVE API KEY ───
# Import from inference_router to avoid duplication
try:
    from .inference_router import _resolve_api_key_to_agent
except ImportError:
    # Fallback: define inline if circular import
    def _resolve_api_key_to_agent(api_key: str) -> Optional[str]:
        return None

logger = logging.getLogger("service-registry")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logger.addHandler(_h)

# ─── DB ───
_DB_PATH = Path(__file__).parent / "agent_services.db"
_db_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_services (
            service_id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            service_name TEXT NOT NULL,
            description TEXT DEFAULT '',
            endpoint TEXT DEFAULT '',
            pricing_tier TEXT DEFAULT 'simple',
            tags TEXT DEFAULT '',
            capabilities TEXT DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    return conn


def register_service(
    service_id: str,
    agent_id: str,
    service_name: str,
    description: str = "",
    endpoint: str = "",
    pricing_tier: str = "simple",
    tags: str = "",
    capabilities: str = "",
) -> dict:
    """Register a new service. Returns {"ok": bool, "error": str|None}."""
    with _db_lock:
        conn = _get_db()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO agent_services
                (service_id, agent_id, service_name, description, endpoint, pricing_tier, tags, capabilities, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (service_id, agent_id, service_name, description, endpoint, pricing_tier, tags, capabilities))
            conn.commit()
            conn.close()
            return {"ok": True, "error": None}
        except Exception as e:
            conn.close()
            return {"ok": False, "error": str(e)}


def get_active_services() -> list[dict]:
    """Return all active services."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT service_id, agent_id, service_name, description, endpoint, pricing_tier, tags, capabilities, created_at
        FROM agent_services WHERE is_active = 1 ORDER BY created_at DESC
    """).fetchall()
    conn.close()
    return [
        {
            "service_id": r[0], "agent_id": r[1],
            "service_name": r[2], "description": r[3],
            "endpoint": r[4], "pricing_tier": r[5],
            "tags": r[6], "capabilities": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


# ─── INTER-AGENT EXECUTION ───

async def _find_service(service_id: str) -> Optional[dict]:
    """Look up a registered service by ID."""
    conn = _get_db()
    row = conn.execute(
        "SELECT service_id, agent_id, service_name, endpoint, pricing_tier FROM agent_services WHERE service_id = ? AND is_active = 1",
        (service_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "service_id": row[0], "agent_id": row[1],
        "service_name": row[2], "endpoint": row[3], "pricing_tier": row[4],
    }


async def _resolve_price_for_tier(pricing_tier: str) -> float:
    """Map pricing_tier to price multiplier."""
    base = 0.02
    multipliers = {"simple": 1, "medium": 2, "high": 4}
    return base * multipliers.get(pricing_tier, 1)


# ─── SERVICE MATCHING ENGINE ───

async def match_service(task_type: str = "", required_capability: str = "") -> Optional[dict]:
    """
    Find the best matching service for a task.
    Matching rules:
    1. Capability match first (exact or partial)
    2. Then pricing tier preference: simple < medium < high
    3. Only active services
    Returns best matching service or None.
    """
    conn = _get_db()
    rows = conn.execute("""
        SELECT service_id, agent_id, service_name, endpoint, pricing_tier, tags, capabilities
        FROM agent_services WHERE is_active = 1
    """).fetchall()
    conn.close()

    if not rows:
        return None

    candidates = []
    for row in rows:
        svc = {
            "service_id": row[0], "agent_id": row[1],
            "service_name": row[2], "endpoint": row[3],
            "pricing_tier": row[4], "tags": row[5] or "",
            "capabilities": row[6] or "",
        }
        score = 0

        # Capability match (highest priority)
        caps = svc["capabilities"].lower()
        if required_capability and required_capability.lower() in caps:
            score += 100
        elif required_capability and any(c.strip() in caps for c in required_capability.lower().split(",")):
            score += 50

        # Tag match
        tags = svc["tags"].lower()
        if task_type and task_type.lower() in tags:
            score += 30

        # Pricing tier preference (lower = cheaper = preferred for same capability match)
        tier_pref = {"simple": 3, "medium": 2, "high": 1}
        score += tier_pref.get(svc["pricing_tier"], 0)

        if score >= 30:
            candidates.append((score, svc))

    if not candidates:
        return None

    # Sort by score descending, return best
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


# ─── ROUTER ───
router = APIRouter(prefix="/v1/services", tags=["Service Discovery"])


@router.get("")
async def list_services():
    """GET /v1/services — List all active registered services."""
    services = get_active_services()
    logger.info(f"SERVICE_DISCOVERY_QUERY results={len(services)}")
    return {
        "services": services,
        "total": len(services),
    }


@router.post("/register")
async def register_service_endpoint(request: Request):
    """POST /v1/services/register — Register a service (requires valid X-API-KEY)."""
    # Auth: require valid A2A API key
    api_key = request.headers.get("X-API-KEY", "")
    if not api_key:
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "X-API-KEY header required"},
        )
    agent_id = _resolve_api_key_to_agent(api_key)
    if not agent_id:
        return JSONResponse(
            status_code=401,
            content={"error": "Unauthorized", "message": "Invalid X-API-KEY"},
        )

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body"},
        )

    service_id = body.get("service_id", "").strip()
    service_name = body.get("service_name", "").strip()
    if not service_id or not service_name:
        return JSONResponse(
            status_code=400,
            content={"error": "service_id and service_name are required"},
        )

    description = body.get("description", "")
    endpoint = body.get("endpoint", "")
    pricing_tier = body.get("pricing_tier", "simple")
    tags = body.get("tags", "")
    capabilities = body.get("capabilities", "")

    result = register_service(
        service_id=service_id,
        agent_id=agent_id,
        service_name=service_name,
        description=description,
        endpoint=endpoint,
        pricing_tier=pricing_tier,
        tags=tags,
        capabilities=capabilities,
    )

    if not result["ok"]:
        return JSONResponse(status_code=500, content={"error": result["error"]})

    logger.info(f"SERVICE_REGISTERED service_id={service_id} agent_id={agent_id} name={service_name}")
    return {
        "success": True,
        "service_id": service_id,
        "agent_id": agent_id,
        "service_name": service_name,
        "pricing_tier": pricing_tier,
    }


# ─── INTER-AGENT EXECUTION ROUTE ───
# Separate router for /v1/agent/* endpoints
agent_router = APIRouter(prefix="/v1/agent", tags=["Inter-Agent Execution"])


@agent_router.post("/execute")
async def execute_agent_task(request: Request):
    """
    POST /v1/agent/execute
    Execute a task on a registered service agent.

    Input: {"service_id": "...", "task": {...}}
    Flow: caller → registry lookup → inference execution → billing → response
    """
    import time as _time
    from app.observability import generate_request_id

    exec_request_id = generate_request_id()

    # Auth: require valid A2A API key
    api_key = request.headers.get("X-API-KEY", "")
    if not api_key:
        return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": "X-API-KEY required"})
    caller_agent_id = _resolve_api_key_to_agent(api_key)
    if not caller_agent_id:
        return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": "Invalid X-API-KEY"})

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    target_service_id = body.get("service_id", "").strip()
    task_payload = body.get("task", {})

    if not target_service_id:
        return JSONResponse(status_code=400, content={"error": "service_id is required"})

    # Step 1: Registry lookup
    service = await _find_service(target_service_id)
    if not service:
        logger.warning(f"AGENT_TASK_EXECUTION_FAIL service_id={target_service_id} reason=SERVICE_NOT_FOUND")
        return JSONResponse(
            status_code=404,
            content={"error": "Service not found", "service_id": target_service_id},
        )

    target_agent_id = service["agent_id"]
    target_endpoint = service["endpoint"] or "/v1/inference"
    pricing_tier = service["pricing_tier"]

    logger.info(
        f"AGENT_TASK_EXECUTION_START "
        f"caller={caller_agent_id} target_service={target_service_id} "
        f"target_agent={target_agent_id} endpoint={target_endpoint} "
        f"pricing_tier={pricing_tier} request_id={exec_request_id}"
    )

    # Step 2: Resolve price from service pricing_tier
    task_price = await _resolve_price_for_tier(pricing_tier)

    # Step 3: Build internal inference request
    # The target agent's API key is needed for the internal call
    # We use the caller's identity but route to the target service
    internal_payload = {
        "prompt": task_payload.get("prompt", ""),
        "max_tokens": task_payload.get("max_tokens", 100),
        "meta": {"agent_id": target_agent_id},
        "task": {
            "complexity": pricing_tier,  # Map pricing_tier to complexity
            "constraints": {"cost_usd": task_price},
        },
    }

    if not internal_payload["prompt"]:
        return JSONResponse(status_code=400, content={"error": "task.prompt is required"})

    # Step 4: Execute via internal HTTP call to own inference endpoint
    try:
        import httpx
        _exec_start = _time.monotonic()
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)) as client:
            internal_resp = await client.post(
                f"http://127.0.0.1:8080{target_endpoint}",
                json=internal_payload,
                headers={
                    "X-Internal-Key": "hermes-mcp-internal-v1",
                    "Content-Type": "application/json",
                },
            )
        _exec_latency_ms = int((_time.monotonic() - _exec_start) * 1000)

        if internal_resp.status_code != 200:
            _err_body = internal_resp.text[:300]
            logger.warning(
                f"AGENT_TASK_EXECUTION_FAIL "
                f"caller={caller_agent_id} target={target_service_id} "
                f"http_status={internal_resp.status_code} "
                f"latency_ms={_exec_latency_ms} request_id={exec_request_id}"
            )
            return JSONResponse(
                status_code=internal_resp.status_code,
                content={
                    "error": "Target service execution failed",
                    "service_id": target_service_id,
                    "detail": _err_body,
                },
            )

        result = internal_resp.json()
        logger.info(
            f"AGENT_TASK_EXECUTION_SUCCESS "
            f"caller={caller_agent_id} target={target_service_id} "
            f"latency_ms={_exec_latency_ms} request_id={exec_request_id}"
        )

        return {
            "success": True,
            "service_id": target_service_id,
            "agent_id": target_agent_id,
            "pricing_tier": pricing_tier,
            "execution": {
                "latency_ms": _exec_latency_ms,
                "model_used": result.get("model_used"),
                "tokens_used": result.get("tokens_used"),
            },
            "result": {
                "response": result.get("response"),
                "cost_usd": result.get("cost_usd"),
                "payment_status": result.get("payment_status"),
            },
        }

    except Exception as e:
        logger.error(
            f"AGENT_TASK_EXECUTION_FAIL "
            f"caller={caller_agent_id} target={target_service_id} "
            f"error={str(e)[:200]} request_id={exec_request_id}"
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal execution error", "detail": str(e)[:200]},
        )


@agent_router.post("/auto-execute")
async def auto_execute_agent_task(request: Request):
    """
    POST /v1/agent/auto-execute
    Automatically match and execute a task on the best-fitting service agent.

    Input: {"task": {"prompt": "...", "task_type": "...", "required_capability": "..."}}
    Flow: task → match_service() → selected service → inter-agent execution → billing → response
    """
    import time as _time
    from app.observability import generate_request_id

    exec_request_id = generate_request_id()

    # Auth: require valid A2A API key
    api_key = request.headers.get("X-API-KEY", "")
    if not api_key:
        return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": "X-API-KEY required"})
    caller_agent_id = _resolve_api_key_to_agent(api_key)
    if not caller_agent_id:
        return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": "Invalid X-API-KEY"})

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    task_payload = body.get("task", {})
    # Support both nested (task.prompt) and flat (input.prompt) formats
    prompt = task_payload.get("prompt") or body.get("input", {}).get("prompt", "")
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "task.prompt is required"})
    task_payload["prompt"] = prompt

    task_type = task_payload.get("task_type", "") or body.get("task_type", "")
    required_capability = task_payload.get("required_capability", "") or body.get("required_capability", "")
    # If task_type looks like a capability name (contains hyphen) and no required_capability set, use it
    if not required_capability and task_type and "-" in task_type:
        required_capability = task_type

    # Step 1: Match service
    matched_service = await match_service(task_type=task_type, required_capability=required_capability)

    if not matched_service:
        logger.warning(
            f"SERVICE_MATCH_NOT_FOUND "
            f"caller={caller_agent_id} task_type={task_type} "
            f"capability={required_capability} request_id={exec_request_id}"
        )
        return JSONResponse(
            status_code=404,
            content={
                "error": "No matching service found",
                "task_type": task_type,
                "required_capability": required_capability,
            },
        )

    target_service_id = matched_service["service_id"]
    target_agent_id = matched_service["agent_id"]
    target_endpoint = matched_service["endpoint"] or "/v1/inference"
    pricing_tier = matched_service["pricing_tier"]

    logger.info(
        f"SERVICE_MATCH_FOUND "
        f"caller={caller_agent_id} matched_service={target_service_id} "
        f"target_agent={target_agent_id} task_type={task_type} "
        f"capability={required_capability} request_id={exec_request_id}"
    )
    logger.info(
        f"AUTO_AGENT_EXECUTION_START "
        f"caller={caller_agent_id} target_service={target_service_id} "
        f"target_agent={target_agent_id} pricing_tier={pricing_tier} "
        f"request_id={exec_request_id}"
    )

    # Step 2: Resolve price from matched service pricing_tier
    task_price = await _resolve_price_for_tier(pricing_tier)

    # Step 3: Build internal inference request
    internal_payload = {
        "prompt": task_payload["prompt"],
        "max_tokens": task_payload.get("max_tokens", 100),
        "meta": {"agent_id": target_agent_id},
        "task": {
            "complexity": pricing_tier,
            "constraints": {"cost_usd": task_price},
        },
    }

    # Step 4: Execute via internal HTTP call
    try:
        import httpx
        _exec_start = _time.monotonic()
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)) as client:
            internal_resp = await client.post(
                f"http://127.0.0.1:8080{target_endpoint}",
                json=internal_payload,
                headers={
                    "X-Internal-Key": "hermes-mcp-internal-v1",
                    "Content-Type": "application/json",
                },
            )
        _exec_latency_ms = int((_time.monotonic() - _exec_start) * 1000)

        if internal_resp.status_code != 200:
            _err_body = internal_resp.text[:300]
            logger.warning(
                f"AUTO_AGENT_EXECUTION_FAIL "
                f"caller={caller_agent_id} target={target_service_id} "
                f"http_status={internal_resp.status_code} "
                f"latency_ms={_exec_latency_ms} request_id={exec_request_id}"
            )
            return JSONResponse(
                status_code=internal_resp.status_code,
                content={
                    "error": "Target service execution failed",
                    "service_id": target_service_id,
                    "detail": _err_body,
                },
            )

        result = internal_resp.json()
        logger.info(
            f"AUTO_AGENT_EXECUTION_SUCCESS "
            f"caller={caller_agent_id} target={target_service_id} "
            f"latency_ms={_exec_latency_ms} request_id={exec_request_id}"
        )

        # ─── Economics Logging ───
        _econ_revenue = task_price
        _econ_cost = result.get("estimated_cost", result.get("cost_usd", 0.0))
        if not isinstance(_econ_cost, (int, float)):
            _econ_cost = 0.0
        log_economic_event(
            event_id=f"econ_{exec_request_id}",
            request_id=exec_request_id,
            agent_id=caller_agent_id,
            service_id=target_service_id,
            pricing_tier=pricing_tier,
            revenue_usd=_econ_revenue,
            provider_cost_usd=_econ_cost,
            latency_ms=_exec_latency_ms,
        )

        # ─── Decision Output Contract ───
        from app.decision_contract import build_decision_output

        _profit = task_price - _econ_cost

        return build_decision_output(
            decision_id=exec_request_id,
            agent_id=target_agent_id,
            request_id=exec_request_id,
            input_summary=task_payload.get("prompt", ""),
            decision_type="analysis",
            value_output={
                "label": "auto_execute_complete",
                "confidence": 1.0,
                "risk_score": 0.0,
                "utility_score": 1.0,
                "service_id": target_service_id,
                "pricing_tier": pricing_tier,
                "match_criteria": {
                    "task_type": task_type,
                    "required_capability": required_capability,
                },
                "execution": {
                    "latency_ms": _exec_latency_ms,
                    "model_used": result.get("model_used"),
                    "tokens_used": result.get("tokens_used"),
                },
                "response": result.get("response"),
            },
            monetization={
                "tier": pricing_tier,
                "price_usd": task_price,
                "cost_usd": round(_econ_cost, 6),
                "profit_usd": round(_profit, 6),
            },
            workflow_meta={
                "steps_executed": 1,
                "latency_ms": _exec_latency_ms,
            },
            payment={
                "status": "charged",
                "provider": "openrouter",
            },
        )

    except Exception as e:
        logger.error(
            f"AUTO_AGENT_EXECUTION_FAIL "
            f"caller={caller_agent_id} target={target_service_id} "
            f"error={str(e)[:200]} request_id={exec_request_id}"
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal execution error", "detail": str(e)[:200]},
        )


# ─── MULTI-AGENT WORKFLOW CHAIN ───

@agent_router.post("/workflow")
async def execute_workflow(request: Request):
    """
    POST /v1/agent/workflow
    Execute a multi-step agent workflow chain.
    Each step's output is injected into the next step's prompt.

    Input: {"workflow": [{"required_capability": "..."}, ...], "input": {"prompt": "..."}}
    Flow: input → step1(match+execute) → result injected → step2 → ... → final result
    """
    import time as _time
    from app.observability import generate_request_id

    workflow_id = generate_request_id()
    _wf_start = _time.monotonic()

    # Auth
    api_key = request.headers.get("X-API-KEY", "")
    if not api_key:
        return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": "X-API-KEY required"})
    caller_agent_id = _resolve_api_key_to_agent(api_key)
    if not caller_agent_id:
        return JSONResponse(status_code=401, content={"error": "Unauthorized", "message": "Invalid X-API-KEY"})

    # Parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body"})

    workflow_steps = body.get("workflow", [])
    input_data = body.get("input", {})

    if not workflow_steps:
        return JSONResponse(status_code=400, content={"error": "workflow array is required"})
    if not input_data.get("prompt"):
        return JSONResponse(status_code=400, content={"error": "input.prompt is required"})

    logger.info(
        f"WORKFLOW_START "
        f"caller={caller_agent_id} steps={len(workflow_steps)} "
        f"workflow_id={workflow_id}"
    )

    # ─── WORKFLOW GOVERNOR CONFIG ───
    _MAX_WORKFLOW_DEPTH = 6
    _MAX_EXPANSION_STEPS = 3
    _MAX_TOTAL_LATENCY_MS = 15000
    _MIN_WORKFLOW_ROI = 0.00002

    # Execute chain
    current_prompt = input_data["prompt"]
    steps_results = []
    total_cost = 0.0
    total_latency_ms = 0

    # ─── WORKFLOW GOVERNOR TRACKERS ───
    _current_depth = 0
    _expansion_count = 0
    _accumulated_cost_usd = 0.0
    _accumulated_revenue_usd = 0.0
    _accumulated_latency_ms = 0

    for step_idx, step_config in enumerate(workflow_steps):
        step_id = generate_request_id()
        step_start = _time.monotonic()

        required_capability = step_config.get("required_capability", "")
        task_type = step_config.get("task_type", "")

        logger.info(
            f"WORKFLOW_STEP_START "
            f"workflow_id={workflow_id} step={step_idx + 1}/{len(workflow_steps)} "
            f"capability={required_capability} step_id={step_id}"
        )

        # Match service for this step
        matched_service = await match_service(task_type=task_type, required_capability=required_capability)

        if not matched_service:
            logger.warning(
                f"WORKFLOW_FAIL "
                f"workflow_id={workflow_id} step={step_idx + 1} "
                f"reason=NO_MATCH capability={required_capability}"
            )
            return JSONResponse(
                status_code=404,
                content={
                    "error": f"No matching service for step {step_idx + 1}",
                    "step": step_idx + 1,
                    "required_capability": required_capability,
                    "workflow_id": workflow_id,
                    "completed_steps": steps_results,
                },
            )

        target_agent_id = matched_service["agent_id"]
        target_endpoint = matched_service["endpoint"] or "/v1/inference"
        pricing_tier = matched_service["pricing_tier"]
        task_price = await _resolve_price_for_tier(pricing_tier)

        # Build prompt: original + previous result context
        if steps_results:
            prev_result = steps_results[-1].get("result", {}).get("response", "")
            enriched_prompt = f"{current_prompt}\n\n[Previous step result]: {prev_result[:500]}"
        else:
            enriched_prompt = current_prompt

        internal_payload = {
            "prompt": enriched_prompt,
            "max_tokens": step_config.get("max_tokens", input_data.get("max_tokens", 100)),
            "meta": {"agent_id": target_agent_id},
            "task": {
                "complexity": pricing_tier,
                "constraints": {"cost_usd": task_price},
            },
        }

        # Execute via internal HTTP call
        try:
            import httpx
            async with httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)) as client:
                internal_resp = await client.post(
                    f"http://127.0.0.1:8080{target_endpoint}",
                    json=internal_payload,
                    headers={
                        "X-Internal-Key": "hermes-mcp-internal-v1",
                        "Content-Type": "application/json",
                    },
                )
            step_latency_ms = int((_time.monotonic() - step_start) * 1000)

            if internal_resp.status_code != 200:
                _err_body = internal_resp.text[:300]
                logger.warning(
                    f"WORKFLOW_STEP_FAIL "
                    f"workflow_id={workflow_id} step={step_idx + 1} "
                    f"service={matched_service['service_id']} "
                    f"http_status={internal_resp.status_code}"
                )
                return JSONResponse(
                    status_code=internal_resp.status_code,
                    content={
                        "error": f"Step {step_idx + 1} execution failed",
                        "step": step_idx + 1,
                        "service_id": matched_service["service_id"],
                        "detail": _err_body,
                        "workflow_id": workflow_id,
                        "completed_steps": steps_results,
                    },
                )

            result = internal_resp.json()
            step_cost = result.get("cost_usd", 0.0)
            total_cost += step_cost
            total_latency_ms += step_latency_ms

            step_result = {
                "step": step_idx + 1,
                "service_id": matched_service["service_id"],
                "agent_id": target_agent_id,
                "pricing_tier": pricing_tier,
                "capability": required_capability,
                "latency_ms": step_latency_ms,
                "cost_usd": step_cost,
                "result": {
                    "response": result.get("response", ""),
                    "payment_status": result.get("payment_status"),
                },
            }
            steps_results.append(step_result)

            # ─── WORKFLOW GOVERNOR: update accumulators after each step ───
            _current_depth += 1
            _accumulated_cost_usd += step_cost
            _accumulated_revenue_usd += _pricing_tier_to_revenue(pricing_tier)
            _accumulated_latency_ms += step_latency_ms

            # ─── STEP EXPANSION (Value Density Injection) ───
            # If high-confidence + medium/high tier + not at max steps, inject follow-up
            _step_confidence = result.get("confidence", 0.0)
            if not isinstance(_step_confidence, (int, float)):
                _step_confidence = 0.0
            _step_pricing_tier = pricing_tier
            _should_expand = (
                _step_confidence >= 0.85
                and _step_pricing_tier in ("medium", "high")
                and step_idx < 4  # 0-indexed, so <4 means step 5 or earlier (max step_idx 4 = step 5)
            )

            # ─── GOVERNOR CHECK: block expansion if any limit exceeded ───
            if _should_expand:
                _roi = _accumulated_revenue_usd - _accumulated_cost_usd
                if _current_depth >= _MAX_WORKFLOW_DEPTH:
                    _should_expand = False
                    logger.info(
                        f"EXPANSION_BLOCKED reason=MAX_DEPTH depth={_current_depth} "
                        f"roi={_roi:.6f} latency={_accumulated_latency_ms}ms "
                        f"workflow_id={workflow_id}"
                    )
                elif _expansion_count >= _MAX_EXPANSION_STEPS:
                    _should_expand = False
                    logger.info(
                        f"EXPANSION_BLOCKED reason=MAX_EXPANSIONS count={_expansion_count} "
                        f"roi={_roi:.6f} latency={_accumulated_latency_ms}ms "
                        f"workflow_id={workflow_id}"
                    )
                elif _accumulated_latency_ms >= _MAX_TOTAL_LATENCY_MS:
                    _should_expand = False
                    logger.info(
                        f"EXPANSION_BLOCKED reason=MAX_LATENCY "
                        f"latency={_accumulated_latency_ms}ms "
                        f"roi={_roi:.6f} workflow_id={workflow_id}"
                    )
                elif _roi < _MIN_WORKFLOW_ROI:
                    _should_expand = False
                    logger.info(
                        f"EXPANSION_BLOCKED reason=MIN_ROI roi={_roi:.6f} "
                        f"depth={_current_depth} latency={_accumulated_latency_ms}ms "
                        f"workflow_id={workflow_id}"
                    )

            if _should_expand:
                logger.info(
                    f"WORKFLOW_EXPANSION_TRIGGERED step={step_idx + 1} "
                    f"confidence={_step_confidence:.2f} tier={_step_pricing_tier} "
                    f"workflow_id={workflow_id}"
                )
                # Build follow-up step
                _fu_step_id = generate_request_id()
                _fu_start = _time.monotonic()
                _fu_required_capability = "value_enhancement"
                _fu_prompt = (
                    f"Enhance and extend the following result with additional insights, "
                    f"deeper analysis, or actionable recommendations:\n\n"
                    f"{result.get('response', '')[:800]}"
                )
                # Match service for follow-up
                _fu_matched = await match_service(
                    task_type="enhancement",
                    required_capability=_fu_required_capability,
                )
                if _fu_matched:
                    _fu_agent_id = _fu_matched["agent_id"]
                    _fu_endpoint = _fu_matched["endpoint"] or "/v1/inference"
                    _fu_pt = _fu_matched["pricing_tier"]
                    _fu_price = await _resolve_price_for_tier(_fu_pt)
                    _fu_internal_payload = {
                        "prompt": _fu_prompt,
                        "max_tokens": 1024,
                        "meta": {"agent_id": _fu_agent_id, "internal_call": True},
                        "task": {
                            "complexity": _fu_pt,
                            "constraints": {"cost_usd": _fu_price},
                        },
                    }
                    try:
                        import httpx as _fu_httpx
                        async with _fu_httpx.AsyncClient(
                            timeout=_fu_httpx.Timeout(connect=5.0, read=60.0, write=10.0, pool=5.0)
                        ) as _fu_client:
                            _fu_resp = await _fu_client.post(
                                f"http://127.0.0.1:8080{_fu_endpoint}",
                                json=_fu_internal_payload,
                                headers={
                                    "X-Internal-Key": "hermes-mcp-internal-v1",
                                    "Content-Type": "application/json",
                                },
                            )
                        _fu_latency_ms = int((_time.monotonic() - _fu_start) * 1000)
                        if _fu_resp.status_code == 200:
                            _fu_result = _fu_resp.json()
                            _fu_cost = _fu_result.get("cost_usd", 0.0)
                            total_cost += _fu_cost
                            total_latency_ms += _fu_latency_ms
                            _fu_step_result = {
                                "step": len(steps_results) + 1,
                                "service_id": _fu_matched["service_id"],
                                "agent_id": _fu_agent_id,
                                "pricing_tier": _fu_pt,
                                "capability": _fu_required_capability,
                                "latency_ms": _fu_latency_ms,
                                "cost_usd": _fu_cost,
                                "result": {
                                    "response": _fu_result.get("response", ""),
                                    "payment_status": _fu_result.get("payment_status"),
                                },
                                "expansion": True,
                                "derived_from_step": step_idx + 1,
                            }
                            steps_results.append(_fu_step_result)
                            # Update governor trackers for expansion step
                            _expansion_count += 1
                            _current_depth += 1
                            _accumulated_cost_usd += _fu_cost
                            _accumulated_revenue_usd += _pricing_tier_to_revenue(_fu_pt)
                            _accumulated_latency_ms += _fu_latency_ms
                            # Economics for follow-up
                            _fu_revenue = _pricing_tier_to_revenue(_fu_pt)
                            _fu_provider_cost = _fu_result.get("estimated_cost", _fu_result.get("cost_usd", 0.0))
                            if not isinstance(_fu_provider_cost, (int, float)):
                                _fu_provider_cost = 0.0
                            log_economic_event(
                                event_id=f"econ_{_fu_step_id}",
                                request_id=_fu_step_id,
                                agent_id=caller_agent_id,
                                service_id=_fu_matched["service_id"],
                                pricing_tier=_fu_pt,
                                revenue_usd=_fu_revenue,
                                provider_cost_usd=_fu_provider_cost,
                                latency_ms=_fu_latency_ms,
                            )
                            logger.info(
                                f"WORKFLOW_EXPANSION_STEP_SUCCESS "
                                f"workflow_id={workflow_id} step={step_idx + 1} "
                                f"fu_service={_fu_matched['service_id']} "
                                f"fu_cost={_fu_cost:.6f} fu_latency_ms={_fu_latency_ms}"
                            )
                        else:
                            logger.warning(
                                f"WORKFLOW_EXPANSION_STEP_FAIL "
                                f"workflow_id={workflow_id} step={step_idx + 1} "
                                f"http_status={_fu_resp.status_code}"
                            )
                    except Exception as _fu_e:
                        logger.warning(
                            f"WORKFLOW_EXPANSION_STEP_ERROR "
                            f"workflow_id={workflow_id} step={step_idx + 1} "
                            f"error={str(_fu_e)[:200]}"
                        )
                else:
                    logger.info(
                        f"WORKFLOW_EXPANSION_NO_MATCH "
                        f"workflow_id={workflow_id} step={step_idx + 1} "
                        f"capability={_fu_required_capability}"
                    )

            # Inject result for next step
            current_prompt = result.get("response", "")

            logger.info(
                f"WORKFLOW_STEP_SUCCESS "
                f"workflow_id={workflow_id} step={step_idx + 1} "
                f"service={matched_service['service_id']} "
                f"cost={step_cost:.6f} latency_ms={step_latency_ms}"
            )

            # ─── Economics Logging (per step) ───
            _step_revenue = _pricing_tier_to_revenue(pricing_tier)
            _step_provider_cost = result.get("estimated_cost", result.get("cost_usd", 0.0))
            if not isinstance(_step_provider_cost, (int, float)):
                _step_provider_cost = 0.0
            log_economic_event(
                event_id=f"econ_{step_id}",
                request_id=step_id,
                agent_id=caller_agent_id,
                service_id=matched_service["service_id"],
                pricing_tier=pricing_tier,
                revenue_usd=_step_revenue,
                provider_cost_usd=_step_provider_cost,
                latency_ms=step_latency_ms,
            )

            # Inject result for next step
            current_prompt = result.get("response", "")

        except Exception as e:
            logger.error(
                f"WORKFLOW_FAIL "
                f"workflow_id={workflow_id} step={step_idx + 1} "
                f"error={str(e)[:200]}"
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": f"Step {step_idx + 1} internal error",
                    "step": step_idx + 1,
                    "detail": str(e)[:200],
                    "workflow_id": workflow_id,
                    "completed_steps": steps_results,
                },
            )

    total_elapsed_ms = int((_time.monotonic() - _wf_start) * 1000)

    # Aggregate revenue from step pricing tiers
    _tier_prices = {"simple": 0.02, "medium": 0.04, "high": 0.08}
    total_revenue = sum(
        _tier_prices.get(s["pricing_tier"], 0.02) for s in steps_results
    )
    total_profit = total_revenue - total_cost

    logger.info(
        f"WORKFLOW_COMPLETE "
        f"workflow_id={workflow_id} steps={len(workflow_steps)} "
        f"total_cost={total_cost:.6f} total_latency_ms={total_elapsed_ms}"
    )

    # ─── Decision Output Contract ───
    from app.decision_contract import build_decision_output

    return build_decision_output(
        decision_id=workflow_id,
        agent_id=caller_agent_id,
        request_id=workflow_id,
        input_summary=input_data.get("prompt", ""),
        decision_type="action",
        value_output={
            "label": "workflow_complete",
            "confidence": 1.0,
            "risk_score": 0.0,
            "utility_score": 1.0,
            "steps_completed": len(steps_results),
            "total_steps": len(workflow_steps),
            "final_result": steps_results[-1]["result"]["response"] if steps_results else "",
        },
        monetization={
            "tier": "workflow",
            "price_usd": round(total_revenue, 6),
            "cost_usd": round(total_cost, 6),
            "profit_usd": round(total_profit, 6),
        },
        workflow_meta={
            "steps_executed": len(steps_results),
            "total_latency_ms": total_elapsed_ms,
        },
        payment={
            "status": "charged",
            "provider": "openrouter",
        },
    )


# ─── PUBLIC A2A CONTRACT LAYER ───

def build_public_manifest() -> dict:
    """
    Build a standardized, machine-readable public manifest for A2A discovery.
    Source: agent_services table (active services only).
    """
    conn = _get_db()
    rows = conn.execute("""
        SELECT service_id, service_name, capabilities, pricing_tier, endpoint, tags
        FROM agent_services WHERE is_active = 1
        ORDER BY created_at DESC
    """).fetchall()
    conn.close()

    capabilities = []
    for row in rows:
        caps = [c.strip() for c in (row[2] or "").split(",") if c.strip()]
        tags = [t.strip() for t in (row[5] or "").split(",") if t.strip()]
        capabilities.append({
            "service_id": row[0],
            "service_name": row[1],
            "capabilities": caps,
            "pricing_tier": row[3],
            "endpoint": row[4] or "/v1/inference",
            "tags": tags,
        })

    return {
        "network": "HALIMA-A2A",
        "version": "1.0",
        "base_url": "http://178.105.35.170:8080",
        "authentication": {
            "type": "X-API-KEY",
            "header": "X-API-KEY",
            "description": "Obtain an API key by registering as an agent. Include in all requests.",
        },
        "capabilities": capabilities,
        "workflow_support": True,
        "auto_execute_support": True,
        "endpoints": {
            "manifest": "/v1/a2a/manifest",
            "well_known": "/.well-known/agent.json",
            "services_list": "/v1/services",
            "service_register": "/v1/services/register",
            "inference": "/v1/inference",
            "agent_execute": "/v1/agent/execute",
            "agent_auto_execute": "/v1/agent/auto-execute",
            "agent_workflow": "/v1/agent/workflow",
        },
    }


# Separate routers for public contract layer
a2a_manifest_router = APIRouter(prefix="/v1/a2a", tags=["A2A Contract"])
well_known_router = APIRouter(tags=["Discovery"])


@a2a_manifest_router.get("/manifest")
async def get_a2a_manifest():
    """GET /v1/a2a/manifest — Public A2A contract manifest for agent discovery."""
    logger.info("PUBLIC_MANIFEST_REQUEST")
    return build_public_manifest()


@well_known_router.get("/.well-known/agent.json")
async def get_well_known_agent():
    """GET /.well-known/agent.json — Standard agent discovery endpoint."""
    logger.info("WELL_KNOWN_AGENT_REQUEST")
    return build_public_manifest()


# ═══════════════════════════════════════════════════════════════
# ECONOMICS LAYER — Profit tracking for A2A executions
# ═══════════════════════════════════════════════════════════════

_ECONOMICS_DB_PATH = Path(__file__).parent / "economics.db"
_econ_lock = threading.Lock()


def _get_econ_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_ECONOMICS_DB_PATH), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS economic_events (
            event_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            service_id TEXT NOT NULL,
            pricing_tier TEXT DEFAULT 'simple',
            revenue_usd REAL NOT NULL DEFAULT 0.0,
            provider_cost_usd REAL NOT NULL DEFAULT 0.0,
            profit_usd REAL NOT NULL DEFAULT 0.0,
            latency_ms INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    return conn


def log_economic_event(
    event_id: str,
    request_id: str,
    agent_id: str,
    service_id: str,
    pricing_tier: str,
    revenue_usd: float,
    provider_cost_usd: float,
    latency_ms: int,
) -> None:
    """Record an economic event after successful A2A execution."""
    profit_usd = revenue_usd - provider_cost_usd
    with _econ_lock:
        conn = _get_econ_db()
        try:
            conn.execute(
                """INSERT INTO economic_events 
                   (event_id, request_id, agent_id, service_id, pricing_tier,
                    revenue_usd, provider_cost_usd, profit_usd, latency_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (event_id, request_id, agent_id, service_id, pricing_tier,
                 revenue_usd, provider_cost_usd, profit_usd, latency_ms),
            )
            conn.commit()
            logger.info(
                f"ECONOMIC_EVENT_RECORDED "
                f"event_id={event_id} agent={agent_id} service={service_id} "
                f"revenue=${revenue_usd:.6f} cost=${provider_cost_usd:.6f} "
                f"profit=${profit_usd:.6f} latency={latency_ms}ms"
            )
        finally:
            conn.close()


def _pricing_tier_to_revenue(tier: str) -> float:
    """Map pricing tier to charged price."""
    prices = {"simple": 0.02, "medium": 0.04, "high": 0.08}
    return prices.get(tier, 0.02)


# ─── Economics Router ───
economics_router = APIRouter(prefix="/v1/economics", tags=["Economics"])


@economics_router.get("/summary")
async def get_economics_summary():
    """
    GET /v1/economics/summary
    Returns aggregate economic metrics for the A2A network.
    """
    conn = _get_econ_db()
    try:
        # Totals
        row = conn.execute("""
            SELECT 
                COUNT(*) as request_count,
                COALESCE(SUM(revenue_usd), 0) as total_revenue,
                COALESCE(SUM(provider_cost_usd), 0) as total_cost,
                COALESCE(SUM(profit_usd), 0) as total_profit,
                COALESCE(AVG(latency_ms), 0) as avg_latency
            FROM economic_events
        """).fetchone()

        request_count, total_revenue, total_cost, total_profit, avg_latency = row

        # Most used services
        most_used = conn.execute("""
            SELECT service_id, COUNT(*) as requests, 
                   SUM(revenue_usd) as revenue,
                   SUM(profit_usd) as profit
            FROM economic_events
            GROUP BY service_id
            ORDER BY requests DESC
            LIMIT 5
        """).fetchall()

        # Highest profit services
        top_profit = conn.execute("""
            SELECT service_id, 
                   SUM(profit_usd) as total_profit,
                   AVG(profit_usd) as avg_profit,
                   COUNT(*) as requests
            FROM economic_events
            GROUP BY service_id
            ORDER BY total_profit DESC
            LIMIT 5
        """).fetchall()

        return {
            "totals": {
                "request_count": request_count,
                "total_revenue_usd": round(total_revenue, 6),
                "total_provider_cost_usd": round(total_cost, 6),
                "total_profit_usd": round(total_profit, 6),
                "avg_latency_ms": round(avg_latency, 1),
            },
            "most_used_services": [
                {
                    "service_id": r[0],
                    "requests": r[1],
                    "revenue_usd": round(r[2], 6),
                    "profit_usd": round(r[3], 6),
                }
                for r in most_used
            ],
            "highest_profit_services": [
                {
                    "service_id": r[0],
                    "total_profit_usd": round(r[1], 6),
                    "avg_profit_usd": round(r[2], 6),
                    "requests": r[3],
                }
                for r in top_profit
            ],
        }
    finally:
        conn.close()


@economics_router.get("/service/{service_id}")
async def get_service_economics(service_id: str):
    """
    GET /v1/economics/service/{service_id}
    Returns economic metrics for a specific service.
    """
    conn = _get_econ_db()
    try:
        row = conn.execute("""
            SELECT 
                COUNT(*) as requests,
                COALESCE(SUM(revenue_usd), 0) as revenue,
                COALESCE(SUM(profit_usd), 0) as total_profit,
                COALESCE(AVG(profit_usd), 0) as avg_profit,
                COALESCE(AVG(latency_ms), 0) as avg_latency,
                pricing_tier
            FROM economic_events
            WHERE service_id = ?
            GROUP BY service_id
        """, (service_id,)).fetchone()

        if not row:
            return JSONResponse(
                status_code=404,
                content={"error": "No economic data for service", "service_id": service_id},
            )

        requests, revenue, total_profit, avg_profit, avg_latency, tier = row

        return {
            "service_id": service_id,
            "pricing_tier": tier,
            "requests": requests,
            "revenue_usd": round(revenue, 6),
            "total_profit_usd": round(total_profit, 6),
            "avg_profit_usd": round(avg_profit, 6),
            "avg_latency_ms": round(avg_latency, 1),
        }
    finally:
        conn.close()


# ═══════════════════════════════════════════════════════════════
# ANALYTICS LAYER — Read-only economic behavior analytics
# ═══════════════════════════════════════════════════════════════

analytics_router = APIRouter(prefix="/v1/analytics", tags=["Analytics"])


@analytics_router.get("/workflow-frequency")
async def workflow_frequency():
    """
    GET /v1/analytics/workflow-frequency
    Returns most executed workflow capability chains with counts,
    avg steps, avg profit, and avg latency.
    """
    logger.info("ANALYTICS_QUERY type=workflow-frequency")
    conn = _get_econ_db()
    try:
        # Group by service_id to get per-service workflow stats
        # Since we don't have a dedicated workflow_runs table, we aggregate
        # from economic_events grouped by request_id prefix patterns
        rows = conn.execute("""
            SELECT 
                service_id,
                COUNT(*) as execution_count,
                AVG(profit_usd) as avg_profit,
                AVG(latency_ms) as avg_latency,
                SUM(revenue_usd) as total_revenue,
                SUM(profit_usd) as total_profit,
                pricing_tier
            FROM economic_events
            GROUP BY service_id
            ORDER BY execution_count DESC
            LIMIT 20
        """).fetchall()

        capabilities = []
        for row in rows:
            capabilities.append({
                "service_id": row[0],
                "execution_count": row[1],
                "avg_profit_usd": round(row[2] or 0, 6),
                "avg_latency_ms": round(row[3] or 0, 1),
                "total_revenue_usd": round(row[4] or 0, 6),
                "total_profit_usd": round(row[5] or 0, 6),
                "pricing_tier": row[6] or "simple",
            })

        # Overall workflow stats
        overall = conn.execute("""
            SELECT 
                COUNT(DISTINCT request_id) as total_executions,
                COUNT(DISTINCT service_id) as unique_services,
                AVG(profit_usd) as avg_profit,
                AVG(latency_ms) as avg_latency,
                SUM(profit_usd) as total_profit
            FROM economic_events
        """).fetchone()

        return {
            "capabilities": capabilities,
            "overall": {
                "total_executions": overall[0],
                "unique_services": overall[1],
                "avg_profit_usd": round(overall[2] or 0, 6),
                "avg_latency_ms": round(overall[3] or 0, 1),
                "total_profit_usd": round(overall[4] or 0, 6),
            },
        }
    finally:
        conn.close()


@analytics_router.get("/profit-density")
async def profit_density():
    """
    GET /v1/analytics/profit-density
    Calculates profit density (profit per second) for services
    and workflow chains.
    """
    logger.info("ANALYTICS_QUERY type=profit-density")
    conn = _get_econ_db()
    try:
        # Per-service profit density
        service_rows = conn.execute("""
            SELECT 
                service_id,
                pricing_tier,
                COUNT(*) as request_count,
                SUM(revenue_usd) as total_revenue,
                SUM(profit_usd) as total_profit,
                SUM(latency_ms) as total_latency_ms,
                AVG(profit_usd) as avg_profit,
                AVG(latency_ms) as avg_latency
            FROM economic_events
            GROUP BY service_id
            ORDER BY total_profit DESC
            LIMIT 20
        """).fetchall()

        services = []
        for row in service_rows:
            total_latency_s = (row[5] or 0) / 1000.0
            _pd = (row[4] / total_latency_s) if total_latency_s > 0 else 0.0
            services.append({
                "service_id": row[0],
                "pricing_tier": row[1] or "simple",
                "request_count": row[2],
                "total_revenue_usd": round(row[3] or 0, 6),
                "total_profit_usd": round(row[4] or 0, 6),
                "total_latency_ms": row[5] or 0,
                "avg_profit_usd": round(row[6] or 0, 6),
                "avg_latency_ms": round(row[7] or 0, 1),
                "profit_density_usd_per_sec": round(_pd, 8),
            })

        # Global profit density
        global_row = conn.execute("""
            SELECT 
                SUM(profit_usd) as total_profit,
                SUM(latency_ms) as total_latency_ms,
                AVG(profit_usd) as avg_profit,
                AVG(latency_ms) as avg_latency,
                COUNT(*) as total_requests
            FROM economic_events
        """).fetchone()

        global_latency_s = (global_row[1] or 0) / 1000.0
        global_pd = (global_row[0] / global_latency_s) if global_latency_s > 0 else 0.0

        return {
            "services": services,
            "global": {
                "total_requests": global_row[4] or 0,
                "total_profit_usd": round(global_row[0] or 0, 6),
                "total_latency_ms": global_row[1] or 0,
                "avg_profit_usd": round(global_row[2] or 0, 6),
                "avg_latency_ms": round(global_row[3] or 0, 1),
                "profit_density_usd_per_sec": round(global_pd, 8),
            },
        }
    finally:
        conn.close()


@analytics_router.get("/expansion-efficiency")
async def expansion_efficiency():
    """
    GET /v1/analytics/expansion-efficiency
    Returns expansion step performance: trigger count, success rate,
    added profit/latency, and ROI delta.
    """
    logger.info("ANALYTICS_QUERY type=expansion-efficiency")
    conn = _get_econ_db()
    try:
        # Expansion steps are identified by event_ids starting with "econ_"
        # and having a matching pattern. We look for events that have
        # "expansion" characteristics: same request chain, sequential timing.
        # Since we log expansion steps with econ_{fu_step_id}, we can
        # identify them by checking for events with lower profit (expansion
        # steps use value_enhancement capability).

        # Total expansion-triggered events: identified by checking
        # events that are not the primary workflow step
        total_events = conn.execute(
            "SELECT COUNT(*) FROM economic_events"
        ).fetchone()[0]

        # Get all events ordered by created_at to find expansion patterns
        all_events = conn.execute("""
            SELECT 
                event_id,
                request_id,
                service_id,
                pricing_tier,
                revenue_usd,
                provider_cost_usd,
                profit_usd,
                latency_ms,
                created_at
            FROM economic_events
            ORDER BY created_at DESC
            LIMIT 1000
        """).fetchall()

        # Identify expansion events: events with the same request_id
        # appearing multiple times (multi-step workflow with expansion)
        from collections import Counter, defaultdict
        request_counts = Counter(e[1] for e in all_events)
        multi_step_requests = {rid for rid, cnt in request_counts.items() if cnt > 1}

        expansion_events = []
        primary_events = []
        for evt in all_events:
            rid = evt[1]
            if rid in multi_step_requests:
                # Later events in a multi-step chain are expansion candidates
                expansion_events.append(evt)
            else:
                primary_events.append(evt)

        # Calculate expansion metrics
        total_expansion_candidates = len(expansion_events)
        total_primary = len(primary_events)

        if total_expansion_candidates > 0:
            avg_added_profit = sum(e[6] for e in expansion_events) / total_expansion_candidates
            avg_added_latency = sum(e[7] for e in expansion_events) / total_expansion_candidates
            expansion_revenue = sum(e[4] for e in expansion_events)
            expansion_cost = sum(e[5] for e in expansion_events)
            expansion_profit = expansion_revenue - expansion_cost
        else:
            avg_added_profit = 0.0
            avg_added_latency = 0.0
            expansion_profit = 0.0

        if total_primary > 0:
            primary_revenue = sum(e[4] for e in primary_events)
            primary_cost = sum(e[5] for e in primary_events)
            primary_profit = primary_revenue - primary_cost
            avg_primary_profit = primary_profit / total_primary
        else:
            primary_profit = 0.0
            avg_primary_profit = 0.0

        # ROI delta: profit with expansion vs without
        roi_delta = expansion_profit  # absolute added profit from expansions

        # Top triggering services (services that appear before expansion steps)
        service_expansion_count = defaultdict(int)
        for evt in expansion_events:
            service_expansion_count[evt[2]] += 1

        top_triggers = sorted(
            [{"service_id": sid, "expansion_count": cnt} for sid, cnt in service_expansion_count.items()],
            key=lambda x: x["expansion_count"],
            reverse=True,
        )[:10]

        # Success rate: expansion events with positive profit
        profitable_expansions = sum(1 for e in expansion_events if e[6] > 0)
        expansion_success_rate = (
            profitable_expansions / total_expansion_candidates
            if total_expansion_candidates > 0
            else 0.0
        )

        return {
            "expansion_summary": {
                "total_expansion_steps": total_expansion_candidates,
                "total_primary_steps": total_primary,
                "expansion_success_rate": round(expansion_success_rate, 4),
                "avg_added_profit_usd": round(avg_added_profit, 6),
                "avg_added_latency_ms": round(avg_added_latency, 1),
                "expansion_profit_usd": round(expansion_profit, 6),
                "primary_profit_usd": round(primary_profit, 6),
                "roi_delta_usd": round(roi_delta, 6),
                "avg_primary_profit_usd": round(avg_primary_profit, 6),
            },
            "top_triggering_services": top_triggers,
        }
    finally:
        conn.close()
