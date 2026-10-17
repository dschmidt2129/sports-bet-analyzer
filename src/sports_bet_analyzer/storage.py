"""Local SQLite history store so the model can accumulate its own season data.

Stdlib-only (sqlite3) so it works unmodified in the packaged mobile app.
"""
import logging
import sqlite3
from contextlib import closing

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    game_id TEXT PRIMARY KEY,
    league TEXT NOT NULL,
    week INTEGER,
    date TEXT,
    home_team_id TEXT,
    away_team_id TEXT,
    home_score INTEGER,
    away_score INTEGER,
    home_spread REAL,
    over_under REAL,
    completed INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS team_stat_snapshots (
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
    source TEXT NOT NULL DEFAULT 'legacy',
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (league, team_id, as_of_week)
);

CREATE TABLE IF NOT EXISTS player_prop_snapshots (
    event_id TEXT NOT NULL,
    league TEXT NOT NULL,
    odd_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    player_name TEXT NOT NULL,
    team_id TEXT,
    stat_id TEXT NOT NULL,
    period_id TEXT NOT NULL,
    side_id TEXT NOT NULL,
    bookmaker_id TEXT NOT NULL,
    line REAL,
    odds INTEGER,
    fair_odds INTEGER,
    season_avg REAL,
    last3_avg REAL,
    opponent_defense_ypp_allowed REAL,
    actual_value REAL,
    over_hit INTEGER,
    source TEXT NOT NULL DEFAULT 'sportsgameodds',
    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id, odd_id, bookmaker_id, captured_at)
);
CREATE INDEX IF NOT EXISTS idx_player_prop_training
    ON player_prop_snapshots (league, stat_id, over_hit);
