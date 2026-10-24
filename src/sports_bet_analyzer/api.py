"""HTTP API for the React and Capacitor client."""
import logging
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sports_bet_analyzer.models import PredictionResult
from sports_bet_analyzer.parlay import (
    MAX_LEGS,
    MIN_LEGS,
    build_parlays,
    leg_from_prop,
    leg_from_recommendation,
)
from sports_bet_analyzer.player_prop_service import PlayerPropService
from sports_bet_analyzer.recommendation_service import RecommendationService

League = Literal["all", "nfl", "college-football"]
LEAGUES = ("nfl", "college-football")

# Uvicorn only configures its own loggers, so app INFO logs are dropped without this.
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)s:     %(name)s - %(message)s",
)


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


class PlayerPropQuoteResponse(BaseModel):
    event_id: str
    league: str
    odd_id: str
    player_id: str
    player_name: str
    team_id: str | None
    opponent_team_id: str | None
    stat_id: str
    period_id: str
    side_id: str
    bookmaker_id: str
    line: float
    odds: int
    fair_odds: int | None
    probability: float
    captured_at: str


class PlayerPropsResponse(BaseModel):
    league: str
    refreshed_at: datetime
    props: list[PlayerPropQuoteResponse]


class ParlayLegResponse(BaseModel):
    leg_id: str
    source: Literal["game", "prop"]
    market: str
    description: str
    matchup: str
    probability: float
    odds: int


class ParlayResponse(BaseModel):
    legs: list[ParlayLegResponse]
    leg_count: int
    probability: float
    decimal_odds: float
    american_odds: int
    expected_value: float
    has_correlated_legs: bool
    notes: list[str]


class ParlaysResponse(BaseModel):
    league: League
    refreshed_at: datetime
    parlays_by_legs: dict[int, list[ParlayResponse]]


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
player_prop_service = PlayerPropService(history=recommendation_service.history)


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


@app.get("/api/parlays", response_model=ParlaysResponse)
def get_parlays(
    league: League = Query(default="all"),
    limit: int = Query(default=5, ge=1, le=10),
):
    selected_leagues = LEAGUES if league == "all" else (league,)
    candidates = [
        leg
        for leg in (
            leg_from_recommendation(rec)
            for rec in recommendation_service.load_recommendations(selected_leagues)
        )
        if leg is not None
    ]
    for selected in selected_leagues:
        candidates.extend(
            leg
            for leg in (leg_from_prop(quote) for quote in player_prop_service.ranked_player_props(selected))
            if leg is not None
        )

    return ParlaysResponse(
        league=league,
        refreshed_at=datetime.now(timezone.utc),
        parlays_by_legs={
            leg_count: [_parlay_response(parlay) for parlay in build_parlays(candidates, leg_count, limit)]
            for leg_count in range(MIN_LEGS, MAX_LEGS + 1)
        },
    )


def _parlay_response(parlay):
    return ParlayResponse(
        legs=[
            ParlayLegResponse(
                leg_id=leg.leg_id,
                source=leg.source,
                market=leg.kind if leg.kind != "prop" else (leg.stat_id or "prop"),
                description=leg.description,
                matchup=leg.matchup,
                probability=leg.probability,
                odds=leg.odds,
            )
            for leg in parlay.legs
        ],
        leg_count=len(parlay.legs),
        probability=parlay.probability,
        decimal_odds=parlay.decimal_odds,
        american_odds=parlay.american_odds,
        expected_value=parlay.expected_value,
        has_correlated_legs=parlay.correlated,
        notes=parlay.notes,
    )


@app.get("/api/player-props", response_model=PlayerPropsResponse)
def get_player_props(league: Literal["nfl", "college-football"] = Query(default="nfl")):
    quotes = player_prop_service.ranked_player_props(league)
    return PlayerPropsResponse(
        league=league,
        refreshed_at=player_prop_service.last_refreshed_at or datetime.now(timezone.utc),
        props=quotes,
    )
