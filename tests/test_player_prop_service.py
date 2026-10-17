from sports_bet_analyzer.player_prop_service import PlayerPropService


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


def test_service_rejects_unknown_league():
    service = PlayerPropService(client=FakeClient([]), history=FakeHistory())

    try:
        service.load_player_props("mlb")
    except ValueError as exc:
        assert "Unsupported player-prop league" in str(exc)
    else:
        raise AssertionError("Expected unsupported league to be rejected")