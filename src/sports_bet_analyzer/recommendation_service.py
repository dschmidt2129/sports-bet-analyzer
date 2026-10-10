"""Coordinates ESPN data collection, history persistence, and bet ranking."""
import logging

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
    def __init__(self, client=None, predictor=None, history=None):
        self.client = client or ESPNClient()
        self.predictor = predictor or Predictor()
        self.history = history or HistoryStore()
        self._team_stats_cache = {}

    def load_recommendations(self, leagues):
        fpi_cache = self._load_fpi_cache(leagues)
        games = []
        for league in leagues:
            raw = self.client.scoreboard(league)
            league_games = parse_games_from_scoreboard(raw, league)
            games.extend(league_games)
            week = league_games[0].week if league_games else None
            self._persist_full_league_stats(league, week, fpi_cache.get(league, {}))
        log.info("Fetched %d game(s) across %d league(s)", len(games), len(leagues))
        self._apply_fpi(games, fpi_cache)
        enrich_games_with_team_stats(self.client, games, cache=self._team_stats_cache)
        self._persist_history(games)
        return rank_games(games, self.predictor)

    def _persist_full_league_stats(self, league, week, fpi_ratings):
        league_teams = fetch_all_league_team_stats(self.client, league, cache=self._team_stats_cache)
        log.info(
            "Persisting full-league stat snapshot league=%s week=%s (%d team(s))",
            league,
            week,
            len(league_teams),
        )
        for team in league_teams.values():
            team.fpi = fpi_ratings.get(team.team_id, team.fpi)
            self.history.save_team_stat_snapshot(league, team, week or 0)

    def _persist_history(self, games):
        log.debug("Persisting history for %d game(s)", len(games))
        fill_missing_odds(self.client, [game for game in games if game.completed])
        for game in games:
            self.history.save_game_result(game)
            week = game.week or 0
            self.history.save_team_stat_snapshot(game.league, game.home_team, week)
            self.history.save_team_stat_snapshot(game.league, game.away_team, week)

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
