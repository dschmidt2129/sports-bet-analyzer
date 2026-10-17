"""Feature engineering shared by offline training and mobile-safe inference.

Returns plain dicts (no numpy/pandas) so this module works unmodified on Android.
"""

SPREAD_FEATURES = (
    "ppg_diff",
    "papg_diff",
    "ypp_diff",
    "yppa_diff",
    "turnover_margin_diff",
    "win_pct_diff",
    "fpi_diff",
    "home_field",
)

TOTAL_FEATURES = (
    "combined_ppg",
    "combined_papg",
    "combined_ypp",
    "over_under_line",
)

PLAYER_PROP_BET_TYPE = "player_prop"
PLAYER_PROP_FEATURES = (
    "season_edge",
    "recent_edge",
    "trend_edge",
    "opponent_defense",
    "market_prob",
    "is_over",
)


def american_to_probability(odds):
    if odds is None or odds == 0:
        return None
    return 100.0 / (odds + 100.0) if odds > 0 else -odds / (-odds + 100.0)


def player_prop_hit_features(quote):
    """Features for P(the quoted side hits); None when player averages or a line are missing."""
    line, season, last3 = quote.get("line"), quote.get("season_avg"), quote.get("last3_avg")
    if not line or season is None or last3 is None:
        return None
    side = 1.0 if quote.get("side_id") == "over" else -1.0
    market_prob = american_to_probability(quote.get("odds"))
    return {
        "season_edge": side * (season - line) / line,
        "recent_edge": side * (last3 - line) / line,
        "trend_edge": side * (last3 - season) / line,
        "opponent_defense": side * (quote.get("opponent_defense_ypp_allowed") or 0.0),
        "market_prob": market_prob if market_prob is not None else 0.5,
        "is_over": 1.0 if side > 0 else 0.0,
    }


def team_differential_features(home, away):
    """Home-minus-away feature vector used for spread/moneyline models."""
    return {
        "ppg_diff": home.points_per_game - away.points_per_game,
        "papg_diff": away.points_allowed_per_game - home.points_allowed_per_game,
        "ypp_diff": home.yards_per_play - away.yards_per_play,
        "yppa_diff": away.yards_allowed_per_play - home.yards_allowed_per_play,
        "turnover_margin_diff": home.turnover_margin - away.turnover_margin,
        "win_pct_diff": home.win_pct - away.win_pct,
        "fpi_diff": (home.fpi or 0.0) - (away.fpi or 0.0),
        "home_field": 1.0,
    }


def total_features(home, away, over_under):
    return {
        "combined_ppg": home.points_per_game + away.points_per_game,
        "combined_papg": home.points_allowed_per_game + away.points_allowed_per_game,
        "combined_ypp": home.yards_per_play + away.yards_per_play,
        "over_under_line": over_under or 0.0,
    }


def prop_features(player_stat, opponent_defense_ypp_allowed):
    return {
        "season_avg": player_stat.season_avg,
        "last3_avg": player_stat.last3_avg,
        "trend": player_stat.last3_avg - player_stat.season_avg,
        "opponent_defense_ypp_allowed": opponent_defense_ypp_allowed,
    }
