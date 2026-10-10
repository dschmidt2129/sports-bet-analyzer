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
