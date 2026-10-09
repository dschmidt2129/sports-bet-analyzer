from sports_bet_analyzer.features import team_differential_features, total_features
from sports_bet_analyzer.models import TeamStats


def test_team_differential_features():
    home = TeamStats(
        team_id="1", name="Home", points_per_game=28, points_allowed_per_game=17,
        yards_per_play=6.2, yards_allowed_per_play=5.0, turnover_margin=1.2, win_pct=0.75, fpi=8.0,
    )
    away = TeamStats(
        team_id="2", name="Away", points_per_game=20, points_allowed_per_game=24,
        yards_per_play=5.1, yards_allowed_per_play=5.8, turnover_margin=-0.5, win_pct=0.4, fpi=2.0,
    )

    features = team_differential_features(home, away)

    assert features["ppg_diff"] == 8
    assert features["papg_diff"] == 7
    assert round(features["ypp_diff"], 2) == 1.1
    assert round(features["yppa_diff"], 2) == 0.8
    assert features["turnover_margin_diff"] == 1.7
    assert features["win_pct_diff"] == 0.35
    assert features["fpi_diff"] == 6.0
    assert features["home_field"] == 1.0


def test_total_features():
    home = TeamStats(team_id="1", name="Home", points_per_game=28, points_allowed_per_game=17, yards_per_play=6.2)
    away = TeamStats(team_id="2", name="Away", points_per_game=20, points_allowed_per_game=24, yards_per_play=5.1)

    features = total_features(home, away, over_under=47.5)

    assert features["combined_ppg"] == 48
    assert features["combined_papg"] == 41
    assert round(features["combined_ypp"], 2) == 11.3
    assert features["over_under_line"] == 47.5
