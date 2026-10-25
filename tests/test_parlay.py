import pytest

from sports_bet_analyzer.models import PredictionResult
from sports_bet_analyzer.parlay import (
    american_to_decimal,
    build_parlays,
    decimal_to_american,
    joint_probability,
    leg_from_prop,
    leg_from_recommendation,
    pair_correlation,
)


def rec(game_id, bet_type, selection, probability, odds, home="Kansas City Chiefs", away="Buffalo Bills"):
    return PredictionResult(
        game_id=game_id,
        bet_type=bet_type,
        selection=selection,
        probability=probability,
        reasoning="",
        home_team_name=home,
        away_team_name=away,
        odds=odds,
    )


def prop(player_id, stat, side, probability, odds=-110, team="KANSAS_CITY_CHIEFS_NFL", opp="BUFFALO_BILLS_NFL"):
    return {
        "event_id": "e1",
        "odd_id": f"{player_id}-{stat}-{side}",
        "player_id": player_id,
        "player_name": player_id.title(),
        "team_id": team,
        "opponent_team_id": opp,
        "stat_id": stat,
        "side_id": side,
        "line": 50.5,
        "odds": odds,
        "probability": probability,
    }


def test_odds_conversions_round_trip():
    assert american_to_decimal(100) == 2.0
    assert american_to_decimal(-200) == pytest.approx(1.5)
    assert decimal_to_american(2.5) == 150
    assert decimal_to_american(1.5) == -200


def test_leg_from_recommendation_requires_odds_and_identifies_team():
    assert leg_from_recommendation(rec("g1", "total", "Over 47.5", 0.7, None)) is None
    leg = leg_from_recommendation(rec("g1", "spread", "Kansas City Chiefs -3.5", 0.7, -110))
    assert leg.picked_team == "kansascitychiefs"
    assert leg_from_recommendation(rec("g1", "total", "Under 47.5", 0.7, -110)).direction == -1


def test_leg_from_prop_filters_low_probability_and_missing_odds():
    assert leg_from_prop(prop("mahomes", "passing_yards", "over", 0.55)) is None
    assert leg_from_prop({**prop("mahomes", "passing_yards", "over", 0.7), "odds": None}) is None
    assert leg_from_prop(prop("mahomes", "passing_yards", "over", 0.7)).direction == 1


def test_pair_correlation_excludes_contradictions_and_signs_by_direction():
    spread = leg_from_recommendation(rec("g1", "spread", "Kansas City Chiefs -3.5", 0.7, -110))
    other_ml = leg_from_recommendation(rec("g1", "moneyline", "Buffalo Bills to win", 0.7, 150))
    same_ml = leg_from_recommendation(rec("g1", "moneyline", "Kansas City Chiefs to win", 0.7, -150))
    assert pair_correlation(spread, other_ml) is None
    assert pair_correlation(spread, same_ml) > 0

    over = leg_from_recommendation(rec("g1", "total", "Over 47.5", 0.7, -110))
    over_prop = leg_from_prop(prop("kelce", "receiving_yards", "over", 0.7))
    under_prop = leg_from_prop(prop("kelce", "receiving_yards", "under", 0.7))
    assert pair_correlation(over, over_prop) > 0
    assert pair_correlation(over, under_prop) < 0

    same_stat = leg_from_prop(prop("kelce", "receiving_yards", "over", 0.7))
    assert pair_correlation(over_prop, same_stat) is None


def test_joint_probability_reflects_correlation():
    independent = joint_probability([0.7, 0.7], [[1, 0], [0, 1]])
    positive = joint_probability([0.7, 0.7], [[1, 0.7], [0.7, 1]])
    negative = joint_probability([0.7, 0.7], [[1, -0.7], [-0.7, 1]])
    assert independent == pytest.approx(0.49, abs=0.02)
    assert negative < independent < positive


def test_joint_probability_handles_non_positive_definite_matrix():
    matrix = [[1, 0.9, -0.9], [0.9, 1, 0.9], [-0.9, 0.9, 1]]
    assert 0 <= joint_probability([0.7, 0.7, 0.7], matrix) <= 1


def test_build_parlays_multiplies_independent_games():
    legs = [
        leg_from_recommendation(rec("g1", "moneyline", "Kansas City Chiefs to win", 0.8, -200)),
        leg_from_recommendation(
            rec("g2", "total", "Over 44.5", 0.7, 100, home="Dallas Cowboys", away="New York Giants")
        ),
    ]
    parlay = build_parlays(legs, leg_count=2)[0]
    assert parlay.probability == pytest.approx(0.56)
    assert parlay.decimal_odds == pytest.approx(3.0)
    assert parlay.american_odds == 200
    assert parlay.expected_value == pytest.approx(0.68)
    assert not parlay.correlated


def test_build_parlays_excludes_legs_from_the_same_game():
    legs = [
        leg_from_recommendation(rec("g1", "total", "Over 47.5", 0.7, -110)),
        leg_from_prop(prop("mahomes", "passing_yards", "over", 0.7)),
    ]
    assert build_parlays(legs, leg_count=2) == []


def test_build_parlays_skips_contradictory_legs_and_respects_size_and_limit():
    legs = [
        leg_from_recommendation(rec("g1", "spread", "Kansas City Chiefs -3.5", 0.7, -110)),
        leg_from_recommendation(rec("g1", "moneyline", "Buffalo Bills to win", 0.7, 150)),
    ]
    assert build_parlays(legs, leg_count=2) == []

    many = [
        leg_from_recommendation(
            rec(f"g{i}", "total", "Over 40.5", 0.9 - i * 0.01, -110, home=f"Home Team {i}", away=f"Away Team {i}")
        )
        for i in range(6)
    ]
    parlays = build_parlays(many, leg_count=3, limit=4)
    assert len(parlays) == 4
    assert all(len(p.legs) == 3 for p in parlays)
    assert parlays == sorted(parlays, key=lambda p: p.probability, reverse=True)


def test_build_parlays_rejects_invalid_leg_count():
    with pytest.raises(ValueError):
        build_parlays([], leg_count=5)
