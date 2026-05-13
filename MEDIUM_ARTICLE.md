# x402 Halal Screening API — Pay $0.01 in USDC to Check if Any Crypto Is Halal

## The Problem

The Islamic finance industry is worth over **$4 trillion** and growing at 10–12% annually. Yet developers building Islamic fintech products have no easy way to check whether a cryptocurrency is Shariah-compliant.

Most teams resort to:
- Hours of manual research per coin
- Scattered fatwas from different scholars
- Expensive Shariah advisory consulting
- Building their own screening logic from scratch

**This is a massive bottleneck for Islamic fintech innovation.**

## The Solution

The **x402 Halal Screening API** is the first pay-per-request API that automatically screens cryptocurrencies for Islamic compliance.

**How it works:**

1. You send USDC via the x402 micropayment protocol on Base blockchain
2. You call the API with any coin symbol
3. You get a full Shariah screening report — including confidence score, reasoning, and scholarly sources

**Pricing:** Just **$0.01 USDC per request** — no subscriptions, no KYC, no middlemen.

## What It Checks

The API evaluates coins against seven Islamic finance criteria:

| Criterion | Meaning | Assessment |
|-----------|---------|------------|
| **Riba** ( Interest) | No hidden interest mechanisms | ✅ Checked |
| **Gharar** (Uncertainty) | Clear utility vs. pure speculation | ✅ Checked |
| **Maysir** (Gambling) | No ponzi or gambling structures | ✅ Checked |
| **Haram Business** | No alcohol, tobacco, weapons | ✅ Checked |
| **Asset-Backed** | Real value backing | ✅ Checked |
| **Transparency** | Open source, team visibility | ✅ Checked |
| **Permissionless** | No centralized control | ✅ Checked |

## Pre-Assessed Coins

**21+ major coins** are already evaluated with scholarly references:

✅ **Halal (strong confidence):** Bitcoin (95%), Monero (90%), Chainlink (90%), Litecoin (90%), Stellar (85%), VeChain (85%), Ethereum (85%), Solana (75%), Polkadot (80%), Cardano (80%), Avalanche (80%), Hedera (80%), Cosmos (80%), Polygon (85%), Dogecoin (75%)

⚠️ **Halal with caveats:** USDC (70%)

❌ **Not Halal:** XRP, USDT, BNB, LUNA, SHIB

For **any coin not in the database**, the API performs live analysis via CoinGecko — checking descriptions, categories, developer activity, and community scores.

## How x402 Micropayments Work

The x402 protocol is an open standard for HTTP 402 Payment Required using ERC-20 tokens:

```
GET /halal-check?symbol=BTC
→ 402 Payment Required
  X-402-Price: 0.01 USDC
  X-402-Recipient: 0xeB...EdD6B
  X-402-Chain: 8453 (Base)
  X-402-Token: 0x8335...2913

→ Send $0.01 USDC on Base to the wallet

→ GET /halal-check?symbol=BTC
  X-402-Proof: 0x<tx_hash>
→ 200 OK (full halal report)
```

## For Developers

```bash
curl -H "X-402-Proof: 0xYOUR_TX_HASH" \
  "http://178.105.35.170:8080/halal-check?symbol=BTC"
```

Available on **RapidAPI**: [https://rapidapi.com](https://rapidapi.com)

Self-host the open-source code:
```bash
git clone https://github.com/anassetti20-prog/x402-halal-api.git
```

## Built for the Future

This API is designed for:
- **Islamic fintech developers** building halal DeFi, wallets, and exchanges
- **AI agents** that autonomously need to verify compliance before trading
- **Researchers** analyzing the crypto market through an Islamic lens
- **DeFi protocols** screening tokens for listing

## The Vision

Islamic finance has always been at the forefront of ethical finance. As crypto and AI reshape the financial world, the Muslim community needs tools that reflect our values — transparent, fair, and grounded in Islamic principles.

The x402 Halal Screening API is my contribution to that vision. Open source. Pay-per-use. No middlemen. Built on blockchain, for blockchain.

**Try it today:** [https://rapidapi.com](https://rapidapi.com)
**Live API:** `http://178.105.35.170:8080`
**GitHub:** `https://github.com/anassetti20-prog/x402-halal-api`

---

*"First Halal Crypto Screening API with x402 micropayments. Check if any cryptocurrency is Sharia-compliant. $0.01 USDC per request on Base blockchain. Built for Islamic fintech developers and AI agents."*