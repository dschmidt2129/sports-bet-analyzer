"""Builds suggested parlays from game recommendations and player-prop quotes.

Legs from different games are treated as independent. Legs from the same game are
priced with a Gaussian copula whose pairwise correlations are conservative
heuristics (not fitted to history), and contradictory same-game legs are excluded.
"""
import itertools
import math
import random
import re
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Optional

MIN_LEGS = 2
MAX_LEGS = 4
MAX_POOL = 10
MIN_PROP_PROBABILITY = 0.60
COPULA_SAMPLES = 10_000
COPULA_SEED = 20240

_NORMAL = NormalDist()
_samples = None


@dataclass
class ParlayLeg:
    leg_id: str
    source: str  # "game" | "prop"
    kind: str  # "spread" | "moneyline" | "total" | "prop"
    description: str
    matchup: str
    probability: float
    odds: int
    teams: frozenset
    picked_team: Optional[str] = None
    direction: int = 0  # +1 over, -1 under
    player_id: Optional[str] = None
    stat_id: Optional[str] = None
    team: Optional[str] = None


@dataclass
class Parlay:
    legs: list
    probability: float
    decimal_odds: float
    american_odds: int
    expected_value: float
    correlated: bool
    notes: list = field(default_factory=list)


def normalize_team(value):
    value = re.sub(r"_(NFL|NCAAF)$", "", value or "", flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _team_match(a, b):
    if not a or not b:
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a))


def american_to_decimal(odds):
    return 1 + (odds / 100 if odds > 0 else 100 / -odds)


def decimal_to_american(decimal_odds):
    if decimal_odds >= 2:
        return round((decimal_odds - 1) * 100)
    return round(-100 / (decimal_odds - 1))


def leg_from_recommendation(rec):
    """Convert a PredictionResult into a leg; None when it has no usable price."""
    if rec.odds is None or not 0 < rec.probability < 1:
        return None
    home, away = normalize_team(rec.home_team_name), normalize_team(rec.away_team_name)
    leg = ParlayLeg(
        leg_id=f"game:{rec.game_id}:{rec.bet_type}",
        source="game",
        kind=rec.bet_type,
        description=rec.selection,
        matchup=f"{rec.away_team_name} @ {rec.home_team_name}",
        probability=rec.probability,
        odds=int(rec.odds),
        teams=frozenset(t for t in (home, away) if t),
    )
    if rec.bet_type == "total":
        leg.direction = 1 if rec.selection.lower().startswith("over") else -1
    elif rec.bet_type in {"spread", "moneyline"}:
        selection = normalize_team(rec.selection)
        leg.picked_team = next((t for t in (home, away) if t and selection.startswith(t)), None)
        if leg.picked_team is None:
            return None
    return leg


def leg_from_prop(quote):
    """Convert a ranked player-prop quote into a leg; None when below the probability bar."""
    probability, odds = quote.get("probability"), quote.get("odds")
    if odds is None or probability is None or probability < MIN_PROP_PROBABILITY or probability >= 1:
        return None
    team = normalize_team(quote.get("team_id"))
    opponent = normalize_team(quote.get("opponent_team_id"))
    side = quote.get("side_id")
    stat = str(quote.get("stat_id", "")).replace("_", " ")
    return ParlayLeg(
        leg_id=f"prop:{quote['event_id']}:{quote['odd_id']}",
        source="prop",
        kind="prop",
        description=f"{quote['player_name']} {str(side).title()} {quote['line']} {stat}",
        matchup=f"{quote.get('team_id') or ''} vs {quote.get('opponent_team_id') or ''}".strip(),
        probability=probability,
        odds=int(odds),
        teams=frozenset(t for t in (team, opponent) if t),
        direction=1 if side == "over" else -1,
        player_id=quote.get("player_id"),
        stat_id=quote.get("stat_id"),
        team=team or None,
    )


def same_game(a, b):
    return any(_team_match(x, y) for x in a.teams for y in b.teams)


