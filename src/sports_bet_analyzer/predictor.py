"""Mobile-safe inference: pure Python, no numpy/sklearn required at runtime.

Loads regression weights trained offline (see tools/train_offline.py) and scores
feature dicts produced by features.py.
"""
import json
import logging
import math
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_WEIGHTS_DIR = Path(__file__).parent / "model_weights"


def sigmoid(x):
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class Predictor:
    """Loads one JSON weight file per bet type: {"bias": float, "weights": {feature: weight}}."""

    def __init__(self, weights_dir=DEFAULT_WEIGHTS_DIR):
        self.weights_dir = Path(weights_dir)
        self._cache = {}

    def _weights_for(self, bet_type):
        if bet_type not in self._cache:
            path = self.weights_dir / f"{bet_type}.json"
            if path.is_file():
                self._cache[bet_type] = json.loads(path.read_text(encoding="utf-8"))
                log.info("Loaded trained weights for bet_type=%s from %s", bet_type, path)
            else:
                self._cache[bet_type] = None
                log.info("No trained weights found for bet_type=%s at %s", bet_type, path)
        return self._cache[bet_type]

    def has_weights(self, bet_type):
        return self._weights_for(bet_type) is not None

    def predict_probability(self, bet_type, features):
        """Returns probability in [0, 1], or None if no trained weights are available yet."""
        model = self._weights_for(bet_type)
        if model is None:
            return None

        score = model.get("bias", 0.0)
        for name, weight in model.get("weights", {}).items():
            score += weight * features.get(name, 0.0)
        probability = sigmoid(score)
        log.debug("Predicted bet_type=%s probability=%.4f features=%s", bet_type, probability, features)
        return probability
