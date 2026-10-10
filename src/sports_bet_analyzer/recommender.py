"""Combines predictor probabilities with a cold-start fallback and ranks bets.

Cold-start fallback (no trained weights yet, e.g. start of season) derives a
probability directly from the FPI differential already fetched from ESPN, so
the app has something useful to show before enough in-season history exists.
"""
import logging

from sports_bet_analyzer import features as feat
from sports_bet_analyzer.models import PredictionResult
from sports_bet_analyzer.predictor import sigmoid

log = logging.getLogger(__name__)

HIGH_CONFIDENCE_THRESHOLD = 0.65
FPI_SCALE = 10.0  # empirical: ~10 FPI points ~= one score's worth of edge


def recommend_for_game(game, predictor, threshold=HIGH_CONFIDENCE_THRESHOLD):
    results = []

    spread_features = feat.team_differential_features(game.home_team, game.away_team)
    spread_prob, spread_is_model = _probability_with_fallback(
        predictor, "spread", spread_features, spread_features["fpi_diff"] / FPI_SCALE
    )
    results.append(
        _build_result(
            game,
            "spread",
            _spread_selection(game, spread_prob),
            spread_prob,
            spread_is_model,
            _spread_odds(game, spread_prob),
        )
    )

    ml_prob, ml_is_model = _probability_with_fallback(
        predictor, "moneyline", spread_features, spread_features["fpi_diff"] / (FPI_SCALE * 0.75)
    )
    results.append(
        _build_result(
            game,
            "moneyline",
            _moneyline_selection(game, ml_prob),
            ml_prob,
            ml_is_model,
            _moneyline_odds(game, ml_prob),
        )
    )

    if game.odds and game.odds.over_under:
        total_feats = feat.total_features(game.home_team, game.away_team, game.odds.over_under)
        total_prob = predictor.predict_probability("total", total_feats)
        if total_prob is not None:
            results.append(
                _build_result(
                    game,
                    "total",
                    _total_selection(game, total_prob),
                    total_prob,
                    True,
                    _total_odds(game, total_prob),
                )
            )

    high_confidence = [r for r in results if r.probability >= threshold]
    log.debug(
        "game_id=%s produced %d result(s), %d above threshold=%.2f",
        game.game_id, len(results), len(high_confidence), threshold,
    )
    return high_confidence


def rank_games(games, predictor, threshold=HIGH_CONFIDENCE_THRESHOLD):
    """Flat, probability-descending list of high-confidence bets across all games."""
    log.info("Ranking %d game(s) with threshold=%.2f", len(games), threshold)
    all_results = []
    for game in games:
        all_results.extend(recommend_for_game(game, predictor, threshold))
    ranked = sorted(all_results, key=lambda r: r.probability, reverse=True)
    log.info("Found %d high-probability bet(s) across %d game(s)", len(ranked), len(games))
    return ranked


def _probability_with_fallback(predictor, bet_type, features, fallback_logit):
    prob = predictor.predict_probability(bet_type, features)
    if prob is not None:
        return prob, True
    return sigmoid(fallback_logit), False


def _spread_selection(game, prob):
    favorite = game.home_team.name if prob >= 0.5 else game.away_team.name
    if game.odds and game.odds.home_spread is not None:
        line = game.odds.home_spread if prob >= 0.5 else -game.odds.home_spread
        return f"{favorite} {line:+.1f}"
    return f"{favorite} to cover (line unavailable)"


def _moneyline_selection(game, prob):
    winner = game.home_team.name if prob >= 0.5 else game.away_team.name
    return f"{winner} to win"


def _total_selection(game, prob):
    direction = "Over" if prob >= 0.5 else "Under"
    return f"{direction} {game.odds.over_under:.1f}"


def _spread_odds(game, prob):
    if game.odds is None:
        return None
    return game.odds.home_spread_odds if prob >= 0.5 else game.odds.away_spread_odds


def _moneyline_odds(game, prob):
    if game.odds is None:
        return None
    return game.odds.home_moneyline if prob >= 0.5 else game.odds.away_moneyline


def _total_odds(game, prob):
    if game.odds is None:
        return None
    return game.odds.over_odds if prob >= 0.5 else game.odds.under_odds


def _build_result(game, bet_type, selection, probability, is_model, odds=None):
    source = "trained model" if is_model else "FPI cold-start estimate"
    reasoning = (
        f"{game.away_team.name} @ {game.home_team.name} - probability from {source}."
    )
    return PredictionResult(
        game_id=game.game_id,
        bet_type=bet_type,
        selection=selection,
        probability=max(probability, 1 - probability),
        reasoning=reasoning,
        odds=odds,
        home_team_name=game.home_team.name,
        away_team_name=game.away_team.name,
    )
