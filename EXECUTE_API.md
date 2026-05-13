# HALIMA Execution API

AI-powered text processing in a single API call.

## Supported Tasks

| Task | Description | Default Max Tokens |
|------|-------------|-------------------|
| `summarize` | Concise summary of input text | 512 |
| `classify` | Single category label | 64 |
| `rewrite` | Professional rewrite | 1024 |
| `extract_json` | Structured JSON extraction | 2048 |

## Quick Start

### 1. Get an API Key
```bash
curl -X POST http://178.105.35.170:8080/register \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com"}'
```

### 2. Call the API
```bash
curl -X POST http://178.105.35.170:8080/v1/execute \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"task": "summarize", "text": "Your text here"}'
```

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/execute` | Execute a task |
| GET | `/v1/execute/health` | Health check |
| GET | `/health` | System health |
| POST | `/register` | Get API key |
| GET | `/credits` | Check remaining credits |

## Auth Methods

- **API Key**: `X-API-Key: your_key` (production)
- **Internal Key**: `X-Internal-Key: key` (service-to-service)
- **Free Tier**: No header needed (10 calls/day/IP)

## Pricing

| Plan | Price | Requests |
|------|-------|----------|
| Starter | $5 | 500 |
| Pro | $20 | 3,000 |
| Enterprise | $50 | 10,000 |
| Free | $0 | 10/day |

## Response Format

```json
{
  "task": "summarize",
  "result": "The summary text...",
  "usage": {
    "tokens": 156,
    "cost_usd": 0.000031,
    "latency_ms": 4123
  }
}
```

## Performance

- **Latency**: ~4 seconds average
- **Cost**: ~$0.00004 per call
- **Model**: DeepSeek V3 via OpenRouter
- **Throughput**: 30 req/min per agent, 5 req/day free tier

## Task Examples

### Summarize
```bash
curl -X POST http://178.105.35.170:8080/v1/execute \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"task":"summarize","text":"Long article text here..."}'
```

### Classify
```bash
curl -X POST http://178.105.35.170:8080/v1/execute \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"task":"classify","text":"This product is amazing, best purchase ever!"}'
```

### Rewrite
```bash
curl -X POST http://178.105.35.170:8080/v1/execute \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"task":"rewrite","text":"hey can u send me the stuff thx"}'
```

### Extract JSON
```bash
curl -X POST http://178.105.35.170:8080/v1/execute \
  -H "X-API-Key: YOUR_KEY" \
  -d '{"task":"extract_json","text":"Meeting Jan 15 2026 at 3pm with John about budget"}'
```

## Error Codes

| Code | Meaning |
|------|---------|
| 400 | Invalid request (missing task/text) |
| 401 | Invalid API key |
| 402 | Insufficient credits |
| 429 | Rate limit exceeded |
| 503 | Provider unavailable |

## Observability

All requests are logged to `/root/.hermes/logs/inference-router.jsonl` with:
- Request ID
- Provider & model used
- Token usage & cost estimate
- Latency
- Success/failure status
