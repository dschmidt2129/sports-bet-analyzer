"""Coordinates player-prop odds collection, caching, and history persistence."""
import logging
import time
from datetime import datetime, timezone

from sports_bet_analyzer.sports_game_odds_client import (
    SportsGameOddsClient,
    parse_player_prop_quotes,
)
from sports_bet_analyzer.storage import HistoryStore

log = logging.getLogger(__name__)

LEAGUE_IDS = {"nfl": "NFL", "college-football": "NCAAF"}


class PlayerPropService:
    def __init__(self, client=None, history=None, cache_ttl_seconds=600):
        self.client = client if client is not None else SportsGameOddsClient()
        self.history = history if history is not None else HistoryStore()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache = {}
        self.last_refreshed_at = None

    def load_player_props(self, league="nfl"):
        """Fetch upcoming props for a league, retaining quote snapshots for training."""
        if league not in LEAGUE_IDS:
            raise ValueError(f"Unsupported player-prop league: {league}")

        now = time.monotonic()
        cached = self._cache.get(league)
        if cached and now - cached[0] < self.cache_ttl_seconds:
            return list(cached[1])

        events = self.client.events(league_id=LEAGUE_IDS[league], limit=100)
        captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        quotes = parse_player_prop_quotes(events, league=league, captured_at=captured_at)
        for quote in quotes:
            self.history.save_player_prop_snapshot(quote)

        self._cache[league] = (now, quotes)
        self.last_refreshed_at = datetime.now(timezone.utc)
        log.info("Loaded %d player-prop quote(s) league=%s", len(quotes), league)
        return list(quotes)