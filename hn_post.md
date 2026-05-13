# Hacker News Post — HALIMA Execution API

## Title

**Show HN: HALIMA — AI text processing API at $0.00004/call (DeepSeek V3)**

## Post Text

---

Hey HN,

I built HALIMA Execution API — a simple REST API that does four text processing tasks (summarize, classify, rewrite, extract_json) in a single endpoint, powered by DeepSeek V3 via OpenRouter.

**The problem I was solving:**

I needed cheap, fast text processing for my trading bot (HALIMA) and other projects. GPT-4 Turbo costs $0.001-0.002 per call and takes 3-10 seconds. Cohere is cheaper but only does summarization. I wanted one endpoint, four tasks, sub-2s latency, and I didn't want to manage prompt templates myself.

**What it does:**

- `summarize` — condense any text to a concise summary
- `classify` — single label classification (sentiment, topic, intent, etc.)
- `rewrite` — professional, clear rewrite of any text
- `extract_json` — pull structured data from unstructured text as valid JSON

**Performance (live benchmarks):**

- Latency: 1.1s - 1.8s average (measured over 3 calls)
- Cost: $0.00004 per call (DeepSeek V3 via OpenRouter)
- Throughput: 30 req/min per agent, 10 free calls/day without API key

**Pricing:**

- Free: 10 calls/day (no API key needed)
- Starter: $5 for 500 calls
- Pro: $20 for 3,000 calls
- Enterprise: $50 for 10,000 calls

**Tech stack:**

- Python + FastAPI
- DeepSeek V3 via OpenRouter
- SQLite for billing, rate limiting, observability
- Hetzner server (Germany, EU data residency)
- A2A (Agent-to-Agent) protocol for autonomous agent billing

**Why it's cheap:**

DeepSeek V3 costs ~$0.0002/1K tokens. Most tasks use 50-200 tokens. That's $0.00001-0.00004 per call. I add a small margin on prepaid plans to cover server costs.

**Architecture:**

One endpoint (`POST /v1/execute`), four task templates, shared inference router with auth/billing/observability. No microservices, no Kubernetes, no complexity. Single server, single database, single API.

**Try it:**

```bash
# Free tier — no API key needed
curl -X POST http://178.105.35.170:8080/v1/execute \
  -H "Content-Type: application/json" \
  -d '{"task":"summarize","text":"Your text here"}'
```

Docs: http://178.105.35.170:8080/docs
Landing page: http://178.105.35.170:8080/v1/execute/page

**What I'd love feedback on:**

1. Is the pricing right? Too cheap? Too expensive?
2. What other task types would you want?
3. Would you use this over GPT-4 for simple text tasks?
4. Any security concerns with the auth approach?

The API is live and ready to use. Free tier works without registration. I'm also preparing a RapidAPI listing for broader distribution.

Built by a solo dev (me) as part of a larger halal-compliant AI infrastructure project. All infrastructure is self-hosted, no AWS/GCP.

---

**HN Tags:** Show HN, API, AI, NLP, DeepSeek, OpenRouter

**Post timing:** Tuesday 10am-12pm EST (peak HN traffic)

**Cross-post to:** r/SideProject, r/webdev, r/SaaS, Indie Hackers, Twitter/X

---

## Technical Details (for HN comments)

### Auth
- X-API-Key header for production use
- X-Internal-Key for service-to-service (A2A)
- Free tier: 10 calls/day/IP without auth

### Rate Limiting
- 30 requests/minute per agent
- $5 daily spend limit per agent
- IP-based tracking for free tier

### Observability
- Every request logged to `/root/.hermes/logs/inference-router.jsonl`
- Fields: request_id, provider, model, tokens, cost, latency, status
- Analytics endpoints: `/v1/analytics/workflow-frequency`, `/v1/analytics/profit-density`, `/v1/analytics/expansion-efficiency`

### Billing
- Prepaid credits via purchase system ($5/500, $20/3000, $50/10000)
- A2A billing with atomic reserve + charge pattern
- SQLite with WAL mode for concurrent access

### Safety
- Max tokens: 2048 (hard cap)
- Max cost: $0.05 (hard cap)
- No retries (single provider, fail fast)
- 60s provider timeout, 65s total request timeout
