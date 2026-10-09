"""Thin wrapper around ESPN's public (unofficial, undocumented) JSON API.

Endpoints are not guaranteed stable - ESPN has changed query-param support before
(see https://gist.github.com/akeaswaran/b48b02f1c94f873c6655e7129910fc3b). All
calls are defensive: on failure they log a warning and return an empty result
instead of raising, so a single broken endpoint doesn't crash the app.
"""
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sports_bet_analyzer.models import Game, OddsLine, TeamStats

log = logging.getLogger(__name__)

BASE = "https://site.api.espn.com/apis/site/v2/sports/football"
LEAGUES = ("nfl", "college-football")

_DEFAULT_TIMEOUT = 10

# ESPN's team-statistics response doesn't document exact stat names, so each
# metric is looked up by trying several known aliases in order.
_POINTS_PER_GAME_KEYS = ("avgPointsFor", "pointsPerGame", "totalPointsPerGame")
_POINTS_ALLOWED_KEYS = ("avgPointsAgainst", "pointsAllowedPerGame", "opponentPointsPerGame")
_YARDS_PER_PLAY_KEYS = ("yardsPerPlay", "netYardsPerPlay", "totalYardsPerPlay")
_YARDS_ALLOWED_PER_PLAY_KEYS = ("opponentYardsPerPlay", "yardsPerPlayAllowed", "defensiveYardsPerPlay")
_TURNOVER_MARGIN_KEYS = ("turnOverDifferential", "turnoverDifferential", "turnoverMargin")
_WIN_PCT_KEYS = ("winPercent", "winPct")


class ESPNClient:
    def __init__(self, session=None, timeout=_DEFAULT_TIMEOUT):
        self.session = session or _build_session()
        self.timeout = timeout

    def _get(self, url, params=None):
        log.debug("GET %s params=%s", url, params)
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            log.debug("GET %s -> status=%s", url, resp.status_code)
            return data
        except requests.RequestException:
            log.warning("ESPN request failed: %s params=%s", url, params, exc_info=True)
            return {}

    def scoreboard(self, league, week=None, groups=None, limit=300):
        log.info("Fetching scoreboard league=%s week=%s groups=%s", league, week, groups)
        params = {"limit": limit}
        if week is not None:
            params["week"] = week
        if groups is not None:
            params["groups"] = groups
        raw = self._get(f"{BASE}/{league}/scoreboard", params=params)
        log.info("Scoreboard league=%s returned %d event(s)", league, len(raw.get("events", [])))
        return raw

    def summary(self, league, event_id):
        log.info("Fetching summary league=%s event_id=%s", league, event_id)
        return self._get(f"{BASE}/{league}/summary", params={"event": event_id})

    def teams(self, league):
        log.info("Fetching teams league=%s", league)
        return self._get(f"{BASE}/{league}/teams")

    def team_statistics(self, league, team_id):
        log.info("Fetching team statistics league=%s team_id=%s", league, team_id)
        return self._get(f"{BASE}/{league}/teams/{team_id}/statistics")

    def fpi(self, league):
        # Undocumented; treated as best-effort cold-start data only.
        log.info("Fetching FPI ratings league=%s", league)
        return self._get(f"{BASE}/{league}/fpi")


def _build_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "sports-bet-analyzer/1.0"})
    return session


def parse_games_from_scoreboard(raw, league):
    games = []
    for event in raw.get("events", []):
        try:
            games.append(_parse_event(event, league))
        except (KeyError, IndexError, TypeError):
            log.warning("Skipping malformed scoreboard event id=%s", event.get("id"), exc_info=True)
    log.debug("Parsed %d game(s) from %d scoreboard event(s)", len(games), len(raw.get("events", [])))
    return games


def _parse_event(event, league):
    competition = event["competitions"][0]
    competitors = competition["competitors"]
    home_raw = next(c for c in competitors if c["homeAway"] == "home")
    away_raw = next(c for c in competitors if c["homeAway"] == "away")

    home_team = _team_stats_from_competitor(home_raw)
    away_team = _team_stats_from_competitor(away_raw)

    completed = competition.get("status", {}).get("type", {}).get("completed", False)

    return Game(
        game_id=event["id"],
        league=league,
        date=event.get("date", ""),
        week=event.get("week", {}).get("number") if isinstance(event.get("week"), dict) else None,
        home_team=home_team,
        away_team=away_team,
        odds=parse_odds_from_competition(competition),
        completed=bool(completed),
        home_score=int(home_raw["score"]) if home_raw.get("score") not in (None, "") else None,
        away_score=int(away_raw["score"]) if away_raw.get("score") not in (None, "") else None,
    )


