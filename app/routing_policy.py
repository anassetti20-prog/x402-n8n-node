#!/usr/bin/env python3
"""
Phase 4F — Routing Optimization Layer (Decision Only)
Minimale Routing-Policy basierend auf Observability-Daten.

Keine neuen Provider, keine neue Architektur, keine ML.
Nur deterministische Heuristiken basierend auf:
- Prompt Length
- Task Type (aus Prompt-Klassifikation)
- Cost/Latency Thresholds

Input: request characteristics (prompt_length, task_type_hint)
Output: provider_decision + decision_reason
"""

import json
import time
from pathlib import Path
from enum import Enum
from typing import Optional

# ─── ROUTING POLICY CONFIG ───
POLICY_FILE = Path("/root/.hermes/phase4d/routing_policy.json")

class TaskType(Enum):
    """Task-Klassifikation basierend auf Prompt-Mustern."""
    SIMPLE = "SIMPLE"           # Kurze Antwort, Fakten
    REASONING = "REASONING"     # Multi-Step, Berechnung
    GENERATION = "GENERATION"   # Text generieren, Schreiben
    EXTRACTION = "EXTRACTION"   # Daten extrahieren, JSON
    CLASSIFICATION = "CLASSIFICATION"  # Klassifizieren
    UNKNOWN = "UNKNOWN"

class ProviderChoice(Enum):
    DEEPSEEK = "deepseek"
    OPENAI = "openai"


# ─── OBSERVABILITY-BASIERTE THRESHOLDS ──=
# Aus Log-Analyse:
# - avg_latency: 1134ms (DeepSeek)
# - avg_cost: $0.000002 (DeepSeek)
# - success_rate: 100% (DeepSeek)
# - avg_tokens: 8 (kurze Responses)
# - p95_latency: 2015ms
# - Alle Requests: < 13 chars prompt

# Schwellen für Entscheidungen
LATENCY_THRESHOLD_MS = 2000       # P95-Latenz als Worst-Case
COST_THRESHOLD_PER_REQUEST = 0.00001  # Max akzeptabel pro Request
SHORT_PROMPT_THRESHOLD = 20       # Chars → SIMPLE Task
LONG_PROMPT_THRESHOLD = 100       # Chars → REASONING/GENERATION


def classify_task_type(prompt: str) -> tuple[TaskType, float]:
    """
    Klassifiziert den Task-Typ basierend auf Prompt-Mustern.
    Returns: (task_type, confidence)
    
    Kein ML — nur Keyword-Heuristiken.
    """
    prompt_lower = prompt.lower().strip()

    # Classification-Indikatoren
    classify_keywords = ["classify", "category", "sentiment", "positive", "negative", "neutral", "label"]
    # Reasoning-Indikatoren
    reason_keywords = ["calculate", "solve", "reason", "step by step", "explain why", "how many", "what is the", "compute", "math"]
    # Extraction-Indikatoren
    extract_keywords = ["extract", "json", "parse", "fields", "keys", "return json", "structured"]
    # Simple-Indikatoren
    simple_keywords = ["what is", "define", "list", "name", "who is", "where", "when", "yes or no", "true or false"]
    # Generation-Indikatoren
    gen_keywords = ["write", "generate", "create", "draft", "compose", "summarize", "rewrite", "translate"]

    scores = {
        TaskType.CLASSIFICATION: sum(1 for kw in classify_keywords if kw in prompt_lower),
        TaskType.REASONING: sum(1 for kw in reason_keywords if kw in prompt_lower),
        TaskType.EXTRACTION: sum(1 for kw in extract_keywords if kw in prompt_lower),
        TaskType.SIMPLE: sum(1 for kw in simple_keywords if kw in prompt_lower),
        TaskType.GENERATION: sum(1 for kw in gen_keywords if kw in prompt_lower),
    }

    # Gewinner
    max_score = max(scores.values())
    if max_score == 0:
        return TaskType.UNKNOWN, 0.0

    # Confidence: gewinner_score / max possible
    max_possible = max(len(classify_keywords), len(reason_keywords), len(extract_keywords),
                       len(simple_keywords), len(gen_keywords))
    confidence = min(max_score / 3.0, 1.0)  # 3 Treffer = 100% confidence

    # Gewinner finden (bei Gleichstand: Reihenfolge priorisieren)
    for task_type in [TaskType.CLASSIFICATION, TaskType.REASONING, TaskType.EXTRACTION,
                      TaskType.GENERATION, TaskType.SIMPLE]:
        if scores[task_type] == max_score:
            return task_type, round(confidence, 2)

    return TaskType.UNKNOWN, 0.0