"""


class HistoryStore:
    def __init__(self, db_path="sports_bet_analyzer.db"):
        self.db_path = db_path
        log.info("Opening history store at %s", db_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.executescript(SCHEMA)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(team_stat_snapshots)")}
            if "source" not in columns:
                conn.execute(
                    "ALTER TABLE team_stat_snapshots ADD COLUMN source TEXT NOT NULL DEFAULT 'legacy'"
                )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(team_stat_snapshots)")}
            if "captured_at" not in columns:
                conn.execute("ALTER TABLE team_stat_snapshots ADD COLUMN captured_at TEXT")
                conn.execute(
                    """
                    UPDATE team_stat_snapshots
                    SET captured_at = CASE
                        WHEN source = 'live' THEN CURRENT_TIMESTAMP
                        ELSE '1970-01-01 00:00:00'
                    END
                    WHERE captured_at IS NULL
                    """
                )
            conn.commit()

    def save_game_result(self, game):
        log.debug("Saving game result game_id=%s completed=%s", game.game_id, game.completed)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO games (
                    game_id, league, week, date, home_team_id, away_team_id,
                    home_score, away_score, home_spread, over_under, completed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(game_id) DO UPDATE SET
                    home_score=excluded.home_score,
                    away_score=excluded.away_score,
                    home_spread=COALESCE(excluded.home_spread, games.home_spread),
                    over_under=COALESCE(excluded.over_under, games.over_under),
                    completed=excluded.completed
                """,
                (
                    game.game_id,
                    game.league,
                    game.week,
                    game.date,
                    game.home_team.team_id,
                    game.away_team.team_id,
                    game.home_score,
                    game.away_score,
                    game.odds.home_spread if game.odds else None,
                    game.odds.over_under if game.odds else None,
                    int(game.completed),
                ),
            )
            conn.commit()

    def save_team_stat_snapshot(self, league, team_stats, as_of_week, source="unverified"):
        log.debug(
            "Saving team stat snapshot league=%s team_id=%s week=%s", league, team_stats.team_id, as_of_week
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO team_stat_snapshots (
                    league, team_id, as_of_week, points_per_game, points_allowed_per_game,
                    yards_per_play, yards_allowed_per_play, turnover_margin, win_pct, fpi,
                    source, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(league, team_id, as_of_week) DO UPDATE SET
                    points_per_game=excluded.points_per_game,
                    points_allowed_per_game=excluded.points_allowed_per_game,
                    yards_per_play=excluded.yards_per_play,
                    yards_allowed_per_play=excluded.yards_allowed_per_play,
                    turnover_margin=excluded.turnover_margin,
                    win_pct=excluded.win_pct,
                    fpi=excluded.fpi,
                    source=excluded.source,
                    captured_at=excluded.captured_at
                WHERE datetime(team_stat_snapshots.captured_at) <= datetime('now', '-3 days')
                """,
                (
                    league,
                    team_stats.team_id,
                    as_of_week,
                    team_stats.points_per_game,
                    team_stats.points_allowed_per_game,
                    team_stats.yards_per_play,
                    team_stats.yards_allowed_per_play,
                    team_stats.turnover_margin,
                    team_stats.win_pct,
                    team_stats.fpi,
                    source,
                ),
            )
            conn.commit()

    def completed_games(self, league):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM games WHERE league = ? AND completed = 1", (league,)
            ).fetchall()
            log.debug("Loaded %d completed game(s) for league=%s", len(rows), league)
            return [dict(row) for row in rows]

    def team_stat_snapshot(self, league, team_id, as_of_week, source=None):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            query = """
                SELECT * FROM team_stat_snapshots
                WHERE league = ? AND team_id = ? AND as_of_week <= ?
            """
            params = [league, team_id, as_of_week]
            if source is not None:
                query += " AND source = ?"
                params.append(source)
            query += " ORDER BY as_of_week DESC LIMIT 1"
            row = conn.execute(query, params).fetchone()
            if row is None:
                log.debug("No stat snapshot found league=%s team_id=%s as_of_week=%s", league, team_id, as_of_week)
            return dict(row) if row else None

    def save_player_prop_snapshot(self, prop):
        """Save one bookmaker quote and its available model features/outcome."""
        actual_value = prop.get("actual_value")
        line = prop.get("line")
        side_id = prop["side_id"]
        over_hit = None
        if actual_value is not None and line is not None and actual_value != line:
            if side_id == "over":
                over_hit = int(actual_value > line)
            elif side_id == "under":
                over_hit = int(actual_value < line)

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO player_prop_snapshots (
                    event_id, league, odd_id, player_id, player_name, team_id,
                    stat_id, period_id, side_id, bookmaker_id, line, odds, fair_odds,
                    season_avg, last3_avg, opponent_defense_ypp_allowed,
                    actual_value, over_hit, source, captured_at
                ) VALUES (
                    :event_id, :league, :odd_id, :player_id, :player_name, :team_id,
                    :stat_id, :period_id, :side_id, :bookmaker_id, :line, :odds, :fair_odds,
                    :season_avg, :last3_avg, :opponent_defense_ypp_allowed,
                    :actual_value, :over_hit, :source, COALESCE(:captured_at, CURRENT_TIMESTAMP)
                )
                ON CONFLICT(event_id, odd_id, bookmaker_id, captured_at) DO UPDATE SET
                    line=excluded.line,
                    odds=excluded.odds,
                    fair_odds=excluded.fair_odds,
                    season_avg=COALESCE(excluded.season_avg, player_prop_snapshots.season_avg),
                    last3_avg=COALESCE(excluded.last3_avg, player_prop_snapshots.last3_avg),
                    opponent_defense_ypp_allowed=COALESCE(
                        excluded.opponent_defense_ypp_allowed,
                        player_prop_snapshots.opponent_defense_ypp_allowed
                    ),
                    actual_value=COALESCE(excluded.actual_value, player_prop_snapshots.actual_value),
                    over_hit=COALESCE(excluded.over_hit, player_prop_snapshots.over_hit)
                """,
                {
                    **prop,
                    "over_hit": over_hit,
                    "source": prop.get("source", "sportsgameodds"),
                    "captured_at": prop.get("captured_at"),
                },
            )
            conn.commit()

    def player_prop_training_rows(self, league):
        """Return labeled prop quotes with the features required by the prop model."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM player_prop_snapshots
                WHERE league = ? AND over_hit IS NOT NULL
                    AND season_avg IS NOT NULL AND last3_avg IS NOT NULL
                ORDER BY captured_at
                """,
                (league,),
            ).fetchall()
            return [dict(row) for row in rows]
