"""BeeWare app entry point. Fetches games and shows ranked recommendations."""
import asyncio
import logging

import toga
from toga.style import Pack
from toga.style.pack import COLUMN, ROW

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

LEAGUES = ("nfl", "college-football")


class SportsBetApp(toga.App):
    def startup(self):
        self.client = ESPNClient()
        self.predictor = Predictor()
        self.history = HistoryStore()
        self._team_stats_cache = {}

        self.status_label = toga.Label(
            "Tap refresh to load this week's games.",
            style=Pack(padding=5),
        )
        self.refresh_button = toga.Button(
            "Refresh",
            on_press=self.refresh,
            style=Pack(padding=5),
        )
        self.results_box = toga.Box(style=Pack(direction=COLUMN, flex=1, padding=5))
        results_scroll = toga.ScrollContainer(
            content=self.results_box,
            horizontal=False,
            style=Pack(flex=1),
        )
        root = toga.Box(
            children=[self.refresh_button, self.status_label, results_scroll],
            style=Pack(direction=COLUMN, flex=1, padding=5),
        )

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = root
        self.main_window.show()

    async def refresh(self, widget):
        log.info("Refresh triggered")
        self.status_label.text = "Loading..."
        self.refresh_button.enabled = False
        self.results_box.remove(*self.results_box.children)
        try:
            recommendations = await asyncio.to_thread(self._load_recommendations)
        except Exception:
            log.exception("Failed to refresh recommendations")
            self.status_label.text = "Failed to load games. Check your connection and try again."
        else:
            self._render(recommendations)
        finally:
            self.refresh_button.enabled = True

    def _load_recommendations(self):
        fpi_cache = self._load_fpi_cache()
        games = []
        for league in LEAGUES:
            raw = self.client.scoreboard(league)
            league_games = parse_games_from_scoreboard(raw, league)
            games.extend(league_games)
            week = league_games[0].week if league_games else None
            self._persist_full_league_stats(league, week, fpi_cache.get(league, {}))
        log.info("Fetched %d game(s) across %d league(s)", len(games), len(LEAGUES))
        self._apply_fpi(games, fpi_cache)
        enrich_games_with_team_stats(self.client, games, cache=self._team_stats_cache)
        self._persist_history(games)
        return rank_games(games, self.predictor)

    def _persist_full_league_stats(self, league, week, fpi_ratings):
        """Persists a stat snapshot for every team, including teams on a bye."""
        league_teams = fetch_all_league_team_stats(self.client, league, cache=self._team_stats_cache)
        log.info(
            "Persisting full-league stat snapshot league=%s week=%s (%d team(s))",
            league, week, len(league_teams),
        )
        for team in league_teams.values():
            team.fpi = fpi_ratings.get(team.team_id, team.fpi)
            self.history.save_team_stat_snapshot(league, team, week or 0)

    def _persist_history(self, games):
        log.debug("Persisting history for %d game(s)", len(games))
        fill_missing_odds(self.client, [game for game in games if game.completed])
        for game in games:
            # Upcoming games are saved too so their pre-game line is captured before ESPN drops it.
            self.history.save_game_result(game)
            week = game.week or 0
            self.history.save_team_stat_snapshot(game.league, game.home_team, week)
            self.history.save_team_stat_snapshot(game.league, game.away_team, week)

    def _load_fpi_cache(self):
        fpi_cache = {}
        for league in LEAGUES:
            raw = self.client.fpi(league)
            fpi_cache[league] = {
                entry.get("team", {}).get("id"): entry.get("fpi")
                for entry in raw.get("teams", [])
            } if raw else {}
            log.debug("Loaded %d FPI rating(s) for league=%s", len(fpi_cache[league]), league)
        return fpi_cache

    def _apply_fpi(self, games, fpi_cache):
        for game in games:
            ratings = fpi_cache.get(game.league, {})
            game.home_team.fpi = ratings.get(game.home_team.team_id)
            game.away_team.fpi = ratings.get(game.away_team.team_id)

    def _render(self, recommendations):
        if not recommendations:
            log.info("No high-probability bets found this refresh")
            self.status_label.text = "No high-probability bets found this week."
            return

        log.info("Rendering %d recommendation(s)", len(recommendations))
        self.status_label.text = f"{len(recommendations)} high-probability bet(s) found."

        header = toga.Box(style=Pack(direction=ROW, padding_bottom=5))
        for text, flex in (
            ("Home Team", 0.23),
            ("Away Team", 0.23),
            ("Recommendation", 0.54),
        ):
            header.add(
                toga.Label(text, style=Pack(flex=flex, font_weight="bold", padding=3))
            )
        self.results_box.add(header)

        for rec in recommendations:
            row = toga.Box(style=Pack(direction=ROW, padding_bottom=5))
            cells = (
                (rec.home_team_name, 0.23),
                (rec.away_team_name, 0.23),
                (
                    f"[{rec.bet_type.upper()}] {rec.selection} - {rec.probability:.0%}\n"
                    f"{rec.reasoning}",
                    0.54,
                ),
            )
            for text, flex in cells:
                row.add(toga.Label(text, style=Pack(flex=flex, padding=3)))
            self.results_box.add(row)


def main():
    return SportsBetApp(
        formal_name="Sports Bet Analyzer",
        app_id="org.sportsbetanalyzer",
    )


if __name__ == "__main__":
    main().main_loop()
