"""Kivy app entry point. Fetches this week's games and shows ranked high-probability bets."""
import logging

from kivy.app import App
from kivy.clock import mainthread
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen, ScreenManager
from kivy.uix.scrollview import ScrollView

from sports_bet_analyzer.espn_client import (
    ESPNClient,
    enrich_games_with_team_stats,
    fetch_all_league_team_stats,
    parse_games_from_scoreboard,
)
from sports_bet_analyzer.models import TeamStats
from sports_bet_analyzer.predictor import Predictor
from sports_bet_analyzer.recommender import rank_games
from sports_bet_analyzer.storage import HistoryStore

log = logging.getLogger(__name__)

LEAGUES = ("nfl", "college-football")


class RecommendationsScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.client = ESPNClient()
        self.predictor = Predictor()
        self.history = HistoryStore()
        self._team_stats_cache = {}

        root = BoxLayout(orientation="vertical")
        self.status_label = Label(text="Tap refresh to load this week's games.", size_hint_y=None, height=40)
        refresh_button = Button(text="Refresh", size_hint_y=None, height=48)
        refresh_button.bind(on_release=lambda *_: self.refresh())

        self.results_box = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6, padding=6)
        self.results_box.bind(minimum_height=self.results_box.setter("height"))
        scroll = ScrollView()
        scroll.add_widget(self.results_box)

        root.add_widget(refresh_button)
        root.add_widget(self.status_label)
        root.add_widget(scroll)
        self.add_widget(root)

    def refresh(self):
        log.info("Refresh triggered")
        self.status_label.text = "Loading..."
        self.results_box.clear_widgets()
        try:
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
            recommendations = rank_games(games, self.predictor)
            self._render(recommendations)
        except Exception:
            log.exception("Failed to refresh recommendations")
            self.status_label.text = "Failed to load games. Check your connection and try again."

    def _persist_full_league_stats(self, league, week, fpi_ratings):
        """Persists a stat snapshot for every team in the league, including teams on a bye."""
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
        for game in games:
            if game.completed:
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

    @mainthread
    def _render(self, recommendations):
        if not recommendations:
            log.info("No high-probability bets found this refresh")
            self.status_label.text = "No high-probability bets found this week."
            return

        log.info("Rendering %d recommendation(s)", len(recommendations))
        self.status_label.text = f"{len(recommendations)} high-probability bet(s) found."
        for rec in recommendations:
            text = f"[{rec.bet_type.upper()}] {rec.selection} - {rec.probability:.0%}\n{rec.reasoning}"
            self.results_box.add_widget(Label(text=text, size_hint_y=None, height=70, halign="left"))


class SportsBetApp(App):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(RecommendationsScreen(name="recommendations"))
        return sm


def main():
    logging.basicConfig(level=logging.INFO)
    SportsBetApp().run()


if __name__ == "__main__":
    main()
