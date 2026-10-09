"""Plain data structures shared across the ESPN client, feature engineering, and predictor."""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TeamStats:
    team_id: str
    name: str
    points_per_game: float = 0.0
    points_allowed_per_game: float = 0.0
    yards_per_play: float = 0.0
    yards_allowed_per_play: float = 0.0
    turnover_margin: float = 0.0
    win_pct: float = 0.0
    fpi: Optional[float] = None


@dataclass
class OddsLine:
    provider: str
    home_spread: Optional[float] = None
    over_under: Optional[float] = None
    home_moneyline: Optional[int] = None
    away_moneyline: Optional[int] = None


@dataclass
class PlayerPropStat:
    player_id: str
    name: str
    team_id: str
    stat_name: str
    season_avg: float = 0.0
    last3_avg: float = 0.0


@dataclass
class Game:
    game_id: str
    league: str
    date: str
    home_team: TeamStats
    away_team: TeamStats
    week: Optional[int] = None
    odds: Optional[OddsLine] = None
    completed: bool = False
    home_score: Optional[int] = None
    away_score: Optional[int] = None
    props: list = field(default_factory=list)


@dataclass
class PredictionResult:
    game_id: str
    bet_type: str  # "spread" | "moneyline" | "total" | "prop"
    selection: str
    probability: float
    reasoning: str
    home_team_name: str = ""
    away_team_name: str = ""
