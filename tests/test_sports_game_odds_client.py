from sports_bet_analyzer.sports_game_odds_client import (
    SportsGameOddsClient,
    parse_player_prop_quotes,
)


class FakeResponse:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return {"success": True, "data": [{"eventID": "event-1"}]}


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params, timeout))
        return FakeResponse()


def test_client_sends_api_key_and_returns_event_data():
    session = FakeSession()
    client = SportsGameOddsClient(api_key="test-key", session=session, timeout=4)

    assert client.events("NFL", limit=12) == [{"eventID": "event-1"}]
    url, params, timeout = session.calls[0]
    assert url.endswith("/v2/events")
    assert params["apiKey"] == "test-key"
    assert params["leagueID"] == "NFL"
    assert params["oddsAvailable"] == "true"
    assert params["limit"] == 12
    assert timeout == 4


def test_client_reads_api_key_from_environment(monkeypatch):
    monkeypatch.setenv("SPORTSGAMEODDS_API_KEY", "env-key")

    client = SportsGameOddsClient()

    assert client.api_key == "env-key"


def test_parser_flattens_player_quotes_and_ignores_team_markets():
    events = [
        {
            "eventID": "event-1",
            "players": {"player-1": {"name": "Player One", "teamID": "team-1"}},
            "odds": {
                "passing_yards-player-1-game-ou-over": {
                    "oddID": "passing_yards-player-1-game-ou-over",
                    "statID": "passing_yards",
                    "statEntityID": "player-1",
                    "playerID": "player-1",
                    "periodID": "game",
                    "betTypeID": "ou",
                    "sideID": "over",
                    "fairOdds": "-105",
                    "byBookmaker": {
                        "draftkings": {"available": True, "overUnder": "245.5", "odds": "-110"},
                        "fanduel": {"available": False, "overUnder": "246.5", "odds": "-108"},
                    },
                },
                "points-home-game-sp-home": {
                    "statID": "points",
                    "statEntityID": "home",
                    "betTypeID": "sp",
                    "sideID": "home",
                    "byBookmaker": {"draftkings": {"available": True, "overUnder": "3.5", "odds": "-110"}},
                },
            },
        }
    ]

    props = parse_player_prop_quotes(events, captured_at="2026-10-16T12:00:00+00:00")

    assert len(props) == 1
    assert props[0]["player_name"] == "Player One"
    assert props[0]["team_id"] == "team-1"
    assert props[0]["line"] == 245.5
    assert props[0]["odds"] == -110
    assert props[0]["fair_odds"] == -105
    assert props[0]["captured_at"] == "2026-10-16T12:00:00+00:00"