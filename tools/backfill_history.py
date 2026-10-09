"""Backfills the local SQLite history store with completed games from earlier weeks.

app/main.py only fetches the *current* week on each refresh, so any week you
weren't running the app during is otherwise never captured. Run this once (or
whenever you fall behind) to catch the history store up:

    python tools/backfill_history.py --league nfl --start-week 1 --end-week 3
"""
import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sports_bet_analyzer.espn_client import (
    ESPNClient,
    enrich_games_with_team_stats,
    fetch_all_league_team_stats,
    parse_games_from_scoreboard,
)  # noqa: E402
from sports_bet_analyzer.storage import HistoryStore  # noqa: E402

log = logging.getLogger(__name__)

# Typical regular-season week counts; --end-week overrides this.
MAX_WEEK = {"nfl": 18, "college-football": 15}
# college-football scoreboard defaults to ranked-only games; groups=80 returns all FBS games.
GROUPS_BY_LEAGUE = {"nfl": None, "college-football": 80}


def load_fpi_ratings(client, league):
    raw = client.fpi(league)
    if not raw:
        return {}
    return {entry.get("team", {}).get("id"): entry.get("fpi") for entry in raw.get("teams", [])}


def backfill(client, store, league, start_week, end_week, delay_seconds=0.5):
    """Fetches each week's scoreboard and persists completed games + team snapshots."""
    fpi_ratings = load_fpi_ratings(client, league)
    groups = GROUPS_BY_LEAGUE.get(league)
    team_stats_cache = {}
    total_saved = 0

    # Full-league coverage: every team's season-to-date stats, not just teams with a game.
    league_teams = fetch_all_league_team_stats(client, league, cache=team_stats_cache)
    for team in league_teams.values():
        team.fpi = fpi_ratings.get(team.team_id, team.fpi)

    for week in range(start_week, end_week + 1):
        raw = client.scoreboard(league, week=week, groups=groups)
        games = parse_games_from_scoreboard(raw, league)
        log.info("Week %d: fetched %d game(s)", week, len(games))

        # Season-to-date stats only (ESPN has no historical per-week stats endpoint),
        # so earlier weeks' snapshots are an approximation using current-season stats.
        enrich_games_with_team_stats(client, games, cache=team_stats_cache)

        for game in games:
            game.home_team.fpi = fpi_ratings.get(game.home_team.team_id)
            game.away_team.fpi = fpi_ratings.get(game.away_team.team_id)

            if game.completed:
                store.save_game_result(game)
                total_saved += 1
            else:
                log.debug("Skipping incomplete game_id=%s for history", game.game_id)

            store.save_team_stat_snapshot(game.league, game.home_team, week)
            store.save_team_stat_snapshot(game.league, game.away_team, week)

        for team in league_teams.values():
            store.save_team_stat_snapshot(league, team, week)
        log.info("Week %d: persisted full-league snapshot for %d team(s)", week, len(league_teams))

        if week != end_week:
            time.sleep(delay_seconds)

    log.info(
        "Backfill complete: saved %d completed game(s) across weeks %d-%d for league=%s",
        total_saved, start_week, end_week, league,
    )
    return total_saved


def main():
    parser = argparse.ArgumentParser(
        description="Backfill completed games from earlier weeks into the local history DB."
    )
    parser.add_argument("--league", default="nfl", choices=["nfl", "college-football"])
    parser.add_argument("--db", default="sports_bet_analyzer.db")
    parser.add_argument("--start-week", type=int, default=1)
    parser.add_argument(
        "--end-week", type=int, default=None,
        help="Defaults to the league's typical max regular-season week",
    )
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds to wait between week requests")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    end_week = args.end_week or MAX_WEEK[args.league]
    if end_week < args.start_week:
        parser.error("--end-week must be >= --start-week")

    client = ESPNClient()
    store = HistoryStore(args.db)
    backfill(client, store, args.league, args.start_week, end_week, args.delay)


if __name__ == "__main__":
    main()
