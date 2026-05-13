"""
x402 Halal Screening API - Configuration
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
ENV_FILE = BASE_DIR / ".env"

# Load .env if exists (plaintext)
if ENV_FILE.exists():
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

# Fallback to encrypted .env.enc (safer)
ENC_FILE = BASE_DIR / ".env.enc"
KEY_FILE = BASE_DIR / ".encryption_key.secure"
if not ENV_FILE.exists() and ENC_FILE.exists() and KEY_FILE.exists():
    import base64
    try:
        with open(KEY_FILE, "rb") as f:
            key = f.read()
        with open(ENC_FILE, "rb") as f:
            enc = base64.b64decode(f.read())
        decrypted = bytes([enc[i] ^ key[i % len(key)] for i in range(len(enc))])
        for line in decrypted.decode().strip().split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except Exception:
        pass  # silently fallback to defaults

# API Config
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))

# Blockchain Config - Base Mainnet
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
BASE_CHAIN_ID = 8453

# USDC on Base
USDC_CONTRACT_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base

# Server Wallet
WALLET_PRIVATE_KEY = os.getenv("WALLET_PRIVATE_KEY", "")
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "")

# Internal Key for MCP server bypass
INTERNAL_KEY = os.getenv("INTERNAL_KEY", "hermes-mcp-internal-v1")

# Pricing
PRICE_USDC = 0.01  # $0.01 per request

# Halal Check API Keys (free tier)
COINGECKO_API_KEY = os.getenv("COINGECKO_API_KEY", "")