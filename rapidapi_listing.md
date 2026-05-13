# RapidAPI Listing — HALIMA Execution API

## Short Description

AI text processing API: summarize, classify, rewrite, and extract JSON from any text. Sub-2s latency at $0.00004/call via DeepSeek V3.

## Long Description

HALIMA Execution API provides four essential text processing tasks through a single, simple REST endpoint. Powered by DeepSeek V3 via OpenRouter, it delivers sub-2-second latency at a fraction of the cost of GPT-4 alternatives.

**What it does:**
- **Summarize**: Condense articles, documents, or any long text into concise summaries
- **Classify**: Categorize text with a single label (sentiment, topic, intent, etc.)
- **Rewrite**: Transform informal or unclear text into professional, polished prose
- **Extract JSON**: Pull structured data from unstructured text as valid JSON

**Why developers choose HALIMA:**
- **1 endpoint, 4 tasks** — No need to manage multiple APIs or prompt templates
- **Sub-2s latency** — Direct inference, no batching, no queues
- **$0.00004/call** — 25x cheaper than GPT-4 Turbo for equivalent tasks
- **Free tier** — 10 calls/day without an API key
- **Prepaid credits** — $5/500, $20/3,000, $50/10,000 calls
- **Full observability** — Every request logged with tokens, cost, latency

**Technical details:**
- Model: DeepSeek V3 (via OpenRouter)
- Auth: API Key (X-API-Key header) or Free Tier
- Rate limits: 30 req/min per agent, 10 free calls/day/IP
- Response format: JSON with task result + usage stats
- Server: Hetzner, Germany (EU data residency)

## Category

**AI / Natural Language Processing / Text Analysis**

Secondary: Developer Tools, Machine Learning

## Pricing Suggestion (RapidAPI)

| Plan | RapidAPI Price | Calls/Month | Cost/Call |
|------|---------------|-------------|-----------|
| Free | $0 | 300 (10/day) | $0 |
| Basic | $5 | 500 | $0.01 |
| Pro | $20 | 3,000 | $0.007 |
| Enterprise | $50 | 10,000 | $0.005 |

**Note:** Actual provider cost is ~$0.00004/call. RapidAPI markup covers platform fees and margin.

## Endpoints

### POST `/v1/execute`

Execute a text processing task.

**Request Body:**
```json
{
  "task": "summarize",
  "text": "Your input text here...",
  "max_tokens": 512
}
```

**Response:**
```json
{
  "task": "summarize",
  "result": "The processed output...",
  "usage": {
    "tokens": 156,
    "cost_usd": 0.000031,
    "latency_ms": 1500
  }
}
```

**Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| task | string | Yes | summarize, classify, rewrite, extract_json |
| text | string | Yes | Input text to process |
| max_tokens | int | No | Override default token limit |

### GET `/v1/execute/health`

Health check and available tasks.

**Response:**
```json
{
  "status": "ok",
  "tasks": ["classify", "extract_json", "rewrite", "summarize"],
  "model": "deepseek/deepseek-chat",
  "max_tokens": 2048,
  "max_cost": 0.05
}
```

## Usage Examples

### cURL — Summarize
```bash
curl -X POST https://halima-execution-api.p.rapidapi.com/v1/execute \
  -H "X-RapidAPI-Key: YOUR_RAPIDAPI_KEY" \
  -H "X-RapidAPI-Host: halima-execution-api.p.rapidapi.com" \
  -H "Content-Type: application/json" \
  -d '{"task":"summarize","text":"Your long text here..."}'
```

### Python
```python
import requests

url = "https://halima-execution-api.p.rapidapi.com/v1/execute"
headers = {
    "X-RapidAPI-Key": "YOUR_RAPIDAPI_KEY",
    "X-RapidAPI-Host": "halima-execution-api.p.rapidapi.com",
    "Content-Type": "application/json"
}
payload = {"task": "classify", "text": "This product is amazing!"}

response = requests.post(url, json=payload, headers=headers)
print(response.json()["result"])  # "Positive"
```

### JavaScript
```javascript
const response = await fetch(
  "https://halima-execution-api.p.rapidapi.com/v1/execute",
  {
    method: "POST",
    headers: {
      "X-RapidAPI-Key": "YOUR_RAPIDAPI_KEY",
      "X-RapidAPI-Host": "halima-execution-api.p.rapidapi.com",
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      task: "extract_json",
      text: "Meeting Jan 15 2026 at 3pm with John"
    })
  }
);
const data = await response.json();
console.log(data.result);
```

## Keywords / Tags

`ai`, `nlp`, `text-processing`, `summarization`, `classification`, `text-rewriting`, `json-extraction`, `deepseek`, `openrouter`, `llm`, `language-model`, `text-analysis`, `sentiment`, `entity-extraction`, `cheap-ai`, `low-latency`, `rest-api`, `developer-tools`, `machine-learning`, `halal-api`

## Target Audience

- Developers building content processing pipelines
- Startups needing cheap AI text processing
- Data scientists extracting structured data from text
- Content platforms needing summarization/classification
- Freelancers automating client work (SEO, content, reports)
- Anyone who finds GPT-4 too expensive for simple text tasks

## Competing APIs on RapidAPI

| API | Cost/Call | Latency | Tasks |
|-----|-----------|---------|-------|
| OpenAI GPT-4 Turbo | $0.001-0.002 | 3-10s | General |
| Cohere Summarize | $0.0005 | 2-5s | Summarize only |
| **HALIMA** | **$0.00004** | **1.5s** | **4 tasks** |

## Launch Plan

1. **Submit to RapidAPI** — Complete listing with all examples above
2. **Set pricing tiers** — Free (300/mo), Basic ($5), Pro ($20), Enterprise ($50)
3. **Verify endpoint** — RapidAPI team tests the API
4. **Go live** — API appears in RapidAPI marketplace
5. **Promote** — Hacker News, Reddit (r/SideProject, r/webdev), Twitter/X, Indie Hackers
