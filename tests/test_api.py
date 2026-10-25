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


def test_player_props_endpoint_returns_provider_quotes(monkeypatch):
    requested_leagues = []
    quote = {
        "event_id": "event-1",
        "league": "nfl",
        "odd_id": "passing_yards-player-1-game-ou-over",
        "player_id": "player-1",
        "player_name": "Player One",
        "team_id": "team-1",
        "opponent_team_id": "team-2",
        "stat_id": "passing_yards",
        "period_id": "game",
        "side_id": "over",
        "bookmaker_id": "draftkings",
        "line": 245.5,
        "odds": -110,
        "fair_odds": -105,
        "probability": 0.51,
        "captured_at": "2026-10-16T12:00:00+00:00",
    }
    monkeypatch.setattr(
        api.player_prop_service,
        "ranked_player_props",
        lambda league: requested_leagues.append(league) or [quote],
    )

    response = TestClient(api.app).get("/api/player-props?league=nfl")

    assert response.status_code == 200
    body = response.json()
    assert body["league"] == "nfl"
    assert body["props"] == [quote]
    assert body["refreshed_at"]
    assert requested_leagues == ["nfl"]


def test_player_props_endpoint_rejects_unknown_league():
    response = TestClient(api.app).get("/api/player-props?league=mlb")

    assert response.status_code == 422


def test_parlays_endpoint_combines_game_picks_and_props(monkeypatch):
    recommendations = [
        PredictionResult(
            game_id="g1",
            bet_type="total",
            selection="Over 47.5",
            probability=0.7,
            reasoning="",
            home_team_name="Kansas City Chiefs",
            away_team_name="Buffalo Bills",
            odds=-110,
        )
    ]
    quote = {
        "event_id": "event-1",
        "odd_id": "passing_yards-mahomes-over",
        "player_id": "mahomes",
        "player_name": "Mahomes",
        "team_id": "DALLAS_COWBOYS_NFL",
        "opponent_team_id": "NEW_YORK_GIANTS_NFL",
        "stat_id": "passing_yards",
        "side_id": "over",
        "bookmaker_id": "draftkings",
        "line": 275.5,
        "odds": -115,
        "probability": 0.68,
    }
    monkeypatch.setattr(api.recommendation_service, "load_recommendations", lambda leagues: recommendations)
    monkeypatch.setattr(
        api.player_prop_service,
        "ranked_player_props",
        lambda league, bookmaker_id=None: [quote] if bookmaker_id == "draftkings" else [],
    )

    response = TestClient(api.app).get("/api/parlays?league=nfl")

    assert response.status_code == 200
    body = response.json()
    assert set(body["parlays_by_legs"]) == {"2", "3", "4"}
    assert body["parlays_by_legs"]["3"] == []
    parlay = body["parlays_by_legs"]["2"][0]
    assert parlay["leg_count"] == 2
    assert {leg["source"] for leg in parlay["legs"]} == {"game", "prop"}
    assert parlay["has_correlated_legs"] is False
    assert 0 < parlay["probability"] < 1
    assert parlay["notes"]


def test_parlays_endpoint_returns_empty_lists_without_enough_legs(monkeypatch):
    monkeypatch.setattr(api.recommendation_service, "load_recommendations", lambda leagues: [])
    monkeypatch.setattr(api.player_prop_service, "ranked_player_props", lambda league, bookmaker_id=None: [])

    response = TestClient(api.app).get("/api/parlays")

    assert response.status_code == 200
    assert response.json()["parlays_by_legs"] == {"2": [], "3": [], "4": []}

