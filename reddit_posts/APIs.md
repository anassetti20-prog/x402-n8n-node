**x402-Powered Halal Crypto Screening API – $0.01/request, no API keys, no subscriptions**

r/APIs —

I built an API that does something unique: per-request on-chain micropayments via x402 on the Base L2. No API keys, no monthly subscriptions — you literally pay $0.01 USDC per API call, settled on-chain.

**What it does:**
Submit a cryptocurrency ticker or contract address → get back a Shariah compliance assessment (halal/not-halal + reasoning).

> First Halal Crypto Screening API with x402 micropayments. Check if any cryptocurrency is Sharia-compliant. $0.01 USDC per request on Base blockchain. Built for Islamic fintech developers and AI agents.

**API details:**
- **Method:** POST /screen
- **Auth:** x402 micropayment in the request header (no API key required)
- **Request body:** `{ "asset": "BTC" }` or `{ "contract": "0x..." }`
- **Response:** JSON with `status` (compliant/non-compliant), `reasoning`, and `confidence_score`
- **Payment:** $0.01 USDC via x402, auto-settled on Base

**Why this matters for API design:**
- Eliminates friction of API key management and recurring billing
- True pay-per-use — no minimum commitments or tiered plans
- Built-in monetization for API providers without Stripe/Plaid dependency
- AI agents can autonomously consume the API since payments are bundled with HTTP requests

**Live on RapidAPI:** https://rapidapi.com

Would love feedback on the x402 integration approach. Has anyone else experimented with HTTP-level micropayments for API access?