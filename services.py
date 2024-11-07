import logging
from typing import Any, Dict, List, Optional, Tuple

import requests
from db import Database
from models import Account, Position

logger = logging.getLogger(__name__)


class DexScreenerAPI:
    BASE_URL = "https://api.dexscreener.com/latest/dex/tokens"

    @staticmethod
    def _get_best_pair(pairs: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Get the pair with highest liquidity in USD."""
        if not pairs:
            return None

        return max(pairs, key=lambda x: x.get("liquidity", {}).get("usd", 0))

    def get_token_data(
        self, token_address: str
    ) -> Optional[Tuple[str, float, float, float]]:
        """Fetch token data from DexScreener API."""
        try:
            response = requests.get(
                f"{self.BASE_URL}/{token_address}", headers={}, timeout=10
            )
            response.raise_for_status()
            data = response.json()

            # Get the best pair based on liquidity
            best_pair = self._get_best_pair(data.get("pairs", []))
            if not best_pair:
                logger.warning(f"No pairs found for token {token_address}")
                return None

            return (
                best_pair.get("baseToken")["symbol"],
                float(best_pair.get("priceNative")),
                float(best_pair.get("priceUsd")),
                float(str(best_pair.get("marketCap"))),
            )
        except requests.RequestException as e:
            logger.error(f"Error fetching token data: {e}")
            return None
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing token data: {e}")
            return None


class PortfolioService:
    def __init__(self, db: Database, dexscreener: DexScreenerAPI):
        self.db = db
        self.dexscreener = dexscreener

    def get_portfolio_summary(self, account: Account, positions: List[Position]) -> str:
        summary = f"Balance: {account.sol_balance:,.2f} SOL\n\nPositions:\n"

        if not positions:
            summary += "No open positions"
            return summary

        for position in positions:
            symbol, token_price_sol, token_price_usd, market_cap = (
                self.dexscreener.get_token_data(position.token_address)
            )

            summary += (
                f"{symbol}:\n"
                f" `{position.token_address}`\n"
                f"  Quantity: {position.quantity}\n"
                f"  Current Position Size: ${position.quantity * token_price_usd:,.2f} ({position.quantity * token_price_sol:,.2f} SOL)\n"
                f"  Average Entry Price: $XX ({position.entry_price:,.2f} SOL)\n"
                f"  Current Price : ${token_price_usd:,.2f} ({token_price_sol:,.2f} SOL)\n"
                f"  Current Market Cap: ${market_cap:,.0f}\n\n"
            )

        return summary
