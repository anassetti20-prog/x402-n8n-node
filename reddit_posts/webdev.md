**Built an API with on-chain micropayments – $0.01 per request, no API keys, no subscriptions**

Hey r/webdev,

Wanted to share a side project that explores an interesting payment model for APIs: **x402 micropayments on Base blockchain**.

The API itself screens cryptocurrencies for Shariah (Islamic) compliance, but I think the payment mechanism is the more generally interesting part.

> First Halal Crypto Screening API with x402 micropayments. Check if any cryptocurrency is Sharia-compliant. $0.01 USDC per request on Base blockchain. Built for Islamic fintech developers and AI agents.

**The tech:**
- **Backend:** Standard REST API (Node.js)
- **Payments:** x402 protocol — the client attaches a $0.01 USDC micropayment directly in the HTTP request headers
- **Settlement:** On-chain on Base (OP Stack L2) — near-zero gas fees
- **No database of API keys**, no Stripe integration, no monthly billing

**What this means for web dev:**
- You can consume the API from a simple `fetch()` call with a small crypto payment attached — no auth setup needed
- Great for hackathons, prototypes, or any situation where you don't want to deal with yet another API key dashboard
- The x402 approach could work for any API you build — imagine charging fractions of a cent per endpoint call

**Try it:** https://rapidapi.com

Curious what you all think — would you use x402 micropayments in your own projects? What API would you build with this kind of per-call crypto payment model?