def pair_correlation(a, b):
    """Correlation between two same-game legs hitting; None when the pair is not allowed."""
    if a.kind == "prop" and b.kind != "prop":
        a, b = b, a
    if a.kind != "prop" and b.kind != "prop":
        if a.kind == "total" or b.kind == "total":
            return 0.0
        return 0.7 if _team_match(a.picked_team, b.picked_team) else None

    if a.kind == "prop" and b.kind == "prop":
        if a.player_id and a.player_id == b.player_id:
            return None if a.stat_id == b.stat_id else 0.4 * a.direction * b.direction
        if a.team and b.team:
            base = 0.1 if _team_match(a.team, b.team) else 0.05
            return base * a.direction * b.direction
        return 0.0

    if a.kind == "total":
        return 0.3 * a.direction * b.direction
    if not b.team:
        return 0.0
    base = 0.25 if _team_match(a.picked_team, b.team) else -0.15
    return base * b.direction


def _cholesky(matrix):
    n = len(matrix)
    lower = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            total = sum(lower[i][k] * lower[j][k] for k in range(j))
            if i == j:
                value = matrix[i][i] - total
                if value <= 1e-9:
                    return None
                lower[i][j] = math.sqrt(value)
            else:
                lower[i][j] = (matrix[i][j] - total) / lower[j][j]
    return lower


def _standard_samples():
    global _samples
    if _samples is None:
        rng = random.Random(COPULA_SEED)
        _samples = [[rng.gauss(0, 1) for _ in range(MAX_LEGS)] for _ in range(COPULA_SAMPLES)]
    return _samples


def joint_probability(probabilities, correlations):
    """P(all legs hit) under a Gaussian copula; correlations is a full symmetric matrix."""
    n = len(probabilities)
    lower = None
    for blend in (0.0, 0.25, 0.5, 0.75, 1.0):
        shrunk = [
            [1.0 if i == j else (1 - blend) * correlations[i][j] for j in range(n)] for i in range(n)
        ]
        lower = _cholesky(shrunk)
        if lower is not None:
            break
    thresholds = [_NORMAL.inv_cdf(p) for p in probabilities]
    hits = 0
    for z in _standard_samples():
        for i in range(n):
            if sum(lower[i][k] * z[k] for k in range(i + 1)) > thresholds[i]:
                break
        else:
            hits += 1
    return hits / COPULA_SAMPLES


def _group_by_game(legs):
    groups = []
    for leg in legs:
        for group in groups:
            if any(same_game(leg, other) for other in group):
                group.append(leg)
                break
        else:
            groups.append([leg])
    return groups


def _group_probability(group, cache):
    if len(group) == 1:
        return group[0].probability
    ordered = sorted(group, key=lambda leg: leg.leg_id)
    key = tuple(leg.leg_id for leg in ordered)
    if key not in cache:
        matrix = [
            [1.0 if a is b else pair_correlation(a, b) for b in ordered] for a in ordered
        ]
        cache[key] = joint_probability([leg.probability for leg in ordered], matrix)
    return cache[key]


def _allowed(legs):
    return not any(same_game(a, b) for a, b in itertools.combinations(legs, 2))


def build_parlays(legs, leg_count=3, limit=5):
    """Return the highest-probability valid parlays of exactly leg_count legs."""
    if not MIN_LEGS <= leg_count <= MAX_LEGS:
        raise ValueError(f"leg_count must be between {MIN_LEGS} and {MAX_LEGS}")
    unique = {leg.leg_id: leg for leg in legs}
    pool = sorted(unique.values(), key=lambda leg: leg.probability, reverse=True)[:MAX_POOL]

    cache = {}
    parlays = []
    for combo in itertools.combinations(pool, leg_count):
        if not _allowed(combo):
            continue
        groups = _group_by_game(combo)
        probability = math.prod(_group_probability(group, cache) for group in groups)
        decimal_odds = math.prod(american_to_decimal(leg.odds) for leg in combo)
        correlated = any(len(group) > 1 for group in groups)
        notes = [
            "DraftKings line availability and parlay eligibility are not verified; confirm in the sportsbook."
        ]
        if correlated:
            notes.append(
                "Includes same-game legs priced with estimated correlations; sportsbooks "
                "may price same-game parlays differently."
            )
        parlays.append(
            Parlay(
                legs=list(combo),
                probability=probability,
                decimal_odds=decimal_odds,
                american_odds=decimal_to_american(decimal_odds),
                expected_value=probability * decimal_odds - 1,
                correlated=correlated,
                notes=notes,
            )
        )
    parlays.sort(key=lambda p: p.probability, reverse=True)
    return parlays[:limit]
