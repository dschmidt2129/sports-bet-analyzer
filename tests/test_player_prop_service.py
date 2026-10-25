from datetime import datetime, timedelta, timezone

from sports_bet_analyzer.player_prop_service import PlayerPropService


def _starts_in(days):
    return {"startsAt": (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()}


class FakeClient:
    def __init__(self, events):
        self.response = events
        self.calls = []

    def events(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class FakeHistory:
    def __init__(self):
        self.saved = []

    def save_player_prop_snapshot(self, quote):
        self.saved.append(quote)


def test_service_persists_and_caches_player_prop_quotes():
    client = FakeClient(
        [
            {
                "eventID": "event-1",
                "status": _starts_in(0),
                "players": {"player-1": {"name": "Player One", "teamID": "team-1"}},
                "odds": {
                    "rushing_yards-player-1-game-ou-over": {
                        "oddID": "rushing_yards-player-1-game-ou-over",
                        "statID": "rushing_yards",
                        "statEntityID": "player-1",
                        "playerID": "player-1",
                        "periodID": "game",
                        "betTypeID": "ou",
                        "sideID": "over",
                        "byBookmaker": {
                            "draftkings": {"available": True, "overUnder": "65.5", "odds": "-110"}
                        },
                    }
                },
            }
        ]
    )
    history = FakeHistory()
    service = PlayerPropService(client=client, history=history)

    first = service.load_player_props("nfl")
    second = service.load_player_props("nfl")

    assert first == second
    assert len(client.calls) == 1
    assert client.calls[0]["league_id"] == "NFL"
    assert history.saved == first
    assert first[0]["line"] == 65.5


def test_service_drops_events_outside_current_week():
    def event(event_id, days):
        return {
            "eventID": event_id,
            "status": _starts_in(days),
            "players": {"p": {"name": "P"}},
            "odds": {
                "o": {
                    "oddID": "o", "statID": "rushing_yards", "playerID": "p", "betTypeID": "ou",
                    "sideID": "over",
                    "byBookmaker": {"draftkings": {"available": True, "overUnder": "10.5", "odds": "-110"}},
                }
            },
        }

    client = FakeClient([event("old", -14), event("later", 30), event("now", 0)])
    service = PlayerPropService(client=client, history=FakeHistory())

    assert {q["event_id"] for q in service.load_player_props("nfl")} == {"now"}


def test_service_rejects_unknown_league():
    service = PlayerPropService(client=FakeClient([]), history=FakeHistory())

    try:
        service.load_player_props("mlb")
    except ValueError as exc:
        assert "Unsupported player-prop league" in str(exc)
    else:
        raise AssertionError("Expected unsupported league to be rejected")

class FakePredictor:
    def predict_probability(self, bet_type, features):
        return 0.5 + features["season_edge"]


def _quote(odd_id, side, season_avg, odds=-110, book="draftkings"):
    return {
        "event_id": "e1", "league": "nfl", "odd_id": odd_id, "player_id": "p", "player_name": "P",
        "team_id": None, "stat_id": "rushing_yards", "period_id": "game", "side_id": side,
        "bookmaker_id": book, "line": 100.0, "odds": odds, "fair_odds": None,
        "season_avg": season_avg, "last3_avg": season_avg, "opponent_defense_ypp_allowed": None,
        "actual_value": None, "captured_at": "t",
    }


def test_ranked_player_props_orders_and_dedupes():
    service = PlayerPropService(client=FakeClient([]), history=FakeHistory(), predictor=FakePredictor())
    quotes = [_quote(f"o{i}", "over", 100 + i) for i in range(9)]
    quotes.append(_quote("o8", "over", 108, odds=-105, book="fanduel"))
    service._cache["nfl"] = (float("inf"), quotes)

    top = service.ranked_player_props("nfl")

    assert len(top) == 9
    assert [q["odd_id"] for q in top] == [f"o{i}" for i in range(8, -1, -1)]
    assert top[0]["bookmaker_id"] == "fanduel"
    assert top[0]["probability"] > top[-1]["probability"]


def test_ranked_player_props_can_require_a_bookmaker():
    service = PlayerPropService(client=FakeClient([]), history=FakeHistory(), predictor=FakePredictor())
    quotes = [
        _quote("market-dk", "over", 101, book="draftkings"),
        _quote("market-fd", "over", 110, book="fanduel"),
    ]
    service._cache["nfl"] = (float("inf"), quotes)

    ranked = service.ranked_player_props("nfl", bookmaker_id="draftkings")

    assert [quote["odd_id"] for quote in ranked] == ["market-dk"]
    assert ranked[0]["bookmaker_id"] == "draftkings"


def test_current_week_window_runs_wednesday_to_wednesday():
    from datetime import datetime, timezone

    from sports_bet_analyzer.player_prop_service import current_week_window

    start, end = current_week_window(datetime(2026, 10, 17, 15, 30, tzinfo=timezone.utc))

    assert start == datetime(2026, 10, 14, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 21, tzinfo=timezone.utc)