def _team_stats_from_competitor(competitor):
    team = competitor["team"]
    return TeamStats(team_id=team["id"], name=team.get("displayName", team.get("name", "")))


def parse_odds_from_competition(competition):
    odds_list = competition.get("odds")
    if not odds_list:
        return None
    odds = odds_list[0]
    return OddsLine(
        provider=odds.get("provider", {}).get("name", "unknown"),
        home_spread=odds.get("spread"),
        over_under=odds.get("overUnder"),
        home_moneyline=_safe_int(odds.get("homeTeamOdds", {}).get("moneyLine")),
        away_moneyline=_safe_int(odds.get("awayTeamOdds", {}).get("moneyLine")),
    )


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def flatten_team_statistics(raw):
    """Flattens ESPN's nested stat-category tree into {name/abbreviation: value}."""
    flat = {}
    _flatten_into(raw, flat)
    log.debug("Flattened %d team statistic(s)", len(flat))
    return flat


def _flatten_into(node, flat):
    if isinstance(node, dict):
        if "value" in node and ("name" in node or "abbreviation" in node):
            for key in (node.get("name"), node.get("abbreviation")):
                if key:
                    flat[key] = node["value"]
        for value in node.values():
            _flatten_into(value, flat)
    elif isinstance(node, list):
        for item in node:
            _flatten_into(item, flat)


def _first_present(stat_map, aliases, default=0.0):
    for alias in aliases:
        if alias in stat_map:
            return float(stat_map[alias])
    log.debug("No stat found for aliases=%s; defaulting to %s", aliases, default)
    return default


def apply_team_season_stats(team_stats, stat_map):
    """Fills in TeamStats fields (ppg, yards/play, turnovers, win%) from a flattened stat map."""
    team_stats.points_per_game = _first_present(stat_map, _POINTS_PER_GAME_KEYS, team_stats.points_per_game)
    team_stats.points_allowed_per_game = _first_present(
        stat_map, _POINTS_ALLOWED_KEYS, team_stats.points_allowed_per_game
    )
    team_stats.yards_per_play = _first_present(stat_map, _YARDS_PER_PLAY_KEYS, team_stats.yards_per_play)
    team_stats.yards_allowed_per_play = _first_present(
        stat_map, _YARDS_ALLOWED_PER_PLAY_KEYS, team_stats.yards_allowed_per_play
    )
    team_stats.turnover_margin = _first_present(stat_map, _TURNOVER_MARGIN_KEYS, team_stats.turnover_margin)
    team_stats.win_pct = _first_present(stat_map, _WIN_PCT_KEYS, team_stats.win_pct)
    return team_stats


def enrich_games_with_team_stats(client, games, cache=None):
    """Fetches and applies season team-statistics for every unique team referenced in games.

    `cache` (keyed by (league, team_id) -> flattened stat map) can be passed in and reused
    across multiple calls (e.g. across weeks in a backfill run) to cut down on API calls,
    since the endpoint only returns current season-to-date stats, not a historical snapshot.
    """
    cache = cache if cache is not None else {}
    for game in games:
        for team in (game.home_team, game.away_team):
            key = (game.league, team.team_id)
            if key not in cache:
                raw = client.team_statistics(game.league, team.team_id)
                cache[key] = flatten_team_statistics(raw)
            apply_team_season_stats(team, cache[key])
    return cache


def parse_teams(raw, league):
    """Parses the full team roster from the /teams endpoint (id + name only)."""
    try:
        league_teams = raw["sports"][0]["leagues"][0]["teams"]
    except (KeyError, IndexError, TypeError):
        log.warning("Malformed teams response for league=%s", league, exc_info=True)
        return []

    teams = []
    for entry in league_teams:
        team = entry.get("team", {})
        team_id = team.get("id")
        if not team_id:
            continue
        teams.append(TeamStats(team_id=team_id, name=team.get("displayName", team.get("name", ""))))
    return teams


def fetch_all_league_team_stats(client, league, cache=None):
    """Fetches season stats for every team in the league, not just ones in a fetched game.

    Returns {team_id: TeamStats}. `cache` behaves the same as in enrich_games_with_team_stats
    and can be shared with it to avoid re-fetching the same team twice.
    """
    cache = cache if cache is not None else {}
    teams = parse_teams(client.teams(league), league)
    log.info("Fetched %d team(s) for full-league coverage league=%s", len(teams), league)

    for team in teams:
        key = (league, team.team_id)
        if key not in cache:
            raw = client.team_statistics(league, team.team_id)
            cache[key] = flatten_team_statistics(raw)
        apply_team_season_stats(team, cache[key])

    return {team.team_id: team for team in teams}
