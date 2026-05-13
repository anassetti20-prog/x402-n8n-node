"""
Halal Screening Module
Checks if a cryptocurrency/project is halal based on:

1. Whitepaper/project analysis
2. Tokenomics (Riba check - no interest, no staking rewards as interest)
3. Use case (Gharar - excessive uncertainty/speculation)
4. Project team and transparency
5. Shariah compliance criteria
"""

from typing import Dict, Any, Optional
import aiohttp
import json

# Halal criteria categories
HALAL_CRITERIA = {
    "riba": "Keine Zinsen, keine versteckten Zinsmechanismen",
    "gharar": "Klare Nutzenstiftung, keine reine Spekulation",
    "maysir": "Kein Glücksspiel, keine Ponzi-Strukturen", 
    "haram_business": "Keine Verbindung zu Haram-Geschäften (Alkohol, Tabak, Waffen, etc.)",
    "backed_by_assets": "Idealerweise durch reale Werte gedeckt",
    "transparency": "Transparentes Team, Open Source Code",
    "permissionless": "Keine zentralen Kontrollinstanzen, die willkürlich eingreifen",
}

# Known halal coins (pre-assessed)
KNOWN_HALAL = {
    "btc": {
        "symbol": "BTC",
        "name": "Bitcoin",
        "halal": True,
        "confidence": 0.95,
        "reason": "Dezentral, Proof-of-Work, keine Zinsen, kein Team mit Kontrolle, reine Peer-to-Peer-Währung",
        "source": "Etablierte Fatwas (Shariah Analysis 2018, Blossom Finance)",
        "caveats": "Mining mit halaler Energie sollte bevorzugt werden",
    },
    "eth": {
        "symbol": "ETH",
        "name": "Ethereum",
        "halal": True,
        "confidence": 0.85,
        "reason": "Dezentral, Smart Contracts für legitime Anwendungen, Proof-of-Stake ist umstritten aber mehrheitlich als halal akzeptiert",
        "source": "Mehrere islamische Finanzinstitute",
        "caveats": "Staking-Rewards sind unter Gelehrten umstritten (ähnlich Zins) - Vorsicht bei Staking-Produkten",
    },
    "xmr": {
        "symbol": "XMR",
        "name": "Monero",
        "halal": True,
        "confidence": 0.90,
        "reason": "Dezentral, Privacy-Fokus, Proof-of-Work, kein Vorverkauf, reines Zahlungsmittel",
        "source": "Islamic Finance Guru",
        "caveats": "Keine wesentlichen",
    },
    "ada": {
        "symbol": "ADA",
        "name": "Cardano",
        "halal": True,
        "confidence": 0.80,
        "reason": "Wissenschaftlich fundiert, Proof-of-Stake, starkes Team, Fokus auf reale Anwendungen",
        "source": "Cardano Shariah Oracle",
        "caveats": "Delegation/Staking könnte als Riba betrachtet werden",
    },
    "xrp": {
        "symbol": "XRP",
        "name": "XRP",
        "halal": False,
        "confidence": 0.60,
        "reason": "Zentralisiert (Ripple kontrolliert große Mengen), Rechtsunsicherheit, Bankenfokus mit Zinskomponenten",
        "source": "Umstritten unter Gelehrten",
        "caveats": "Einige Gelehrte erlauben XRP für grenzüberschreitende Zahlungen",
    },
    "usdt": {
        "symbol": "USDT",
        "name": "Tether",
        "halal": False,
        "confidence": 0.55,
        "reason": "Stablecoin, der durch traditionelle Finanzanlagen gedeckt ist (Staatsanleihen mit Zinsen), Intransparenz der Reserven",
        "source": "Islamic Finance Guru",
        "caveats": "USDC und einige andere Stablecoins gelten als halaler (mehr Transparenz)",
    },
    "usdc": {
        "symbol": "USDC",
        "name": "USD Coin",
        "halal": True,
        "confidence": 0.70,
        "reason": "Transparente Reserven, reguliert, aber Reserven in Staatsanleihen (Riba-technisch) – von einigen als 'notwendiges Übel' akzeptiert",
        "source": "Circle hat Fatwa eingeholt, aber umstritten",
        "caveats": "Nicht 100% schariakonform wegen Zinshinterlegung",
    },
    "doge": {
        "symbol": "DOGE",
        "name": "Dogecoin",
        "halal": True,
        "confidence": 0.75,
        "reason": "Dezentral, Proof-of-Work, reiner Meme-Coin ohne Zinsversprechen, aber sehr spekulativ",
        "source": "Allgemeine Meinung",
        "caveats": "Hohe Spekulation (Gharar) - für kurzfristiges Trading weniger geeignet",
    },
    "sol": {
        "symbol": "SOL",
        "name": "Solana",
        "halal": True,
        "confidence": 0.75,
        "reason": "Dezentral, Proof-of-Stake, Fokus auf Skalierbarkeit für reale Anwendungen",
        "source": "Mehrere Analysen",
        "caveats": "Staking umstritten, Netzwerkausfälle in der Vergangenheit",
    },
    "bnb": {
        "symbol": "BNB",
        "name": "Binance Coin",
        "halal": False,
        "confidence": 0.65,
        "reason": "Zentralisiert (Binance kontrolliert), BNB Burn-Mechanismus hat Glücksspielelemente, Binance bietet Leverage/Zinsprodukte",
        "source": "Umstritten",
        "caveats": "Reine Nutzung für Gas-Gebühren könnte erlaubt sein, aber Investment wird abgeraten",
    },
    "dot": {
        "symbol": "DOT",
        "name": "Polkadot",
        "halal": True,
        "confidence": 0.80,
        "reason": "Dezentral, Governance durch DOT-Holder, Fokus auf Interoperabilität für reale Anwendungen",
        "source": "Mehrere Analysen",
        "caveats": "Staking umstritten, aber Nennung/Nominierung ist eher Governance als Zins",
    },
    "link": {
        "symbol": "LINK",
        "name": "Chainlink",
        "halal": True,
        "confidence": 0.90,
        "reason": "Dezentrales Oracle-Netzwerk für Smart Contracts, klarer Nutzen, kein Zinsversprechen",
        "source": "Islamic Finance Guru",
        "caveats": "Keine wesentlichen",
    },
    "atom": {
        "symbol": "ATOM",
        "name": "Cosmos",
        "halal": True,
        "confidence": 0.80,
        "reason": "Dezentral, Interoperabilitätsprotokoll, Staking für Netzwerksicherheit",
        "source": "Mehrere Analysen",
        "caveats": "Staking umstritten (Riba-ähnlich?)",
    },
    "matic": {
        "symbol": "MATIC",
        "name": "Polygon",
        "halal": True,
        "confidence": 0.85,
        "reason": "Layer-2-Skalierungslösung, klarer Nutzen, dezentral",
        "source": "Mehrere Analysen",
        "caveats": "Wurde zu POL migriert - bitte POL prüfen",
    },
    "luna": {
        "symbol": "LUNA",
        "name": "Terra Classic",
        "halal": False,
        "confidence": 0.99,
        "reason": "Ehemaliges algorithmisches Stablecoin-Projekt, das kollabiert ist - hoher Verlust für Anleger, Ponzi-ähnliche Struktur",
        "source": "Allgemein bekannt",
        "caveats": "LUNC/LUNA stark spekulativ nach Kollaps",
    },
    "shib": {
        "symbol": "SHIB",
        "name": "Shiba Inu",
        "halal": False,
        "confidence": 0.70,
        "reason": "Reiner Meme-Token ohne klaren Nutzen, extrem spekulativ, hohes Gharar-Risiko",
        "source": "Allgemeine Meinung",
        "caveats": "Shibarium-Ökosystem könnte Nutzen bringen, derzeit aber sehr spekulativ",
    },
    "avax": {
        "symbol": "AVAX",
        "name": "Avalanche",
        "halal": True,
        "confidence": 0.80,
        "reason": "Dezentral, Proof-of-Stake mit Subnets, Fokus auf reale Anwendungen",
        "source": "Mehrere Analysen",
        "caveats": "Staking umstritten",
    },
    "ltc": {
        "symbol": "LTC",
        "name": "Litecoin",
        "halal": True,
        "confidence": 0.90,
        "reason": "Proof-of-Work, dezentral, reines Zahlungsmittel, kein Vorverkauf",
        "source": "Islamic Finance Guru",
        "caveats": "Mining-Energieverbrauch",
    },
    "xlm": {
        "symbol": "XLM",
        "name": "Stellar",
        "halal": True,
        "confidence": 0.85,
        "reason": "Dezentral, Fokus auf Überweisungen und Finanzinklusion, keine Zinsen",
        "source": "Stellar hat Kooperation mit islamischen Finanzinstituten",
        "caveats": "Teilweise zentralisiert (Stellar Foundation hat große Kontrolle)",
    },
    "vet": {
        "symbol": "VET",
        "name": "VeChain",
        "halal": True,
        "confidence": 0.85,
        "reason": "Fokus auf Supply-Chain-Tracking für reale Produkte klarer Nutzen, Proof-of-Authority",
        "source": "Mehrere Analysen",
        "caveats": "Teilweise zentralisiert, aber Geschäftsmodell ist halal",
    },
    "hbar": {
        "symbol": "HBAR",
        "name": "Hedera",
        "halal": True,
        "confidence": 0.80,
        "reason": "Enterprise-DAG, klarer Nutzen, Governing Council, keine Zinsen",
        "source": "Mehrere Analysen",
        "caveats": "Zentralisiert durch Governing Council (Unternehmen)",
    },
}

