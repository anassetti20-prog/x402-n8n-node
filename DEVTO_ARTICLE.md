---
title: "Introducing x402 Halal Screening API — Check Any Crypto for Shariah Compliance for $0.01"
published: true
description: "First Halal Crypto Screening API with x402 micropayments. Check if any cryptocurrency is Sharia-compliant. $0.01 USDC per request on Base blockchain. Built for Islamic fintech developers and AI agents."
tags: halal, blockchain, api, islamicfinance, web3
---

# 🕌 x402 Halal Screening API — Crypto Shariah Compliance at $0.01/request

As an Islamic fintech developer, have you ever wondered whether a cryptocurrency is halal to invest in, trade, or build with?

The $4+ trillion Islamic finance industry is growing at 10-12% annually, yet developers lack simple tooling to screen cryptocurrencies for Shariah compliance. Most rely on manual research, scattered fatwas, or expensive consulting.

That's why I built the **x402 Halal Screening API** — the first pay-per-request API that checks any cryptocurrency for Islamic compliance, using the x402 micropayment protocol.

## What It Does

Send a coin symbol → get a full Shariah screening report:

```bash
curl -H "X-402-Proof: 0xYOUR_TX_HASH" \
  "http://178.105.35.170:8080/halal-check?symbol=BTC"
```

**Output:**
```json
{
  "symbol": "BTC",
  "name": "Bitcoin",
  "halal": true,
  "confidence": 0.95,
  "reason": "Dezentral, Proof-of-Work, keine Zinsen, keine zentrale Kontrolle",
  "source": "Etablierte Fatwas (Shariah Analysis 2018, Blossom Finance)"
}
```

## The Assessment Criteria 🕌

The API screens coins against 7 Islamic finance criteria:

| Criterion | Arabic | What We Check |
|-----------|--------|---------------|
| No Interest | **Riba** | No hidden interest mechanisms |
| No Excessive Uncertainty | **Gharar** | Clear utility, not pure speculation |
| No Gambling | **Maysir** | No ponzi structures |
| No Haram Business | **Haram** | No alcohol, tobacco, weapons connections |
| Asset-Backed | **Mal** | Ideally backed by real value |
| Transparency | **Shafafiya** | Open source code, transparent team |
| Permissionless | — | No centralized control |

## 21 Coins Pre-Assessed 🔍

### ✅ Halal (Strong Confidence)
BTC (95%), XMR (90%), LINK (90%), LTC (90%), XLM (85%), VET (85%), ETH (85%), SOL (75%), DOT (80%), ADA (80%), AVAX (80%), HBAR (80%), ATOM (80%), MATIC (85%), DOGE (75%)

### ⚠️ Halal with Caveats
USDC (70%) — reserves in interest-bearing assets

### ❌ Not Halal
XRP, USDT, BNB, LUNA, SHIB

For **unknown coins**, the API auto-analyzes via CoinGecko data — checking project descriptions, categories, and community/developer scores.

## How x402 Micropayments Work ⛓️

The API uses the **x402 protocol** — HTTP 402 Payment Required with ERC-20 USDC tokens on **Base blockchain**:

1. **Client requests** → Server responds 402 with payment headers
2. **Client sends** $0.01 USDC on Base to the server wallet
3. **Client retries** with `X-402-Proof: <tx_hash>` header
4. **Server verifies** the on-chain transfer and returns the result

**No subscriptions. No KYC. No middlemen.** Just pure pay-per-request.

## Why This Matters for Islamic Fintech 🏦

- **DeFi protocols** can screen tokens before listing
- **Islamic wallets** can warn users about haram coins
- **AI agents** can autonomously check compliance before executing trades
- **Researchers** get instant data instead of manual analysis

## Try It Out 🚀

The API is available on **RapidAPI**: [https://rapidapi.com](https://rapidapi.com)

**Quick start:**
```bash
# Step 1: Send $0.01 USDC on Base to the server wallet
# (wallet address available from GET /wallet)

# Step 2: Check any coin
curl -H "X-402-Proof: 0xYOUR_TX_HASH" \
  "http://178.105.35.170:8080/halal-check?symbol=BTC"
```

### Self-Hosting

The entire codebase is open source (MIT). Check the **GitHub repo** for self-hosting instructions:
```bash
git clone https://github.com/anassetti20-prog/x402-halal-api.git
```

## Technical Stack 🛠️

| Component | Technology |
|-----------|-----------|
| API Framework | FastAPI (Python) |
| Payments | x402 Protocol (USDC on Base) |
| Blockchain | Base (Coinbase L2, Chain ID: 8453) |
| Hosting | Hetzner (Germany) |
| Auto-restart | Systemd |
| Security | AES-256 encrypted keys |

## Roadmap 🗺️

- ✅ x402 micropayments
- ✅ 21+ pre-assessed coins
- ✅ Auto-analysis via CoinGecko
- 🔜 Community-sourced coin assessments
- 🔜 Telegram bot integration
- 🔜 AI agent SDK

## Let's Build Halal Fintech Together 🤝

The Islamic finance industry needs modern tooling. This API is my contribution — open, transparent, and built on Islamic principles from day one.

**Try it:** [https://rapidapi.com](https://rapidapi.com)
**GitHub:** [https://github.com/anassetti20-prog/x402-halal-api](https://github.com/anassetti20-prog/x402-halal-api)
**Live Server:** `http://178.105.35.170:8080`

*"First Halal Crypto Screening API with x402 micropayments. Check if any cryptocurrency is Sharia-compliant. $0.01 USDC per request on Base blockchain. Built for Islamic fintech developers and AI agents."*

---

*Questions? Feedback? Reach out — let's make Islamic fintech accessible to every developer.* 🌙