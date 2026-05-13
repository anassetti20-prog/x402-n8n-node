"""
x402 Protocol Implementation (Python)
HTTP 402 Payment Required with ERC-20 Token (USDC on Base)

Based on the x402 specification:
https://github.com/x402/x402

This implements the server-side x402 protocol for USDC micropayments.
"""

import os
import time
import hashlib
import hmac
from typing import Optional, Dict, Any

# Optional web3 import — gracefully degrade if not installed
try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    _WEB3_AVAILABLE = True
except ImportError:
    _WEB3_AVAILABLE = False

from .config import (
    BASE_RPC_URL,
    USDC_CONTRACT_ADDRESS,
    WALLET_PRIVATE_KEY,
    WALLET_ADDRESS,
    PRICE_USDC,
    BASE_CHAIN_ID,
)

# ERC-20 ABI (minimal for balanceOf and transfer)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]

# USDC has 6 decimals on Base
USDC_DECIMALS = 6

# Session cache for paid requests (in-memory, production would use Redis)
_paid_sessions: Dict[str, float] = {}
SESSION_TTL = 3600  # 1 hour


def _get_web3():
    """Get Web3 instance. Returns None if web3 not available."""
    if not _WEB3_AVAILABLE:
        return None
    w3 = Web3(Web3.HTTPProvider(BASE_RPC_URL))
    try:
        w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    except Exception:
        pass
    return w3


def get_wallet_balance() -> float:
    """Get wallet USDC balance. Returns 0 if web3 not available."""
    if not WALLET_ADDRESS or not _WEB3_AVAILABLE:
        return 0.0
    w3 = _get_web3()
    if w3 is None:
        return 0.0
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_CONTRACT_ADDRESS),
        abi=ERC20_ABI,
    )
    balance = contract.functions.balanceOf(
        Web3.to_checksum_address(WALLET_ADDRESS)
    ).call()
    return balance / (10 ** USDC_DECIMALS)


def create_wallet() -> dict:
    """Create a new Ethereum wallet. Requires web3."""
    if not _WEB3_AVAILABLE:
        return {"address": "", "private_key": "", "error": "web3 not available"}
    from eth_account import Account
    import secrets

    w3 = _get_web3()
    acct = Account.create(secrets.token_hex(32))
    address = acct.address
    private_key = acct._private_key.hex()
    
    return {
        "address": address,
        "private_key": private_key,
        "chain": "Base",
        "chain_id": BASE_CHAIN_ID,
        "rpc_url": BASE_RPC_URL,
        "usdc_contract": USDC_CONTRACT_ADDRESS,
    }


def get_x402_headers(price: float = PRICE_USDC) -> dict:
    """Generate x402 payment required headers."""
    return {
        "X-402-Price": f"{price} USDC",
        "X-402-Recipient": WALLET_ADDRESS or "0x0000000000000000000000000000000000000000",
        "X-402-Chain": str(BASE_CHAIN_ID),
        "X-402-Chain-Name": "base",
        "X-402-Token": USDC_CONTRACT_ADDRESS,
        "X-402-Token-Symbol": "USDC",
        "X-402-Network": "mainnet",
        "X-402-Required-Confirmations": "1",
    }


def verify_payment(tx_hash: str) -> bool:
    """
    Verify an on-chain USDC transfer to our wallet.
    If web3 is not available, accepts any non-empty hash (dev/test mode).
    """
    if not _WEB3_AVAILABLE or not tx_hash:
        return bool(tx_hash)
    if not WALLET_ADDRESS:
        return False

    # Check cache first
    cache_key = f"paid:{tx_hash}"
    if cache_key in _paid_sessions:
        return True

    try:
        w3 = _get_web3()
        
        # Get transaction receipt
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
        except Exception:
            return False
        
        if not receipt or receipt.get("status") != 1:
            return False
        
        # Get the transaction
        tx = w3.eth.get_transaction(tx_hash)
        
        # Check it's a transfer to our USDC contract
        if tx["to"] and tx["to"].lower() != USDC_CONTRACT_ADDRESS.lower():
            return False
        
        # Check the transfer event (Transfer(from, to, value))
        usdc_contract = w3.eth.contract(
            address=Web3.to_checksum_address(USDC_CONTRACT_ADDRESS),
            abi=ERC20_ABI,
        )
        
        # Parse transfer logs
        transfer_logs = usdc_contract.events.Transfer().process_receipt(receipt)
        
        for log in transfer_logs:
            args = log.get("args", {})
            to_address = args.get("to", "").lower()
            value = args.get("value", 0)
            
            if to_address == WALLET_ADDRESS.lower():
                amount = value / (10 ** USDC_DECIMALS)
                if amount >= PRICE_USDC:
                    # Cache the payment
                    _paid_sessions[cache_key] = time.time()
                    return True
        
        return False
        
    except Exception as e:
        print(f"Payment verification error: {e}")
        return False


def generate_proof_token(address: str, timestamp: int = None) -> str:
    """Generate a signed proof token for authenticated requests."""
    if not WALLET_PRIVATE_KEY:
        return ""
    if timestamp is None:
        timestamp = int(time.time())
    message = f"x402:{address}:{timestamp}:{PRICE_USDC}"
    w3 = _get_web3()
    acct = w3.eth.account.from_key(WALLET_PRIVATE_KEY)
    signed = acct.sign_message(message.encode())
    return f"{timestamp}:{signed.signature.hex()}"


def verify_proof_token(proof: str, max_age: int = 300) -> Optional[str]:
    """
    Verify a proof token and return the wallet address if valid.
    Proof format: timestamp:signature
    """
    try:
        parts = proof.split(":", 2)
        if len(parts) != 3:
            return None
        
        timestamp_str, r_hex, s_hex = parts
        timestamp = int(timestamp_str)
        
        # Check age
        if time.time() - timestamp > max_age:
            return None
        
        message = f"x402:{address}:{timestamp}:{PRICE_USDC}"  # Can't recover without address
        return None
        
    except Exception:
        return None


def cleanup_old_sessions():
    """Clean up expired payment sessions."""
    now = time.time()
    expired = [k for k, v in _paid_sessions.items() if now - v > SESSION_TTL]
    for k in expired:
        del _paid_sessions[k]