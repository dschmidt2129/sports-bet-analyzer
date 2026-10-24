export type League = "all" | "nfl" | "college-football";

export interface Recommendation {
  game_id: string;
  bet_type: string;
  selection: string;
  probability: number;
  reasoning: string;
  home_team_name: string;
  away_team_name: string;
  odds: number | null;
}

export interface RecommendationsResponse {
  league: League;
  refreshed_at: string;
  recommendations: Recommendation[];
}

export interface PlayerPropQuote {
  event_id: string;
  league: string;
  odd_id: string;
  player_id: string;
  player_name: string;
  team_id: string | null;
  opponent_team_id: string | null;
  stat_id: string;
  period_id: string;
  side_id: "over" | "under";
  bookmaker_id: string;
  line: number;
  odds: number;
  fair_odds: number | null;
  probability: number;
  captured_at: string;
}

export interface PlayerPropsResponse {
  league: string;
  refreshed_at: string;
  props: PlayerPropQuote[];
}

export interface ParlayLeg {
  leg_id: string;
  source: "game" | "prop";
  market: string;
  description: string;
  matchup: string;
  probability: number;
  odds: number;
}

export interface Parlay {
  legs: ParlayLeg[];
  leg_count: number;
  probability: number;
  decimal_odds: number;
  american_odds: number;
  expected_value: number;
  has_correlated_legs: boolean;
  notes: string[];
}

export interface ParlaysResponse {
  league: League;
  leg_count: number;
  refreshed_at: string;
  parlays: Parlay[];
}
