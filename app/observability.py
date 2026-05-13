#!/usr/bin/env python3
"""
Phase 4E — Observability Layer (Minimal, Non-Breaking)
Erweitert inference_router.py Logging um strukturierte JSON-Lines.

Nur additive Änderungen:
- request_id Generierung
- Error-Taxonomy Klassifikation
- Strukturierte Log-Einträge mit Pflichtfelder
- Keine Response-Flow-Änderungen
"""

import json
import uuid
import time
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
from enum import Enum

# ─── ERROR TAXONOMY ───
class ErrorType(Enum):
    """Zentrale Error-Klassifikation für alle Inference-Requests."""
    NONE = "NONE"
    # Client-seitig
    VALIDATION_ERROR = "VALIDATION_ERROR"       # Fehlende/ungültige Eingaben
    RATE_LIMIT = "RATE_LIMIT"                   # Rate-Limit überschritten
    AUTH_ERROR = "AUTH_ERROR"                   # Auth fehlgeschlagen
    # Netzwerk
    TIMEOUT = "TIMEOUT"                         # Request-Timeout
    CONNECTION_ERROR = "CONNECTION_ERROR"       # Verbindungsproblem
    # Provider
    PROVIDER_ERROR = "PROVIDER_ERROR"           # Provider API-Fehler (4xx/5xx)
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"  # Provider nicht erreichbar
    # Config
    CONFIG_ERROR = "CONFIG_ERROR"               # Provider nicht in Whitelist
    COST_EXCEEDED = "COST_EXCEEDED"             # Kostenlimit überschritten
    # Unknown
    UNKNOWN = "UNKNOWN"                         # Nicht klassifizierter Fehler


class RequestStatus(Enum):
    """Request-Status für Logging."""
    SUCCESS = "SUCCESS"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    TIMEOUT = "TIMEOUT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMIT = "RATE_LIMIT"
    AUTH_ERROR = "AUTH_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"


def classify_error(error_str: Optional[str], http_status: Optional[int] = None) -> ErrorType:
    """
    Klassifiziert einen Fehler-String in eine ErrorType-Kategorie.
    Deterministisch, keine ML, keine Heuristik — nur exakte Pattern-Matching.
    """
    if not error_str:
        return ErrorType.NONE

    err_lower = error_str.lower()

    # Config-Fehler
    if "not in whitelist" in err_lower or "provider" in err_lower and "whitelist" in err_lower:
        return ErrorType.CONFIG_ERROR

    # Cost
    if "cost" in err_lower and "exceeds" in err_lower:
        return ErrorType.COST_EXCEEDED

    # Timeout
    if "timeout" in err_lower or "timed out" in err_lower:
        return ErrorType.TIMEOUT

    # Connection
    if "connection" in err_lower or "connect" in err_lower or "reset" in err_lower:
        return ErrorType.CONNECTION_ERROR

    # HTTP-Status-basiert
    if http_status:
        if http_status == 429:
            return ErrorType.RATE_LIMIT
        elif http_status in (401, 403):
            return ErrorType.AUTH_ERROR
        elif http_status == 400:
            return ErrorType.VALIDATION_ERROR
        elif http_status >= 500:
            return ErrorType.PROVIDER_ERROR
        elif http_status >= 400:
            return ErrorType.PROVIDER_ERROR

    # Provider-Fehler (HTTP Error im Text)
    if "http" in err_lower and any(str(s) in err_lower for s in [400, 401, 403, 404, 429, 500, 502, 503, 504]):
        return ErrorType.PROVIDER_ERROR

    return ErrorType.UNKNOWN


def determine_status(success: bool, error_type: ErrorType) -> RequestStatus:
    """Bestimmt den Request-Status basierend auf Success und ErrorType."""
    if success:
        return RequestStatus.SUCCESS
    mapping = {
        ErrorType.VALIDATION_ERROR: RequestStatus.VALIDATION_ERROR,
        ErrorType.RATE_LIMIT: RequestStatus.RATE_LIMIT,
        ErrorType.AUTH_ERROR: RequestStatus.AUTH_ERROR,
        ErrorType.TIMEOUT: RequestStatus.TIMEOUT,
        ErrorType.PROVIDER_ERROR: RequestStatus.PROVIDER_ERROR,
        ErrorType.PROVIDER_UNAVAILABLE: RequestStatus.PROVIDER_ERROR,
        ErrorType.CONFIG_ERROR: RequestStatus.CONFIG_ERROR,
        ErrorType.COST_EXCEEDED: RequestStatus.VALIDATION_ERROR,
        ErrorType.CONNECTION_ERROR: RequestStatus.TIMEOUT,
        ErrorType.UNKNOWN: RequestStatus.PROVIDER_ERROR,
        ErrorType.NONE: RequestStatus.SUCCESS,
    }
    return mapping.get(error_type, RequestStatus.PROVIDER_ERROR)


def generate_request_id() -> str:
    """Generiert eine eindeutige Request-ID."""
    return f"req_{uuid.uuid4().hex[:12]}_{int(time.time())}"


def build_observability_log(
    request_id: str,
    provider_used: Optional[str],
    model_used: Optional[str],
    latency_ms: int,
    cost_estimate: float,
    tokens_used: int,
    prompt_length: int,
    success: bool,
    error_type: ErrorType,
    status: RequestStatus,
    error_detail: Optional[str] = None,
    http_status: Optional[int] = None,
    preferred_model: Optional[str] = None,
) -> dict:
    """
    Baut einen strukturierten Observability-Log-Eintrag.
    Alle Pflichtfelder sind immer vorhanden.
    """
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "provider_used": provider_used,
        "model_used": model_used,
        "latency_ms": latency_ms,
        "cost_estimate": cost_estimate,
        "tokens_used": tokens_used,
        "prompt_length": prompt_length,
        "status": status.value,
        "error_type": error_type.value if error_type != ErrorType.NONE else None,
        "error_detail": error_detail if error_type != ErrorType.NONE else None,
        "http_status": http_status,
        "preferred_model": preferred_model,
    }