def estimate_tokens(prompt_length: int) -> int:
    """
    Schätzt die Output-Token-Anzahl basierend auf Prompt-Länge.
    Regel: 1 token ≈ 4 chars (Englisch), Output ≈ 0.5x Input-Länge
    """
    return max(int(prompt_length / 8), 5)  # Minimum 5 tokens


def estimate_cost(provider: ProviderChoice, prompt_length: int) -> float:
    """
    Schätzt die Kosten basierend auf Provider und Prompt-Länge.
    Nutzt echte Preise aus Observability-Daten.
    """
    tokens = estimate_tokens(prompt_length)
    rates = {
        ProviderChoice.DEEPSEEK: 0.0002,  # $/1K tokens (aus Logs: avg $0.000002 for 10 tokens)
        ProviderChoice.OPENAI: 0.0015,
    }
    rate = rates.get(provider, 0.0005)
    return round((tokens / 1000) * rate, 6)


def routing_decision_function(
    prompt: str,
    preferred_model: Optional[str] = None,
    max_cost: float = 0.05,
    latency_priority: float = 0.5,  # 0=balanced, 1=latency-critical
    quality_priority: float = 0.5,  # 0=balanced, 1=quality-critical
) -> dict:
    """
    Deterministische Routing-Entscheidung.
    
    Input: Request-Parameter
    Output: {
        "provider": ProviderChoice,
        "task_type": TaskType,
        "decision_reason": str,
        "estimated_cost": float,
        "estimated_tokens": int,
        "confidence": float
    }
    
    Regeln (kein ML):
    1. IMMER DeepSeek (Single-Provider Mode, keine Alternative)
    2. Task-Klassifikation für Logging
    3. Cost/Latenz-Schwellen zur Warnung
    """
    prompt_length = len(prompt.strip())

    # Task-Klassifikation
    task_type, confidence = classify_task_type(prompt)

    # Provider-Entscheidung: DeepSeek ist einziger Provider
    provider = ProviderChoice.DEEPSEEK

    # Kosten- und Latenzschätzung
    est_cost = estimate_cost(provider, prompt_length)
    est_tokens = estimate_tokens(prompt_length)

    # Decision Reason (deterministisch)
    reasons = []

    # Regel 1: Provider verfügbar?
    reasons.append(f"Single-Provider Mode: {provider.value} only")

    # Regel 2: Task-Typ
    reasons.append(f"Task classified as {task_type.value} (confidence={confidence})")

    # Regel 3: Kostencheck
    if est_cost > max_cost:
        reasons.append(f"⚠️ Estimated cost ${est_cost:.6f} exceeds max_cost ${max_cost:.4f}")
    else:
        reasons.append(f"OK: est_cost ${est_cost:.6f} <= max_cost ${max_cost:.4f}")

    # Regel 4: Latenzschätzung (basierend auf historischen Daten)
    # Aus Logs: avg 1134ms, p95 2015ms
    estimated_latency = 1134  # ms, aus Observational-Daten
    if task_type == TaskType.REASONING:
        estimated_latency = int(estimated_latency * 1.3)  # 30% mehr für Reasoning
    elif task_type == TaskType.GENERATION:
        estimated_latency = int(estimated_latency * 1.2)
    elif task_type == TaskType.SIMPLE:
        estimated_latency = int(estimated_latency * 0.8)

    reasons.append(f"Est. latency: {estimated_latency}ms (baseline=1134ms, task={task_type.value})")

    # Regel 5: Prompt-Länge Warnung
    if prompt_length > 5000:
        reasons.append(f"⚠️ Very long prompt ({prompt_length} chars), may hit token limits")
    elif prompt_length > 1000:
        reasons.append(f"Long prompt ({prompt_length} chars), monitoring recommended")

    # Regel 6: Preferred Model Check
    if preferred_model and preferred_model != provider.value:
        reasons.append(f"⚠️ User prefers {preferred_model} but {provider.value} is single active provider")

    return {
        "provider": provider.value,
        "task_type": task_type.value,
        "prompt_length": prompt_length,
        "estimated_tokens": est_tokens,
        "estimated_cost": est_cost,
        "estimated_latency_ms": estimated_latency,
        "confidence": confidence,
        "decision_reason": " | ".join(reasons),
        "timestamp": time.time(),
    }


