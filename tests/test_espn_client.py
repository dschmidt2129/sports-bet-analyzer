import pytest

from sports_bet_analyzer.espn_client import (
    apply_team_season_stats,
    enrich_games_with_team_stats,
    fetch_all_league_team_stats,
    flatten_team_statistics,
    parse_games_from_scoreboard,
    parse_odds_from_competition,
    parse_teams,
)
from sports_bet_analyzer.models import Game, TeamStats


def _competitor(home_away, team_id, name, score="21"):
    return {
        "homeAway": home_away,
        "score": score,
        "team": {"id": team_id, "displayName": name},
    }


def _event(with_odds=True, completed=True):
    competition = {
        "competitors": [_competitor("home", "1", "Home Team"), _competitor("away", "2", "Away Team")],
        "status": {"type": {"completed": completed}},
    }
    if with_odds:
        competition["odds"] = [
            {
                "provider": {"name": "ESPN BET"},
                "spread": -3.5,
                "overUnder": 44.5,
                "homeTeamOdds": {"moneyLine": -180},
                "awayTeamOdds": {"moneyLine": 150},
            }
        ]
    return {"id": "401", "date": "2026-09-21T17:00Z", "week": {"number": 3}, "competitions": [competition]}


def test_parse_games_from_scoreboard_basic():
    raw = {"events": [_event()]}
    games = parse_games_from_scoreboard(raw, "nfl")

    assert len(games) == 1
    game = games[0]
    assert game.game_id == "401"
    assert game.league == "nfl"
    assert game.week == 3
    assert game.home_team.name == "Home Team"
    assert game.away_team.name == "Away Team"
    assert game.home_score == 21
    assert game.completed is True
    assert game.odds.home_spread == -3.5
    assert game.odds.over_under == 44.5
    assert game.odds.home_moneyline == -180


def test_parse_games_skips_malformed_event():
    raw = {"events": [{"id": "bad"}]}
    games = parse_games_from_scoreboard(raw, "nfl")
    assert games == []


def test_parse_odds_from_competition_missing_odds():
    assert parse_odds_from_competition({}) is None


def test_flatten_team_statistics_finds_nested_stat_entries():
    raw = {
        "results": {
            "stats": {
                "categories": [
                    {
                        "name": "scoring",
                        "stats": [
                            {"name": "avgPointsFor", "abbreviation": "PPG", "value": 27.5},
                            {"name": "avgPointsAgainst", "abbreviation": "PAPG", "value": 19.0},
                        ],
                    }
                ]
            }
        }
    }

    flat = flatten_team_statistics(raw)

    assert flat["avgPointsFor"] == 27.5
    assert flat["PPG"] == 27.5
    assert flat["avgPointsAgainst"] == 19.0


def test_apply_team_season_stats_uses_first_matching_alias():
    stats = TeamStats(team_id="1", name="Home")
    stat_map = {"pointsPerGame": 24.0, "turnoverDifferential": 1.5}

    apply_team_season_stats(stats, stat_map)

    assert stats.points_per_game == 24.0
    assert stats.turnover_margin == 1.5
    assert stats.points_allowed_per_game == 0.0  # no alias present -> default retained


class _FakeClient:
    def __init__(self, stats_by_team):
        self.stats_by_team = stats_by_team
        self.calls = []

    def team_statistics(self, league, team_id):
        self.calls.append((league, team_id))
        return self.stats_by_team.get(team_id, {})


def test_enrich_games_with_team_stats_caches_per_team():
    home = TeamStats(team_id="1", name="Home")
    away = TeamStats(team_id="2", name="Away")
    game = Game(game_id="g1", league="nfl", date="2026-09-21", home_team=home, away_team=away)

    stats_by_team = {
        "1": {"results": {"stats": {"categories": [{"stats": [{"name": "avgPointsFor", "value": 30.0}]}]}}},
    }
    client = _FakeClient(stats_by_team)

    cache = enrich_games_with_team_stats(client, [game, game])

    assert home.points_per_game == 30.0
    assert away.points_per_game == 0.0
    # Second pass over the same game shouldn't re-fetch either team's stats.
    assert client.calls == [("nfl", "1"), ("nfl", "2")]
    assert set(cache.keys()) == {("nfl", "1"), ("nfl", "2")}


def test_parse_teams_extracts_id_and_name():
    raw = {
        "sports": [
            {"leagues": [{"teams": [
                {"team": {"id": "1", "displayName": "Home Team"}},
                {"team": {"id": "2", "displayName": "Away Team"}},
            ]}]}
        ]
    }

    teams = parse_teams(raw, "nfl")

    assert [t.team_id for t in teams] == ["1", "2"]
    assert [t.name for t in teams] == ["Home Team", "Away Team"]


def test_parse_teams_handles_malformed_response():
    assert parse_teams({}, "nfl") == []


class _FakeLeagueClient(_FakeClient):
    def __init__(self, stats_by_team, teams_raw):
        super().__init__(stats_by_team)
        self.teams_raw = teams_raw

    def teams(self, league):
        return self.teams_raw


def test_fetch_all_league_team_stats_covers_every_team_including_byes():
    teams_raw = {
        "sports": [
            {"leagues": [{"teams": [
                {"team": {"id": "1", "displayName": "Team One"}},
                {"team": {"id": "2", "displayName": "Team Two"}},
                {"team": {"id": "3", "displayName": "Bye Team"}},
            ]}]}
        ]
    }
    stats_by_team = {
        "1": {"results": {"stats": {"categories": [{"stats": [{"name": "avgPointsFor", "value": 28.0}]}]}}},
    }
    client = _FakeLeagueClient(stats_by_team, teams_raw)

    league_teams = fetch_all_league_team_stats(client, "nfl")

    assert set(league_teams.keys()) == {"1", "2", "3"}
    assert league_teams["1"].points_per_game == 28.0
    assert league_teams["3"].points_per_game == 0.0
