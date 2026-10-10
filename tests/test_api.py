from fastapi.testclient import TestClient

from sports_bet_analyzer import api
from sports_bet_analyzer.models import PredictionResult


def test_health_endpoint():
    response = TestClient(api.app).get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_recommendations_endpoint_serializes_predictions(monkeypatch):
    requested_leagues = []

    def load_recommendations(leagues):
        requested_leagues.append(leagues)
        return [
            PredictionResult(
                game_id="401000001",
                bet_type="spread",
                selection="Home Team -3.5",
                probability=0.72,
                reasoning="FPI cold-start estimate.",
                home_team_name="Home Team",
                away_team_name="Away Team",
                odds=-110,
            )
        ]

    monkeypatch.setattr(
        api.recommendation_service,
        "load_recommendations",
        load_recommendations,
    )

    response = TestClient(api.app).get("/api/recommendations?league=nfl")

    assert response.status_code == 200
    body = response.json()
    assert body["league"] == "nfl"
    assert body["recommendations"] == [
        {
            "game_id": "401000001",
            "bet_type": "spread",
            "selection": "Home Team -3.5",
            "probability": 0.72,
            "reasoning": "FPI cold-start estimate.",
            "home_team_name": "Home Team",
            "away_team_name": "Away Team",
            "odds": -110,
        }
    ]
    assert body["refreshed_at"]
    assert requested_leagues == [("nfl",)]


def test_recommendations_endpoint_loads_both_leagues_by_default(monkeypatch):
    requested_leagues = []
    monkeypatch.setattr(
        api.recommendation_service,
        "load_recommendations",
        lambda leagues: requested_leagues.append(leagues) or [],
    )

    response = TestClient(api.app).get("/api/recommendations")

    assert response.status_code == 200
    assert response.json()["league"] == "all"
    assert response.json()["recommendations"] == []
    assert requested_leagues == [("nfl", "college-football")]


def test_recommendations_endpoint_rejects_unknown_league():
    response = TestClient(api.app).get("/api/recommendations?league=mlb")

    assert response.status_code == 422
