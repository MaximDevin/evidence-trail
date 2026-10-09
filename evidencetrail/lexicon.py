"""Shared, transparent rule vocabulary for the agents.

Nothing here is hidden: every word list and threshold is a published rule with
an id, and each id that fires is written into the reasoning trail.
"""
from __future__ import annotations

# asset mentions -> canonical symbol
ASSETS = {
    "bitcoin": "BTC", "btc": "BTC", "bitcoins": "BTC",
    "ethereum": "ETH", "ether": "ETH", "eth": "ETH", "ethers": "ETH",
    "solana": "SOL", "sol": "SOL",
    "binance coin": "BNB", "bnb": "BNB", "bnb chain": "BNB",
    "tron": "TRX", "trx": "TRX",
    "chainlink": "LINK", "link": "LINK",
    "stablecoin": "STABLES", "usdt": "USDT", "usdc": "USDC",
    "defi": "DEFI", "layer 2": "L2", "layer-2": "L2",
}

# negative event cues -> weight
NEGATIVE_CUES = {
    "hack": -3, "hacked": -3, "exploit": -3, "exploited": -3, "breach": -3,
    "stolen": -3, "drain": -3, "vulnerability": -2, "rug": -3, "rugpull": -3,
    "lawsuit": -2, "sued": -2, "charges": -2, "charged": -2, "fine": -2,
    "ban": -3, "banned": -3, "prohibit": -2, "restriction": -2,
    "outage": -2, "halt": -2, "suspend": -2, "suspends": -2, "freeze": -2,
    "liquidation": -2, "liquidations": -2, "crash": -3, "plunge": -3,
    "collapse": -3, "default": -3, "insolvent": -3, "bankruptcy": -3,
    "delay": -1, "reject": -2, "rejected": -2, "denied": -2, "warning": -1,
    "risk": -1, "scam": -3, "fraud": -3, "ponzi": -3,
    # plurals / variants (matched with word boundaries)
    "hacks": -3, "exploits": -3, "lawsuits": -2, "fines": -2, "bans": -3,
    "breaches": -3, "liquidations": -2, "wiped": -3, "selloff": -2, "slump": -2,
}

POSITIVE_CUES = {
    "approval": 3, "approved": 3, "approve": 3, "adoption": 2, "adopt": 2,
    "partnership": 2, "partner": 2, "integration": 2, "integrate": 2,
    "launch": 2, "launches": 2, "launched": 2, "upgrade": 2, "upgraded": 2,
    "etf": 2, "institutional": 2, "record": 2, "milestone": 2, "surge": 3,
    "rally": 2, "gain": 1, "growth": 2, "expand": 1, "expands": 1,
    "stablecoin": 1, "listing": 1, "lists": 1, "custody": 1, "fund": 1,
    "funding": 1, "investment": 1, "invest": 1, "mainnet": 2, "testnet": 1,
    "grant": 1, "reward": 1, "burn": 1, "buyback": 1, "all-time high": 3,
    # plurals / variants (matched with word boundaries)
    "funds": 1, "stablecoins": 1, "etfs": 2, "partners": 1, "etf approval": 3,
    "record high": 3, "integrations": 2, "listings": 1,
    "rebounds": 2, "rebound": 2, "recovers": 2, "recovery": 1,
}

# debate weights
DEBATE_RULES = {
    "bull.price_positive": {"desc": "24h change is positive", "weight": 2},
    "bull.volume_above_median": {"desc": "24h quote volume above watchlist median", "weight": 1},
    "bull.positive_news": {"desc": "headline scored positive by NewsChecker", "weight": 3},
    "bull.community_warm": {"desc": "HN mentions lean positive/neutral", "weight": 1},
    "bear.price_negative": {"desc": "24h change is negative", "weight": 2},
    "bear.near_24h_low": {"desc": "last price within 1.5% of 24h low", "weight": 2},
    "bear.negative_news": {"desc": "headline scored negative by NewsChecker", "weight": 3},
    "bear.volatility_extreme": {"desc": "|24h change| above 8%", "weight": 1},
}

# TokenHunter screening thresholds (published, editable)
HUNTER_RULES = {
    "liquidity": {"desc": "24h quote volume >= 50,000,000 USD", "min": 50_000_000},
    "stability": {"desc": "|24h change| <= 25% (no degen pumps/dumps)", "max": 25.0},
    "trend": {"desc": "24h change >= -3% (not in free fall)", "min": -3.0},
    "data_quality": {"desc": "price > 0 and high >= low > 0", "min": 0.0},
}

# Buy-the-dip parameters
DIP_PARAMS = {
    "lookback": 30,          # candles that define the local high
    "min_drawdown_pct": 2.0, # enter only this far below the local high
    "max_drawdown_pct": 12.0,# too deep = falling knife, stay out
    "stop_pct": 3.0,         # stop distance from entry
    "target_pct": 5.0,       # take-profit distance from entry
    "risk_per_trade_pct": 1.0,  # account risk per trade
    "max_notional_pct": 10.0,   # position cap (mirror of ledger limit)
}
