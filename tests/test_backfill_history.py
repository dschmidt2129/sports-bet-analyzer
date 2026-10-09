import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from backfill_history import backfill  # noqa: E402


class FakeClient:
    def __init__(self, games_by_week, league_teams=None):
        self.games_by_week = games_by_week
        self.league_teams = league_teams or []
        self.requested_weeks = []

    def scoreboard(self, league, week=None, groups=None):
        self.requested_weeks.append(week)
        return self.games_by_week.get(week, {"events": []})

    def teams(self, league):
        return {
            "sports": [{"leagues": [{"teams": [
                {"team": {"id": team_id, "displayName": team_id}} for team_id in self.league_teams
            ]}]}]
        }

    def team_statistics(self, league, team_id):
        return {}

    def fpi(self, league):
        return {}


class FakeStore:
    def __init__(self):
        self.saved_games = []
        self.saved_snapshots = []

    def save_game_result(self, game):
        self.saved_games.append(game.game_id)

    def save_team_stat_snapshot(self, league, team_stats, as_of_week):
        self.saved_snapshots.append((team_stats.team_id, as_of_week))


def _event(event_id, completed=True):
    return {
        "id": event_id,
        "date": "2026-09-21T17:00Z",
        "week": {"number": 1},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "score": "21", "team": {"id": "1", "displayName": "Home"}},
                    {"homeAway": "away", "score": "14", "team": {"id": "2", "displayName": "Away"}},
                ],
                "status": {"type": {"completed": completed}},
            }
        ],
    }


def test_backfill_saves_only_completed_games_across_weeks():
    games_by_week = {
        1: {"events": [_event("g1", completed=True)]},
        2: {"events": [_event("g2", completed=False)]},
    }
    client = FakeClient(games_by_week)
    store = FakeStore()

    total_saved = backfill(client, store, "nfl", start_week=1, end_week=2, delay_seconds=0)

    assert total_saved == 1
    assert store.saved_games == ["g1"]
    assert client.requested_weeks == [1, 2]
    assert len(store.saved_snapshots) == 4  # 2 teams x 2 weeks


def test_backfill_persists_full_league_coverage_including_bye_teams():
    games_by_week = {1: {"events": [_event("g1", completed=True)]}}
    client = FakeClient(games_by_week, league_teams=["1", "2", "3"])
    store = FakeStore()

    backfill(client, store, "nfl", start_week=1, end_week=1, delay_seconds=0)

    snapshotted_team_ids = {team_id for team_id, _ in store.saved_snapshots}
    assert snapshotted_team_ids == {"1", "2", "3"}
