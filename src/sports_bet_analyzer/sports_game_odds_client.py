"""Client for SportsGameOdds event and player-prop odds data."""
import logging
import os
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

log = logging.getLogger(__name__)

load_dotenv()

BASE = "https://api.sportsgameodds.com/v2"
DEFAULT_TIMEOUT = 10
_TEAM_ENTITIES = {"all", "home", "away"}


class SportsGameOddsClient:
    def __init__(self, api_key=None, session=None, timeout=DEFAULT_TIMEOUT):
        self.api_key = api_key if api_key is not None else os.getenv("SPORTSGAMEODDS_API_KEY")
        self.session = session or requests.Session()
        self.timeout = timeout

    def events(self, league_id="NFL", limit=100, finalized=None):
        """Fetch events with odds; an empty list is returned on configuration/API errors."""
        if not self.api_key:
            log.warning("SPORTSGAMEODDS_API_KEY is not configured; skipping player props")
            return []

        params = {
            "apiKey": self.api_key,
            "leagueID": league_id,
            "oddsAvailable": "true",
            "limit": limit,
        }
        if finalized is not None:
            params["finalized"] = str(finalized).lower()

        log.info("Fetching SportsGameOdds events league=%s limit=%d", league_id, limit)
        try:
            response = self.session.get(f"{BASE}/events", params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            log.warning("SportsGameOdds request failed league=%s", league_id, exc_info=True)
            return []

        events = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            log.warning("SportsGameOdds response malformed league=%s", league_id)
            return []
        return events


def parse_player_prop_quotes(events, league="nfl", captured_at=None):
    """Flatten SportsGameOdds events into one row per player/side/book quote."""
    captured_at = captured_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    quotes = []
    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict):
            continue
        event_id = event.get("eventID")
        players = event.get("players") or {}
        odds = event.get("odds") or {}
        if not event_id or not isinstance(players, dict) or not isinstance(odds, dict):
            continue

        for odd_id, market in odds.items():
            if not isinstance(market, dict) or market.get("betTypeID") != "ou":
                continue
            side_id = str(market.get("sideID", "")).lower()
            player_id = market.get("playerID") or market.get("statEntityID")
            if side_id not in {"over", "under"} or not player_id or player_id in _TEAM_ENTITIES:
                continue

            player = players.get(player_id) or {}
            player_name = player.get("name") or market.get("marketName")
            stat_id = market.get("statID")
            if not player_name or not stat_id:
                continue

            bookmaker_quotes = market.get("byBookmaker") or {}
            if not isinstance(bookmaker_quotes, dict):
                continue
            for bookmaker_id, bookmaker_quote in bookmaker_quotes.items():
                if not isinstance(bookmaker_quote, dict) or not bookmaker_quote.get("available", True):
                    continue
                line = _number(bookmaker_quote.get("overUnder", market.get("bookOverUnder")))
                price = _american_odds(bookmaker_quote.get("odds"))
                if line is None or price is None:
                    continue

                quotes.append(
                    {
                        "event_id": str(event_id),
                        "league": league.lower(),
                        "odd_id": str(market.get("oddID") or odd_id),
                        "player_id": str(player_id),
                        "player_name": str(player_name),
                        "team_id": player.get("teamID"),
                        "stat_id": str(stat_id),
                        "period_id": str(market.get("periodID") or "game"),
                        "side_id": side_id,
                        "bookmaker_id": str(bookmaker_id),
                        "line": line,
                        "odds": price,
                        "fair_odds": _american_odds(market.get("fairOdds")),
                        "season_avg": _number(player.get("seasonAvg")),
                        "last3_avg": _number(player.get("last3Avg")),
                        "opponent_defense_ypp_allowed": _number(
                            player.get("opponentDefenseYardsPerPlayAllowed")
                        ),
                        "actual_value": _number(market.get("score")),
                        "captured_at": captured_at,
                    }
                )
    return quotes


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _american_odds(value):
    number = _number(value)
    return int(number) if number is not None else None