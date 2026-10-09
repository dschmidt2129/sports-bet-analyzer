"""Desktop-only offline trainer (not shipped to the Android app).

Builds a training set from the local SQLite history (see storage.py), fits a
simple logistic regression per bet type with plain gradient descent (numpy),
and exports the learned weights as JSON that predictor.py loads at inference
time. Requires requirements-dev.txt (numpy) - do not import numpy anywhere
under src/sports_bet_analyzer so the mobile app never needs it.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sports_bet_analyzer import features as feat  # noqa: E402
from sports_bet_analyzer.models import TeamStats  # noqa: E402
from sports_bet_analyzer.storage import HistoryStore  # noqa: E402

log = logging.getLogger(__name__)

WEIGHTS_DIR = Path(__file__).resolve().parents[1] / "src" / "sports_bet_analyzer" / "model_weights"


def build_spread_dataset(store, league):
    """Returns (X, y): y=1 if the home team covered the closing spread."""
    rows, labels = [], []
    completed = store.completed_games(league)
    log.info("Building spread dataset from %d completed game(s) for league=%s", len(completed), league)
    for game in completed:
        if game["home_spread"] is None or game["home_score"] is None:
            log.debug("Skipping game_id=%s: missing spread or score", game["game_id"])
            continue
        home_snap = store.team_stat_snapshot(league, game["home_team_id"], game["week"] or 0)
        away_snap = store.team_stat_snapshot(league, game["away_team_id"], game["week"] or 0)
        if not home_snap or not away_snap:
            log.debug("Skipping game_id=%s: missing stat snapshot", game["game_id"])
            continue

        home = TeamStats(team_id=game["home_team_id"], name="", **_strip(home_snap))
        away = TeamStats(team_id=game["away_team_id"], name="", **_strip(away_snap))
        features = feat.team_differential_features(home, away)

        margin = game["home_score"] - game["away_score"]
        covered = 1 if (margin + game["home_spread"]) > 0 else 0

        rows.append([features[name] for name in feat.SPREAD_FEATURES])
        labels.append(covered)

    log.info("Built dataset with %d usable sample(s)", len(labels))
    return np.array(rows, dtype=float), np.array(labels, dtype=float)


def _strip(snapshot_row):
    return {
        "points_per_game": snapshot_row["points_per_game"] or 0.0,
        "points_allowed_per_game": snapshot_row["points_allowed_per_game"] or 0.0,
        "yards_per_play": snapshot_row["yards_per_play"] or 0.0,
        "yards_allowed_per_play": snapshot_row["yards_allowed_per_play"] or 0.0,
        "turnover_margin": snapshot_row["turnover_margin"] or 0.0,
        "win_pct": snapshot_row["win_pct"] or 0.0,
        "fpi": snapshot_row["fpi"],
    }


def train_logistic_regression(X, y, feature_names, lr=0.05, epochs=2000, l2=0.001):
    n, d = X.shape
    log.info("Training logistic regression on %d sample(s), %d feature(s), epochs=%d", n, d, epochs)
    weights = np.zeros(d)
    bias = 0.0

    for epoch in range(epochs):
        z = X @ weights + bias
        preds = 1.0 / (1.0 + np.exp(-z))
        error = preds - y

        grad_w = (X.T @ error) / n + l2 * weights
        grad_b = error.mean()

        weights -= lr * grad_w
        bias -= lr * grad_b

        if epoch % 500 == 0:
            loss = -np.mean(y * np.log(preds + 1e-9) + (1 - y) * np.log(1 - preds + 1e-9))
            log.debug("epoch=%d loss=%.4f", epoch, loss)

    log.info("Training complete: bias=%.4f", bias)
    return {"bias": float(bias), "weights": {name: float(w) for name, w in zip(feature_names, weights)}}


def main():
    parser = argparse.ArgumentParser(description="Train offline betting models from local ESPN history.")
    parser.add_argument("--db", default="sports_bet_analyzer.db")
    parser.add_argument("--league", default="nfl", choices=["nfl", "college-football"])
    parser.add_argument("--min-samples", type=int, default=50)
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    store = HistoryStore(args.db)
    X, y = build_spread_dataset(store, args.league)

    if len(y) < args.min_samples:
        log.warning("Only %d labeled game(s) available (need %d); skipping training.", len(y), args.min_samples)
        log.warning("Run the app for more weeks to accumulate history, or seed historical data manually.")
        return

    model = train_logistic_regression(X, y, feat.SPREAD_FEATURES)

    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WEIGHTS_DIR / "spread.json"
    out_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    log.info("Wrote %s trained on %d game(s).", out_path, len(y))


if __name__ == "__main__":
    main()
