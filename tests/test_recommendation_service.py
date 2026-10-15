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