import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("polymarket_spike_bot")

GAMMA_API = os.getenv("POLYMARKET_GAMMA_API", "https://gamma-api.polymarket.com")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "45"))
MARKET_LIMIT = int(os.getenv("MARKET_LIMIT", "200"))
SPIKE_THRESHOLD = float(os.getenv("SPIKE_THRESHOLD", "0.10"))
MIN_NOTIONAL_24H = float(os.getenv("MIN_NOTIONAL_24H", "10000"))
EXCLUDED_CATEGORIES = {
    x.strip().lower()
    for x in os.getenv("EXCLUDED_CATEGORIES", "crypto,sports,esports").split(",")
    if x.strip()
}
STARTUP_TEST_MESSAGE = os.getenv("STARTUP_TEST_MESSAGE", "true").lower() == "true"

SPORTS_KEYWORDS = {
    "nba",
    "wnba",
    "nfl",
    "nhl",
    "mlb",
    "ncaa",
    "soccer",
    "football",
    "baseball",
    "basketball",
    "tennis",
    "golf",
    "ufc",
    "mma",
    "f1",
    "formula 1",
    "premier league",
    "champions league",
    "esports",
    "e-sports",
    "valorant",
    "counter-strike",
    "cs2",
    "league of legends",
    "dota",
}

CRYPTO_KEYWORDS = {
    "bitcoin",
    "btc",
    "ethereum",
    "eth",
    "solana",
    "sol",
    "doge",
    "xrp",
    "ada",
    "bnb",
    "crypto",
    "token",
    "airdrop",
}


@dataclass
class MarketSnapshot:
    question: str
    slug: str
    last_trade_price: float
    one_day_price_change: float
    volume_24h: float


class PolymarketSpikeBot:
    def __init__(self) -> None:
        if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
            raise ValueError(
                "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID environment variables"
            )

        self.session = requests.Session()
        self.prev_prices: Dict[str, float] = {}

    def verify_telegram_config(self) -> None:
        """Fail fast if bot token/chat id are invalid."""
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getMe"
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise ValueError(f"Telegram getMe failed: {data}")
        username = data.get("result", {}).get("username", "<unknown>")
        logger.info("Telegram token valid for bot @%s", username)

    def fetch_markets(self) -> List[MarketSnapshot]:
        """Fetch active markets and map response fields defensively."""
        url = f"{GAMMA_API}/markets"
        params = {
            "active": "true",
            "closed": "false",
            "limit": MARKET_LIMIT,
            "order": "volume24hr",
            "ascending": "false",
        }
        response = self.session.get(url, params=params, timeout=20)
        response.raise_for_status()
        raw = response.json()

        markets: List[MarketSnapshot] = []
        for item in raw:
            slug = item.get("slug")
            question = item.get("question")
            if not slug or not question:
                continue

            if not self._should_include_market(item):
                continue

            price = self._to_float(item.get("lastTradePrice"))
            one_day_move = self._to_float(item.get("oneDayPriceChange"))
            vol24 = self._to_float(item.get("volume24hr"))

            if price is None:
                continue

            markets.append(
                MarketSnapshot(
                    question=question,
                    slug=slug,
                    last_trade_price=price,
                    one_day_price_change=one_day_move or 0.0,
                    volume_24h=vol24 or 0.0,
                )
            )

        logger.info("Fetched %s included markets", len(markets))
        return markets

    def _should_include_market(self, item: dict) -> bool:
        """Exclude sports/crypto markets using category metadata + keyword fallback."""
        normalized: set[str] = set()

        for key in ("category", "subcategory", "groupItemTitle"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                normalized.add(value.strip().lower())

        events = item.get("events")
        if isinstance(events, list):
            for event in events:
                if isinstance(event, dict):
                    for key in ("category", "subcategory", "slug", "title"):
                        value = event.get(key)
                        if isinstance(value, str) and value.strip():
                            normalized.add(value.strip().lower())

        if normalized & EXCLUDED_CATEGORIES:
            return False

        question = str(item.get("question", "")).lower()
        if "sports" in EXCLUDED_CATEGORIES and any(k in question for k in SPORTS_KEYWORDS):
            return False
        if "esports" in EXCLUDED_CATEGORIES and any(k in question for k in SPORTS_KEYWORDS):
            return False
        if "crypto" in EXCLUDED_CATEGORIES and any(k in question for k in CRYPTO_KEYWORDS):
            return False

        return True

    def detect_spikes(self, markets: List[MarketSnapshot]) -> List[str]:
        alerts: List[str] = []
        for market in markets:
            current = market.last_trade_price
            previous = self.prev_prices.get(market.slug)
            self.prev_prices[market.slug] = current

            if previous is None or previous <= 0:
                continue

            delta = current - previous
            delta_pct = delta / previous

            if abs(delta_pct) < SPIKE_THRESHOLD:
                continue

            if market.volume_24h < MIN_NOTIONAL_24H:
                continue

            direction = "📈 spike UP" if delta_pct > 0 else "📉 spike DOWN"
            msg = (
                f"{direction}\n"
                f"Market: {market.question}\n"
                f"Price: {previous:.3f} → {current:.3f} ({delta_pct:+.2%})\n"
                f"24h Δ: {market.one_day_price_change:+.2%}\n"
                f"24h volume: ${market.volume_24h:,.0f}\n"
                f"https://polymarket.com/event/{market.slug}"
            )
            alerts.append(msg)

        logger.info("Detected %s spike alerts this cycle", len(alerts))
        return alerts

    def send_telegram(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "disable_web_page_preview": True,
        }
        response = self.session.post(url, json=payload, timeout=20)
        response.raise_for_status()

    @staticmethod
    def _to_float(value: Optional[object]) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def run(self) -> None:
        self.verify_telegram_config()

        excluded = ", ".join(sorted(EXCLUDED_CATEGORIES)) if EXCLUDED_CATEGORIES else "none"
        if STARTUP_TEST_MESSAGE:
            self.send_telegram(
                "✅ Polymarket spike bot started. "
                f"Threshold={SPIKE_THRESHOLD:.0%}, min24h=${MIN_NOTIONAL_24H:,.0f}, excluded={excluded}"
            )

        while True:
            try:
                markets = self.fetch_markets()
                alerts = self.detect_spikes(markets)
                for alert in alerts:
                    self.send_telegram(alert)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Bot loop failure")
                try:
                    self.send_telegram(f"⚠️ Bot error: {exc}")
                except Exception:  # noqa: BLE001
                    logger.exception("Failed to send Telegram error message")

            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    PolymarketSpikeBot().run()
