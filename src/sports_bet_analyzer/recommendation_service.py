"""Coordinates ESPN data collection, history persistence, and bet ranking."""
import logging
import time

from sports_bet_analyzer.espn_client import (
    ESPNClient,
    enrich_games_with_team_stats,
    fetch_all_league_team_stats,
    fill_missing_odds,
    parse_games_from_scoreboard,
)
from sports_bet_analyzer.predictor import Predictor
from sports_bet_analyzer.recommender import rank_games
from sports_bet_analyzer.storage import HistoryStore

log = logging.getLogger(__name__)


def _extract_fpi(entry):
    for category in entry.get("categories", []):
        if category.get("name") == "fpi":
            values = category.get("values") or []
            return values[0] if values else None
    return None


class RecommendationService:
    def __init__(self, client=None, predictor=None, history=None, cache_ttl_seconds=600):
        self.client = client or ESPNClient()
        self.predictor = predictor or Predictor()
        self.history = history or HistoryStore()
        self.cache_ttl_seconds = cache_ttl_seconds
        self._team_stats_cache = {}
        self._recommendation_cache = {}

    def load_recommendations(self, leagues):
        """Rank bets for the leagues, reusing results fetched within the cache TTL."""
        key = tuple(leagues)
        now = time.monotonic()
        cached = self._recommendation_cache.get(key)
        if cached and now - cached[0] < self.cache_ttl_seconds:
            log.debug("Serving cached recommendations leagues=%s", key)
            return list(cached[1])
        results, failed = self._load_recommendations(leagues)
        if results and not failed:
            self._recommendation_cache[key] = (now, results)
        else:
            log.info("Not caching recommendations leagues=%s (empty=%s failed=%s)", key, not results, failed)
        return list(results)

    def _load_recommendations(self, leagues):
        """Return (ranked results, whether any ESPN request failed)."""
        failed = False
        not_found_at_start = self._not_found_count()
        fpi_cache = self._load_fpi_cache(leagues)
        games = []
        for league in leagues:
            raw = self.client.scoreboard(league)
            if raw is None:
                log.warning("Skipping league history persistence after scoreboard failure league=%s", league)
                failed = True
                continue
            league_games = parse_games_from_scoreboard(raw, league)
            games.extend(league_games)
            week = league_games[0].week if league_games else None
            self._persist_full_league_stats(league, week, fpi_cache.get(league, {}))
        log.info("Fetched %d game(s) across %d league(s)", len(games), len(leagues))
        self._apply_fpi(games, fpi_cache)
        not_found_before = self._not_found_count()
        enrich_games_with_team_stats(self.client, games, cache=self._team_stats_cache)
        if self._not_found_count() != not_found_before:
            log.warning("Skipping history persistence after ESPN 404 during team stats fetch")
        else:
            self._persist_history(games)
        failed = failed or self._not_found_count() != not_found_at_start
        return rank_games(games, self.predictor), failed

    def _not_found_count(self):
        return getattr(self.client, "not_found_count", 0)

    def _persist_full_league_stats(self, league, week, fpi_ratings):
        not_found_before = self._not_found_count()
        league_teams = fetch_all_league_team_stats(self.client, league, cache=self._team_stats_cache)
        if self._not_found_count() != not_found_before:
            log.warning("Skipping full-league persistence after ESPN 404 league=%s", league)
            return
        log.info(
            "Persisting full-league stat snapshot league=%s week=%s (%d team(s))",
            league,
            week,
            len(league_teams),
        )
        for team in league_teams.values():
            team.fpi = fpi_ratings.get(team.team_id, team.fpi)
            self.history.save_team_stat_snapshot(league, team, week or 0, source="live")

    def _persist_history(self, games):
        log.debug("Persisting history for %d game(s)", len(games))
        fill_missing_odds(self.client, [game for game in games if game.completed])
        for game in games:
            self.history.save_game_result(game)
            week = game.week or 0
            self.history.save_team_stat_snapshot(game.league, game.home_team, week, source="live")
            self.history.save_team_stat_snapshot(game.league, game.away_team, week, source="live")

    def _load_fpi_cache(self, leagues):
        fpi_cache = {}
        for league in leagues:
            raw = self.client.fpi(league)
            fpi_cache[league] = {
                entry.get("team", {}).get("id"): _extract_fpi(entry)
                for entry in raw.get("teams", [])
            } if raw else {}
            log.debug("Loaded %d FPI rating(s) for league=%s", len(fpi_cache[league]), league)
        return fpi_cache

    def _apply_fpi(self, games, fpi_cache):
        for game in games:
            ratings = fpi_cache.get(game.league, {})
            game.home_team.fpi = ratings.get(game.home_team.team_id)
            game.away_team.fpi = ratings.get(game.away_team.team_id)
