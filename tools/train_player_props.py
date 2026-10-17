"""Desktop-only offline trainer for the player-prop hit model (needs numpy; see requirements-dev.txt).

Fits logistic regression on labeled prop snapshots in the local history DB and writes
model_weights/player_prop.json, which PlayerPropService loads through predictor.py.
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sports_bet_analyzer import features as feat
from sports_bet_analyzer.storage import HistoryStore
from train_offline import WEIGHTS_DIR, train_logistic_regression

log = logging.getLogger(__name__)


def build_player_prop_dataset(store, league):
    """Returns (X, y): y=1 if the quoted side (over/under) hit."""
    rows, labels = [], []
    for row in store.player_prop_training_rows(league):
        features = feat.player_prop_hit_features(row)
        if features is None:
            continue
        rows.append([features[name] for name in feat.PLAYER_PROP_FEATURES])
        labels.append(row["over_hit"])  # despite the name, this is "quoted side hit"
    log.info("Built player-prop dataset with %d sample(s) league=%s", len(labels), league)
    return np.array(rows, dtype=float), np.array(labels, dtype=float)


def main():
    parser = argparse.ArgumentParser(description="Train the player-prop hit model from local history.")
    parser.add_argument("--db", default="sports_bet_analyzer.db")
    parser.add_argument("--league", default="nfl", choices=["nfl", "college-football"])
    parser.add_argument("--min-samples", type=int, default=200)
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)

    X, y = build_player_prop_dataset(HistoryStore(args.db), args.league)
    if len(y) < args.min_samples:
        log.warning("Only %d labeled prop(s) available (need %d); skipping training.", len(y), args.min_samples)
        return

    model = train_logistic_regression(X, y, feat.PLAYER_PROP_FEATURES)
    WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = WEIGHTS_DIR / f"{feat.PLAYER_PROP_BET_TYPE}.json"
    out_path.write_text(json.dumps(model, indent=2), encoding="utf-8")
    log.info("Wrote %s trained on %d prop(s).", out_path, len(y))


if __name__ == "__main__":
    main()
