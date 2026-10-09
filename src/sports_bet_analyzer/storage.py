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
    PRIMARY KEY (league, team_id, as_of_week)
);
"""


class HistoryStore:
    def __init__(self, db_path="sports_bet_analyzer.db"):
        self.db_path = db_path
        log.info("Opening history store at %s", db_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.executescript(SCHEMA)
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

    def save_team_stat_snapshot(self, league, team_stats, as_of_week):
        log.debug(
            "Saving team stat snapshot league=%s team_id=%s week=%s", league, team_stats.team_id, as_of_week
        )
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                """
                INSERT INTO team_stat_snapshots (
                    league, team_id, as_of_week, points_per_game, points_allowed_per_game,
                    yards_per_play, yards_allowed_per_play, turnover_margin, win_pct, fpi
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(league, team_id, as_of_week) DO UPDATE SET
                    points_per_game=excluded.points_per_game,
                    points_allowed_per_game=excluded.points_allowed_per_game,
                    yards_per_play=excluded.yards_per_play,
                    yards_allowed_per_play=excluded.yards_allowed_per_play,
                    turnover_margin=excluded.turnover_margin,
                    win_pct=excluded.win_pct,
                    fpi=excluded.fpi
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

    def team_stat_snapshot(self, league, team_id, as_of_week):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM team_stat_snapshots
                WHERE league = ? AND team_id = ? AND as_of_week <= ?
                ORDER BY as_of_week DESC LIMIT 1
                """,
                (league, team_id, as_of_week),
            ).fetchone()
            if row is None:
                log.debug("No stat snapshot found league=%s team_id=%s as_of_week=%s", league, team_id, as_of_week)
            return dict(row) if row else None