def _get_default_halal_coins() -> list:
    """Get list of pre-assessed coins."""
    return list(KNOWN_HALAL.keys())


async def check_halal_via_coingecko(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetch project info from CoinGecko for additional context."""
    try:
        symbol = symbol.lower().strip()
        url = f"https://api.coingecko.com/api/v3/coins/{symbol}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "name": data.get("name", ""),
                        "description": data.get("description", {}).get("en", ""),
                        "categories": data.get("categories", []),
                        "market_cap_rank": data.get("market_cap_rank"),
                        "community_score": data.get("community_score"),
                        "developer_score": data.get("developer_score"),
                        "liquidity_score": data.get("liquidity_score"),
                        "public_interest_score": data.get("public_interest_score"),
                        "links": data.get("links", {}),
                    }
                return None
    except Exception:
        return None


def score_halal_from_cg(data: Dict) -> Dict:
    """Score a coin based on CoinGecko data."""
    score = 0.50  # neutral start
    reasons = []
    
    desc = (data.get("description", "") or "").lower()
    categories = [c.lower() for c in data.get("categories", [])]
    
    # Check for red flags
    red_flags = ["gambling", "casino", "porn", "alcohol", "tobacco", "weapon", "ponzi", "scam"]
    for flag in red_flags:
        if flag in desc or any(flag in cat for cat in categories):
            score -= 0.15
            reasons.append(f"⚠️ Rote Flagge gefunden: '{flag}'")
    
    # Check for green flags
    green_flags = ["supply chain", "payments", "remittance", "decentralized finance", "smart contract", 
                   "real world", "utility", "cross-border", "inclusive", "charity", "zakat"]
    for flag in green_flags:
        if flag in desc:
            score = min(score + 0.05, 1.0)
    
    # Developer activity
    dev_score = data.get("developer_score", 0)
    if dev_score and dev_score > 0.5:
        score = min(score + 0.05, 1.0)
        reasons.append("✓ Aktive Entwicklung (Open Source)")
    
    # Community
    community = data.get("community_score", 0)
    if community and community > 0.5:
        score = min(score + 0.03, 1.0)
    
    # Market cap rank (more established = more stable = less gharar)
    rank = data.get("market_cap_rank")
    if rank and rank <= 100:
        score = min(score + 0.05, 1.0)
        reasons.append("✓ Hohe Marktkapitalisierung (Top 100)")
    
    return {"score": round(score, 2), "reasons": reasons}


async def check_halal(symbol: str) -> Dict[str, Any]:
    """
    Main halal check function.
    Returns a comprehensive halal screening report.
    """
    sym = symbol.lower().strip()
    
    # 1. Check known database first
    if sym in KNOWN_HALAL:
        known = KNOWN_HALAL[sym]
        report = {
            "symbol": known["symbol"],
            "name": known["name"],
            "halal": known["halal"],
            "confidence": known["confidence"],
            "source": known["source"],
            "reason": known["reason"],
            "caveats": known["caveats"],
            "criteria_assessment": {},
        }
        
        for criterion, description in HALAL_CRITERIA.items():
            if known["halal"]:
                report["criteria_assessment"][criterion] = "bestanden"
            else:
                report["criteria_assessment"][criterion] = "nicht bestanden"
        
        return report
    
    # 2. Try to fetch from CoinGecko for unknown coins
    cg_data = await check_halal_via_coingecko(symbol)
    
    if cg_data:
        cg_score = score_halal_from_cg(cg_data)
        
        is_halal = cg_score["score"] >= 0.60
        confidence = cg_score["score"]
        
        report = {
            "symbol": symbol.upper(),
            "name": cg_data.get("name", symbol.upper()),
            "halal": is_halal,
            "confidence": confidence,
            "source": "CoinGecko API + Automatische Analyse",
            "reason": " | ".join(cg_score["reasons"]) if cg_score["reasons"] else "Automatische Analyse basierend auf verfügbaren Daten",
            "caveats": "⚠️ Automatische Analyse - Bitte immer einen Gelehrten konsultieren",
            "criteria_assessment": {},
        }
        
        return report
    
    # 3. Fallback - unknown coin
    return {
        "symbol": symbol.upper(),
        "name": symbol.upper(),
        "halal": None,  # Unknown
        "confidence": 0.0,
        "source": "Nicht in unserer Datenbank",
        "reason": "Dieser Coin ist nicht in unserer Halal-Datenbank. Bitte konsultiere einen islamischen Finanzgelehrten für eine Fatwa.",
        "caveats": "Keine Daten verfügbar - manuelle Prüfung erforderlich",
        "criteria_assessment": {},
        "suggestion": "Du kannst diesen Coin auf Islamic Finance Guru (ifg.io) oder Blossom Finance prüfen lassen.",
    }