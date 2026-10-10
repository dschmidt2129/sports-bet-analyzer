import json
from unittest.mock import Mock

from sports_bet_analyzer.models import Game, OddsLine, TeamStats
from sports_bet_analyzer.predictor import Predictor
from sports_bet_analyzer.recommender import rank_games, recommend_for_game


def _game(home_fpi=10.0, away_fpi=0.0, home_spread=-3.5, over_under=45.0):
    home = TeamStats(team_id="1", name="Home", fpi=home_fpi)
    away = TeamStats(team_id="2", name="Away", fpi=away_fpi)
    odds = OddsLine(
        provider="ESPN BET",
        home_spread=home_spread,
        over_under=over_under,
        home_moneyline=-180,
        away_moneyline=150,
        home_spread_odds=-110,
        away_spread_odds=-105,
        over_odds=-115,
        under_odds=-105,
    )
    return Game(game_id="g1", league="nfl", date="2026-09-21", home_team=home, away_team=away, odds=odds)


def test_recommend_for_game_cold_start_uses_fpi_fallback(tmp_path):
    predictor = Predictor(weights_dir=tmp_path)
    game = _game(home_fpi=20.0, away_fpi=0.0)

    results = recommend_for_game(game, predictor, threshold=0.5)

    bet_types = {r.bet_type for r in results}
    assert "spread" in bet_types
    assert "moneyline" in bet_types
    for r in results:
        assert 0.5 <= r.probability <= 1.0
        assert r.home_team_name == "Home"
        assert r.away_team_name == "Away"


def test_recommend_for_game_uses_trained_model_when_available(tmp_path):
    model = {"bias": 0.0, "weights": {"fpi_diff": 1.0}}
    (tmp_path / "spread.json").write_text(json.dumps(model), encoding="utf-8")
    predictor = Predictor(weights_dir=tmp_path)

    game = _game(home_fpi=20.0, away_fpi=0.0)
    results = recommend_for_game(game, predictor, threshold=0.0)

    spread_result = next(r for r in results if r.bet_type == "spread")
    assert "trained model" in spread_result.reasoning


def test_rank_games_sorts_by_probability_desc(tmp_path):
    predictor = Predictor(weights_dir=tmp_path)
    strong = _game(home_fpi=30.0, away_fpi=0.0)
    strong.game_id = "strong"
    weak = _game(home_fpi=5.0, away_fpi=4.0)
    weak.game_id = "weak"

    ranked = rank_games([weak, strong], predictor, threshold=0.0)

    probabilities = [r.probability for r in ranked]
    assert probabilities == sorted(probabilities, reverse=True)


def test_recommendations_include_odds_for_selected_side():
    predictor = Mock()
    predictor.predict_probability.side_effect = [0.8, 0.2, 0.2]
    game = _game()

    results = recommend_for_game(game, predictor, threshold=0.0)

    assert next(r for r in results if r.bet_type == "spread").odds == -110
    assert next(r for r in results if r.bet_type == "moneyline").odds == 150
    assert next(r for r in results if r.bet_type == "total").odds == -105
