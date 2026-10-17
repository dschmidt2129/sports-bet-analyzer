import sqlite3
from contextlib import closing

from sports_bet_analyzer.models import TeamStats
from sports_bet_analyzer.storage import HistoryStore


def test_existing_snapshots_are_migrated_as_legacy(tmp_path):
    db_path = tmp_path / "history.db"
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE team_stat_snapshots (
                league TEXT NOT NULL,
                team_id TEXT NOT NULL,
                as_of_week INTEGER NOT NULL,
                points_per_game REAL,
                points_allowed_per_game REAL,
                yards_per_play REAL,
                yards_allowed_per_play REAL,
                turnover_margin REAL,
                win_pct REAL,
                fpi REAL,
                PRIMARY KEY (league, team_id, as_of_week)
            )
            """
        )
        conn.execute(
            "INSERT INTO team_stat_snapshots (league, team_id, as_of_week) VALUES (?, ?, ?)",
            ("nfl", "team-1", 1),
        )
        conn.commit()

    store = HistoryStore(str(db_path))

    snapshot = store.team_stat_snapshot("nfl", "team-1", 1)
    assert snapshot["source"] == "legacy"
    assert snapshot["captured_at"] == "1970-01-01 00:00:00"
    assert store.team_stat_snapshot("nfl", "team-1", 1, source="live") is None


def test_live_snapshot_is_available_to_training_queries(tmp_path):
    store = HistoryStore(str(tmp_path / "history.db"))
    team = TeamStats(team_id="team-1", name="Team One")

    store.save_team_stat_snapshot("nfl", team, 1, source="live")

    snapshot = store.team_stat_snapshot("nfl", "team-1", 1, source="live")
    assert snapshot is not None
    assert snapshot["source"] == "live"
    assert snapshot["captured_at"]


def test_snapshot_is_not_overwritten_within_three_days(tmp_path):
    store = HistoryStore(str(tmp_path / "history.db"))
    original = TeamStats(team_id="team-1", name="Team One", points_per_game=20.0)
    refreshed = TeamStats(team_id="team-1", name="Team One", points_per_game=30.0)

    store.save_team_stat_snapshot("nfl", original, 1, source="live")
    first = store.team_stat_snapshot("nfl", "team-1", 1, source="live")
    store.save_team_stat_snapshot("nfl", refreshed, 1, source="live")
    second = store.team_stat_snapshot("nfl", "team-1", 1, source="live")

    assert first["points_per_game"] == 20.0
    assert second["points_per_game"] == 20.0
    assert second["captured_at"] == first["captured_at"]


def test_snapshot_can_be_overwritten_after_three_days(tmp_path):
    db_path = str(tmp_path / "history.db")
    store = HistoryStore(db_path)
    original = TeamStats(team_id="team-1", name="Team One", points_per_game=20.0)
    refreshed = TeamStats(team_id="team-1", name="Team One", points_per_game=30.0)

    store.save_team_stat_snapshot("nfl", original, 1, source="live")
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "UPDATE team_stat_snapshots SET captured_at = datetime('now', '-4 days')"
        )
        conn.commit()

    store.save_team_stat_snapshot("nfl", refreshed, 1, source="live")

    snapshot = store.team_stat_snapshot("nfl", "team-1", 1, source="live")
    assert snapshot["points_per_game"] == 30.0
    assert snapshot["captured_at"] != "1970-01-01 00:00:00"


def test_player_prop_snapshot_is_ml_ready_and_keeps_capture_history(tmp_path):
    store = HistoryStore(str(tmp_path / "history.db"))
    prop = {
        "event_id": "event-1",
        "league": "nfl",
        "odd_id": "passing_yards-player-1-game-ou-over",
        "player_id": "player-1",
        "player_name": "Player One",
        "team_id": "team-1",
        "stat_id": "passing_yards",
        "period_id": "game",
        "side_id": "over",
        "bookmaker_id": "book-a",
        "line": 245.5,
        "odds": -110,
        "fair_odds": -105,
        "season_avg": 250.0,
        "last3_avg": 270.0,
        "opponent_defense_ypp_allowed": 5.5,
        "actual_value": 260.0,
        "captured_at": "2026-10-16T12:00:00+00:00",
    }

    store.save_player_prop_snapshot(prop)
    store.save_player_prop_snapshot({**prop, "odds": -115})
    store.save_player_prop_snapshot({**prop, "captured_at": "2026-10-16T12:10:00+00:00"})

    rows = store.player_prop_training_rows("nfl")
    assert len(rows) == 2
    assert rows[0]["over_hit"] == 1
    assert rows[0]["last3_avg"] == 270.0
    assert rows[0]["odds"] == -115
    assert rows[1]["captured_at"] == "2026-10-16T12:10:00+00:00"