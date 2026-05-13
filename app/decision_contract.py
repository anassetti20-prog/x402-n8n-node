"""
Decision Output Contract — Structured decision schema for A2A systems.

Provides a unified output format for any A2A decision, analysis, score,
or recommendation. Designed to be consumed by external agents, billing
systems, and economics tracking.

Usage:
    from app.decision_contract import build_decision_output, DecisionType

    result = build_decision_output(
        decision_id="dec_abc123",
        agent_id="agent-001",
        request_id="req_xyz789",
        input_summary="Sentiment analysis of user review",
        decision_type=DecisionType.ANALYSIS,
        value_output={"label": "positive", "confidence": 0.92, "risk_score": 0.05, "utility_score": 0.88},
        monetization={"tier": "medium", "price_usd": 0.04, "cost_usd": 0.00003, "profit_usd": 0.03997},
        workflow_meta={"steps_executed": 3, "latency_ms": 4500},
        payment={"status": "charged", "provider": "openrouter"},
    )
"""

from enum import Enum
from typing import Any, Optional


class DecisionType(str, Enum):
    """Classification of the decision output type."""
    ANALYSIS = "analysis"
    ACTION = "action"
    SCORE = "score"
    RECOMMENDATION = "recommendation"


def build_decision_output(
    decision_id: str,
    agent_id: str,
    request_id: str,
    input_summary: str,
    decision_type: str | DecisionType,
    value_output: dict[str, Any],
    monetization: dict[str, Any],
    workflow_meta: dict[str, Any],
    payment: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a structured decision output contract.

    Args:
        decision_id:   Unique identifier for this decision.
        agent_id:      Agent that produced the decision.
        request_id:    Original request identifier.
        input_summary: Human-readable summary of the input.
        decision_type: One of 'analysis', 'action', 'score', 'recommendation'.
        value_output:  Decision payload — must contain at least one of:
                         label, confidence, risk_score, utility_score.
        monetization:  Economic data — tier, price_usd, cost_usd, profit_usd.
        workflow_meta: Execution metadata — steps_executed, latency_ms.
        payment:       Payment state — status, provider.

    Returns:
        Structured dict conforming to the Decision Output Contract.
    """
    # Normalize decision_type
    if isinstance(decision_type, DecisionType):
        decision_type = decision_type.value

    # Validate decision_type
    valid_types = {t.value for t in DecisionType}
    if decision_type not in valid_types:
        decision_type = DecisionType.ANALYSIS.value

    # Build value_output with defaults for missing keys
    _value = {
        "label": value_output.get("label", ""),
        "confidence": value_output.get("confidence", 0.0),
        "risk_score": value_output.get("risk_score", 0.0),
        "utility_score": value_output.get("utility_score", 0.0),
    }
    # Include any extra keys from caller
    for k, v in value_output.items():
        if k not in _value:
            _value[k] = v

    # Build monetization with defaults
    _monetization = {
        "tier": monetization.get("tier", "simple"),
        "price_usd": monetization.get("price_usd", 0.0),
        "cost_usd": monetization.get("cost_usd", 0.0),
        "profit_usd": monetization.get("profit_usd", 0.0),
    }
    for k, v in monetization.items():
        if k not in _monetization:
            _monetization[k] = v

    # Build workflow_meta with defaults
    _workflow = {
        "steps_executed": workflow_meta.get("steps_executed", 1),
        "latency_ms": workflow_meta.get("latency_ms", 0),
    }
    for k, v in workflow_meta.items():
        if k not in _workflow:
            _workflow[k] = v

    # Build payment with defaults
    _payment = {
        "status": payment.get("status", "pending"),
        "provider": payment.get("provider", "openrouter"),
    }
    for k, v in payment.items():
        if k not in _payment:
            _payment[k] = v

    return {
        "decision_id": decision_id,
        "agent_id": agent_id,
        "request_id": request_id,
        "input_summary": input_summary,
        "decision_type": decision_type,
        "value_output": _value,
        "monetization": _monetization,
        "workflow_meta": _workflow,
        "payment": _payment,
    }
