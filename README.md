# @anassetti20-prog/n8n-nodes-x402-api

[![npm version](https://img.shields.io/npm/v/@anassetti20-prog%2Fn8n-nodes-x402-api.svg)](https://www.npmjs.com/package/@anassetti20-prog/n8n-nodes-x402-api)

**Pay-per-use AI services via USDC micropayments on Base chain.**
An n8n community node for the x402 API — a collection of utility AI tools you pay for per request with USDC.

---

## Features

- **14 services** — from code analysis to QR code generation
- **Pay-per-use** — $0.01–$0.02 USDC per request on Base chain (no subscriptions)
- **Two payment modes**: Internal API key (server-side) or manual TX hash (public nodes)
- **Halal-compliant** — designed for Sharia-friendly workflows

### Available Services

| Service | Price | Description |
|---------|-------|-------------|
| Halal Screening | $0.01 | Check if a cryptocurrency is Sharia-compliant |
| Web Search | $0.01 | Search the web for information |
| Code Analysis | $0.01 | Analyze source code for bugs and security issues |
| Data Processing | $0.01 | Transform, filter, validate structured data |
| Translation | $0.01 | Translate text between languages |
| Text Generation | $0.02 | Generate AI text in various styles |
| UUID Generator | $0.01 | Generate UUIDs (v4) |
| Hash Generator | $0.01 | Generate cryptographic hashes |
| Base64 Process | $0.01 | Encode or decode Base64 |
| Password Generator | $0.01 | Generate secure random passwords |
| Text Statistics | $0.01 | Get detailed text statistics |
| JSON Processor | $0.01 | Validate, format, or minify JSON |
| QR Code Generator | $0.01 | Generate QR codes |
| Sentiment Analysis | $0.01 | Analyze sentiment of text |

---

## Installation

### Via n8n Community Nodes

1. Go to **Settings → Community Nodes** in your n8n instance
2. Enter `@anassetti20-prog/n8n-nodes-x402-api` as the package name
3. Click **Install**

### Via npm

```bash
npm install @anassetti20-prog/n8n-nodes-x402-api
```

---

## Credentials

The node requires **x402 API** credentials with the following fields:

| Field | Description |
|-------|-------------|
| **API Base URL** | x402 API server URL (default: Cloudflare tunnel URL) |
| **Internal API Key** | *(Optional)* Server-side key to bypass x402 payment |
| **Web3 Private Key** | *(Optional)* Ethereum private key for signing payments |
| **USDC Contract Address** | USDC contract on Base (default: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`) |
| **Base RPC URL** | Base chain RPC endpoint (default: `https://mainnet.base.org`) |

---

## Usage

### Basic Workflow

1. Add an **x402 API** node to your workflow
2. Configure credentials
3. Select a **Service** from the dropdown
4. Fill in the service parameters
5. Choose **Payment Mode**:
   - **Internal Key** — uses an internal API key (no USDC needed, server-side only)
   - **Manual** — send USDC and provide the transaction hash
6. Run the workflow

### Example: Web Search

```
[Webhook Trigger] → [x402 API: Web Search] → [Set] → [Respond]
```

**Parameters:**
- Service: `Web Search`
- Query: `latest AI news`
- Payment Mode: `Manual`
- TX Hash: *(your USDC transaction hash on Base)*

### Example: Halal Screening

```
[Manual Trigger] → [x402 API: Halal Screening] → [IF (halal)] → [...]
```

**Parameters:**
- Service: `Halal Screening`
- Symbol: `BTC`
- Payment Mode: `Internal Key`

---

## Output Format

Each node execution returns a JSON object with:

```json
{
  "service": "web_search",
  "service_name": "Web Search",
  "price_paid": 0.01,
  "statusCode": 200,
  // ... response data from the API
}
```

If payment is required (HTTP 402), the node returns payment instructions instead:

```json
{
  "error": "Payment Required",
  "service": "web_search",
  "price_usdc": 0.01,
  "instruction": "Send 0.01 USDC on Base chain (8453)...",
  "payment": {
    "price_usdc": 0.01,
    "chain": "Base (8453)",
    "chain_id": 8453,
    "recipient": "0xeB262928D55A92f2EAac946807CeC4d80E9EdD6B",
    "token": "USDC"
  }
}
```

---

## Development

```bash
# Install dependencies
npm install

# Build TypeScript
npm run build

# Watch mode
npm run dev
```

---

## Publishing

This package is published to npm via GitHub Actions with provenance statements.

---

## License

[MIT](LICENSE)

---

## Support

- [GitHub Issues](https://github.com/anassetti20-prog/x402-n8n-node/issues)
