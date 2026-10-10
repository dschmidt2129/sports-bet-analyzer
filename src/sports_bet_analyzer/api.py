"""HTTP API for the React and Capacitor client."""
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sports_bet_analyzer.models import PredictionResult
from sports_bet_analyzer.recommendation_service import RecommendationService

League = Literal["all", "nfl", "college-football"]
LEAGUES = ("nfl", "college-football")


class RecommendationResponse(BaseModel):
    game_id: str
    bet_type: str
    selection: str
    probability: float
    reasoning: str
    home_team_name: str
    away_team_name: str
    odds: int | None


class RecommendationsResponse(BaseModel):
    league: League
    refreshed_at: datetime
    recommendations: list[RecommendationResponse]


app = FastAPI(title="Sports Bet Analyzer API", version="1.0.0")
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,capacitor://localhost,https://localhost",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)
recommendation_service = RecommendationService()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    league: League = Query(default="all"),
):
    selected_leagues = LEAGUES if league == "all" else (league,)
    recommendations: list[PredictionResult] = recommendation_service.load_recommendations(
        selected_leagues
    )
    return RecommendationsResponse(
        league=league,
        refreshed_at=datetime.now(timezone.utc),
        recommendations=[
            RecommendationResponse(
                game_id=result.game_id,
                bet_type=result.bet_type,
                selection=result.selection,
                probability=result.probability,
                reasoning=result.reasoning,
                home_team_name=result.home_team_name,
                away_team_name=result.away_team_name,
                odds=result.odds,
            )
            for result in recommendations
        ],
    )