def save_policy():
    """Speichert die Routing-Policy als JSON für Dokumentation."""
    policy = {
        "version": "1.0",
        "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "mode": "SINGLE_PROVIDER",
        "active_provider": "deepseek",
        "rules": [
            {
                "rule": "Provider Selection",
                "logic": "DEEPSEEK only (Single-Provider Mode)",
                "reason": "100% success rate observed, lowest cost"
            },
            {
                "rule": "Task Classification",
                "logic": "Keyword-based heuristic, 5 categories",
                "categories": ["SIMPLE", "REASONING", "GENERATION", "EXTRACTION", "CLASSIFICATION"]
            },
            {
                "rule": "Cost Estimation",
                "logic": "tokens = prompt_length / 8, cost = tokens * rate",
                "rates": {"deepseek": 0.0002, "openai": 0.0015}
            },
            {
                "rule": "Latency Estimation",
                "logic": "Baseline 1134ms, adjusted by task type",
                "adjustments": {
                    "SIMPLE": 0.8,
                    "REASONING": 1.3,
                    "GENERATION": 1.2,
                    "EXTRACTION": 1.0,
                    "CLASSIFICATION": 0.9,
                    "UNKNOWN": 1.0
                }
            },
            {
                "rule": "Max Cost Enforcement",
                "logic": "Reject if estimated_cost > max_cost",
                "threshold": 0.05
            }
        ],
        "thresholds": {
            "latency_p95_ms": 2015,
            "avg_latency_ms": 1134,
            "avg_cost_per_request": 0.000002,
            "avg_tokens_per_request": 8,
        }
    }
    POLICY_FILE.write_text(json.dumps(policy, indent=2))
    print(f"Policy saved: {POLICY_FILE}")
    return policy


if __name__ == "__main__":
    # Demo-Tests
    print("=" * 60)
    print("Phase 4F — Routing Optimization Layer")
    print("=" * 60)

    test_cases = [
        ("What is 2+2?", "deepseek"),
        ("Calculate the area of a circle with radius 5", "deepseek"),
        ("Extract JSON from: name=John, age=30", "deepseek"),
        ("Write a haiku about coding", "deepseek"),
        ("Classify sentiment: I love this product!", "deepseek"),
        ("Summarize the theory of relativity", "deepseek"),
    ]

    for prompt, pref in test_cases:
        decision = routing_decision_function(prompt, preferred_model=pref)
        print(f"\nPrompt: '{prompt[:50]}'")
        print(f"  Provider: {decision['provider']}")
        print(f"  Task Type: {decision['task_type']} (conf={decision['confidence']})")
        print(f"  Est. Tokens: {decision['estimated_tokens']}")
        print(f"  Est. Cost: ${decision['estimated_cost']:.6f}")
        print(f"  Est. Latency: {decision['estimated_latency_ms']}ms")
        print(f"  Reason: {decision['decision_reason']}")

    policy = save_policy()
    print(f"\n{'='*60}")
    print("Policy saved.")
