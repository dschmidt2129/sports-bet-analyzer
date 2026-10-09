import json

from sports_bet_analyzer.predictor import Predictor, sigmoid


def test_sigmoid_bounds():
    assert 0.0 < sigmoid(0.0) < 1.0
    assert sigmoid(1000) == 1.0
    assert sigmoid(-1000) == 0.0


def test_predict_probability_with_no_weights_returns_none(tmp_path):
    predictor = Predictor(weights_dir=tmp_path)
    assert predictor.predict_probability("spread", {"ppg_diff": 5}) is None
    assert predictor.has_weights("spread") is False


def test_predict_probability_with_weights(tmp_path):
    model = {"bias": 0.0, "weights": {"ppg_diff": 0.1, "home_field": 0.2}}
    (tmp_path / "spread.json").write_text(json.dumps(model), encoding="utf-8")

    predictor = Predictor(weights_dir=tmp_path)
    prob = predictor.predict_probability("spread", {"ppg_diff": 10, "home_field": 1.0})

    assert predictor.has_weights("spread") is True
    assert 0.5 < prob < 1.0
