from sports_bet_analyzer.recommendation_service import RecommendationService


class FailedScoreboardClient:
    def fpi(self, league):
        return {}

    def scoreboard(self, league):
        return None


class RecordingHistory:
    def __init__(self):
        self.saved_snapshots = []

    def save_team_stat_snapshot(self, *args, **kwargs):
        self.saved_snapshots.append((args, kwargs))


def test_failed_scoreboard_does_not_persist_snapshots():
    history = RecordingHistory()
    service = RecommendationService(
        client=FailedScoreboardClient(),
        predictor=object(),
        history=history,
    )

    assert service.load_recommendations(["nfl"]) == []
    assert history.saved_snapshots == []


class CountingClient(FailedScoreboardClient):
    def __init__(self):
        self.scoreboard_calls = 0

    def scoreboard(self, league):
        self.scoreboard_calls += 1
        return None


def test_failed_recommendation_loads_are_not_cached():
    client = CountingClient()
    service = RecommendationService(
        client=client, predictor=object(), history=RecordingHistory(), cache_ttl_seconds=600
    )

    service.load_recommendations(["nfl"])
    service.load_recommendations(["nfl"])

    assert client.scoreboard_calls == 2


def _service_with_loader(results_by_call, failed_by_call):
    service = RecommendationService(
        client=CountingClient(), predictor=object(), history=RecordingHistory(), cache_ttl_seconds=600
    )
    calls = []

    def fake_loader(leagues):
        index = len(calls)
        calls.append(tuple(leagues))
        return results_by_call[index], failed_by_call[index]

    service._load_recommendations = fake_loader
    return service, calls


def test_successful_non_empty_recommendations_are_cached_per_league_set_until_ttl_expires():
    service, calls = _service_with_loader([["pick"]] * 4, [False] * 4)

    assert service.load_recommendations(["nfl"]) == ["pick"]
    assert service.load_recommendations(["nfl"]) == ["pick"]
    assert len(calls) == 1

    service.load_recommendations(["college-football"])
    assert len(calls) == 2

    service.cache_ttl_seconds = 0
    service.load_recommendations(["nfl"])
    assert len(calls) == 3


def test_empty_recommendations_are_not_cached():
    service, calls = _service_with_loader([[], ["pick"], ["pick"]], [False] * 3)

    assert service.load_recommendations(["nfl"]) == []
    assert service.load_recommendations(["nfl"]) == ["pick"]
    assert service.load_recommendations(["nfl"]) == ["pick"]
    assert len(calls) == 2


def test_partially_failed_recommendations_are_not_cached():
    service, calls = _service_with_loader([["pick"], ["pick"]], [True, False])

    service.load_recommendations(["nfl"])
    service.load_recommendations(["nfl"])
    service.load_recommendations(["nfl"])

    assert len(calls) == 2