# x402 Halal Screening API - RapidAPI Registration Info
# Stand: 30.04.2026

## API Details
- **Name:** x402 Halal Screening API
- **Description:** Pay-per-request Halal-Screening für Kryptowährungen. Prüft Coins auf Riba, Gharar, Maysir und Haram-Geschäfte. $0.01 USDC pro Anfrage auf Base Blockchain.
- **Version:** 1.0.0
- **Endpoint:** http://178.105.35.170:8080/halal-check?symbol=BTC
- **Payment:** x402 Micropayment Protocol (USDC on Base, Chain ID: 8453)

## Test Request
```bash
curl -H "X-402-Proof: 0xYOUR_TX_HASH" \
  "http://178.105.35.170:8080/halal-check?symbol=BTC"
```

## Pricing
- **Price:** $0.01 USDC per request
- **Payment Method:** USDC on Base Blockchain
- **Wallet:** 0xeB262928D55A92f2EAac946807CeC4d80E9EdD6B
- **USDC Contract:** 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 (Base)

## Server Details
- **Host:** hetzner (178.105.35.170)
- **Port:** 8080
- **Systemd Service:** x402-halal-api.service
- **Location:** /root/x402-api/

## RapidAPI Registration (manuell)
1. Gehe zu https://rapidapi.com/signup
2. Erstelle Account
3. Gehe zu "My APIs" → "Create New API"
4. Trage die obigen Details ein
5. Setze Pricing auf $0.01/request
6. Füge Endpoint hinzu: GET /halal-check?symbol={symbol}
7. Dokumentation: Kopiere README