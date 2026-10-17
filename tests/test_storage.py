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