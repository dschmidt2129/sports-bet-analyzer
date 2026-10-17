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
MIN_MARKET_EDGE = 0.04
MARKET_WEIGHT = 0.60
FPI_TO_POINT_MARGIN = 0.7
HOME_FIELD_POINTS = 1.5
MARGIN_LOGISTIC_SCALE = {"nfl": 7.0, "college-football": 9.0}
TOTAL_LOGISTIC_SCALE = {"nfl": 8.0, "college-football": 10.0}


def recommend_for_game(game, predictor, threshold=HIGH_CONFIDENCE_THRESHOLD):
    results = []

    spread_features = feat.team_differential_features(game.home_team, game.away_team)
    market_spread_prob = _paired_market_probability(
        game.odds.home_spread_odds if game.odds else None,
        game.odds.away_spread_odds if game.odds else None,
    )
    spread_model_prob = predictor.predict_probability("spread", spread_features)
    spread_is_model = spread_model_prob is not None
    if not spread_is_model:
        spread_model_prob = _cold_start_spread_probability(game)
    spread_prob = _market_blend(spread_model_prob, market_spread_prob)
    if (
        game.odds
        and game.odds.home_spread is not None
        and _meets_recommendation_bar(spread_prob, market_spread_prob, threshold)
    ):
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

    market_moneyline_prob = _paired_market_probability(
        game.odds.home_moneyline if game.odds else None,
        game.odds.away_moneyline if game.odds else None,
    )
    moneyline_model_prob = predictor.predict_probability("moneyline", spread_features)
    moneyline_is_model = moneyline_model_prob is not None
    if not moneyline_is_model:
        margin = _projected_home_margin(game)
        moneyline_model_prob = (
            sigmoid(margin / _margin_scale(game)) if margin is not None else None
        )
    moneyline_prob = _market_blend(moneyline_model_prob, market_moneyline_prob)
    if _meets_recommendation_bar(moneyline_prob, market_moneyline_prob, threshold):
        results.append(
            _build_result(
                game,
                "moneyline",
                _moneyline_selection(game, moneyline_prob),
                moneyline_prob,
                moneyline_is_model,
                _moneyline_odds(game, moneyline_prob),
            )
        )

    if game.odds and game.odds.over_under is not None:
        total_feats = feat.total_features(game.home_team, game.away_team, game.odds.over_under)
        market_total_prob = _paired_market_probability(game.odds.over_odds, game.odds.under_odds)
        total_model_prob = predictor.predict_probability("total", total_feats)
        total_is_model = total_model_prob is not None
        if not total_is_model:
            total_model_prob = _cold_start_total_probability(game)
        total_prob = _market_blend(total_model_prob, market_total_prob)
        if _meets_recommendation_bar(total_prob, market_total_prob, threshold):
            results.append(
                _build_result(
                    game,
                    "total",
                    _total_selection(game, total_prob),
                    total_prob,
                    total_is_model,
                    _total_odds(game, total_prob),
                )
            )

    log.debug(
        "game_id=%s produced %d recommendation(s) meeting threshold=%.2f and market edge",
        game.game_id, len(results), threshold,
    )
    return results


def rank_games(games, predictor, threshold=HIGH_CONFIDENCE_THRESHOLD):
    """Flat, probability-descending list of high-confidence bets across all games."""
    log.info("Ranking %d game(s) with threshold=%.2f", len(games), threshold)
    all_results = []
    for game in games:
        all_results.extend(recommend_for_game(game, predictor, threshold))
    ranked = sorted(all_results, key=lambda r: r.probability, reverse=True)
    log.info("Found %d high-probability bet(s) across %d game(s)", len(ranked), len(games))
    return ranked


def _cold_start_spread_probability(game):
    if game.odds is None or game.odds.home_spread is None:
        return None
    margin = _projected_home_margin(game)
    if margin is None:
        return None
    return sigmoid((margin + game.odds.home_spread) / _margin_scale(game))


def _cold_start_total_probability(game):
    if game.odds is None or game.odds.over_under is None or not _has_scoring_stats(game):
        return None
    home_expected = (game.home_team.points_per_game + game.away_team.points_allowed_per_game) / 2
    away_expected = (game.away_team.points_per_game + game.home_team.points_allowed_per_game) / 2
    expected_total = home_expected + away_expected
    scale = TOTAL_LOGISTIC_SCALE.get(game.league, TOTAL_LOGISTIC_SCALE["nfl"])
    return sigmoid((expected_total - game.odds.over_under) / scale)


def _projected_home_margin(game):
    home = game.home_team
    away = game.away_team
    fpi_margin = None
    if home.fpi is not None and away.fpi is not None:
        fpi_margin = (home.fpi - away.fpi) * FPI_TO_POINT_MARGIN

    stats_margin = None
    if _has_scoring_stats(game):
        home_expected = (home.points_per_game + away.points_allowed_per_game) / 2
        away_expected = (away.points_per_game + home.points_allowed_per_game) / 2
        stats_margin = home_expected - away_expected

    if fpi_margin is None and stats_margin is None:
        return None
    if fpi_margin is None:
        margin = stats_margin
    elif stats_margin is None:
        margin = fpi_margin
    else:
        margin = 0.6 * fpi_margin + 0.4 * stats_margin
    return margin + HOME_FIELD_POINTS


def _has_scoring_stats(game):
    teams = (game.home_team, game.away_team)
    return all(
        value is not None and value > 0
        for team in teams
        for value in (team.points_per_game, team.points_allowed_per_game)
    )


def _margin_scale(game):
    return MARGIN_LOGISTIC_SCALE.get(game.league, MARGIN_LOGISTIC_SCALE["nfl"])


def _market_blend(model_probability, market_probability):
    if model_probability is None or market_probability is None:
        return None
    return MARKET_WEIGHT * market_probability + (1 - MARKET_WEIGHT) * model_probability


def _meets_recommendation_bar(probability, market_probability, threshold):
    if probability is None or market_probability is None:
        return False
    selected_probability = max(probability, 1 - probability)
    selected_market_probability = market_probability if probability >= 0.5 else 1 - market_probability
    return (
        selected_probability >= threshold
        and selected_probability - selected_market_probability >= MIN_MARKET_EDGE
    )


def _paired_market_probability(selected_odds, opposing_odds):
    selected_probability = _american_implied_probability(selected_odds)
    opposing_probability = _american_implied_probability(opposing_odds)
    if selected_probability is None or opposing_probability is None:
        return None
    return selected_probability / (selected_probability + opposing_probability)


def _american_implied_probability(odds):
    if odds is None or odds == 0:
        return None
    if odds < 0:
        return -odds / (-odds + 100)
    return 100 / (odds + 100)


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
    source = "trained model blended with market" if is_model else "season-stat/FPI estimate blended with market"
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
