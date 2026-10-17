"""Coordinates player-prop odds collection, caching, and history persistence."""
import logging
import time
from datetime import datetime, timedelta, timezone

from sports_bet_analyzer import features as feat
from sports_bet_analyzer.predictor import Predictor
from sports_bet_analyzer.sports_game_odds_client import (
    SportsGameOddsClient,
    parse_player_prop_quotes,
)
from sports_bet_analyzer.storage import HistoryStore

log = logging.getLogger(__name__)

LEAGUE_IDS = {"nfl": "NFL", "college-football": "NCAAF"}


def current_week_window(now=None):
    """Wednesday 00:00 UTC to the next Wednesday, which spans Thursday-through-Monday NFL games."""
    now = now or datetime.now(timezone.utc)
    start = (now - timedelta(days=(now.weekday() - 2) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=7)


def _starts_in_window(event, start, end):
    # The provider's date filters weren't enough on their own, so each event's start is checked here.
    status = event.get("status") if isinstance(event, dict) else None
    starts_at = status.get("startsAt") if isinstance(status, dict) else None
    if not isinstance(starts_at, str):
        return False
    try:
        starts = datetime.fromisoformat(starts_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=timezone.utc)
    return start <= starts < end and not status.get("finalized") and not status.get("cancelled")


class PlayerPropService:
    def __init__(self, client=None, history=None, cache_ttl_seconds=600, predictor=None):
        self.client = client if client is not None else SportsGameOddsClient()
        self.history = history if history is not None else HistoryStore()
        self.predictor = predictor if predictor is not None else Predictor()
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

        log.info("Started player-prop load league=%s", league)
        week_start, week_end = current_week_window()
        events = self.client.events(
            league_id=LEAGUE_IDS[league],
            limit=100,
            finalized=False,
            starts_after=week_start,
            starts_before=week_end,
        )
        fetched = len(events)
        events = [event for event in events if _starts_in_window(event, week_start, week_end)]
        log.info("Kept %d of %d event(s) starting this week league=%s", len(events), fetched, league)
        captured_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        quotes = parse_player_prop_quotes(events, league=league, captured_at=captured_at)
        if not quotes:
            log.warning("No player-prop quotes league=%s (events=%d)", league, len(events))
        for quote in quotes:
            self.history.save_player_prop_snapshot(quote)

        self._cache[league] = (now, quotes)
        self.last_refreshed_at = datetime.now(timezone.utc)
        log.info("Loaded %d player-prop quote(s) league=%s", len(quotes), league)
        return list(quotes)

    def ranked_player_props(self, league="nfl"):
        """Return all quotes (best book per market) ordered by probability of hitting, highest first."""
        best = {}
        for quote in self.load_player_props(league):
            probability = self._hit_probability(quote)
            if probability is None:
                continue
            key = (quote["event_id"], quote["odd_id"])
            current = best.get(key)
            if current is None or (probability, quote["odds"]) > (current["probability"], current["odds"]):
                best[key] = {**quote, "probability": probability}
        ranked = sorted(best.values(), key=lambda q: q["probability"], reverse=True)
        log.info("Ranked %d player prop(s) league=%s", len(ranked), league)
        return ranked

    def _hit_probability(self, quote):
        features = feat.player_prop_hit_features(quote)
        if features is not None:
            probability = self.predictor.predict_probability(feat.PLAYER_PROP_BET_TYPE, features)
            if probability is not None:
                return probability
        # No trained model or player averages: fall back to the book's fair (no-vig) price.
        return feat.american_to_probability(quote.get("fair_odds"))