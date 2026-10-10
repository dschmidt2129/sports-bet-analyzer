import type { League, RecommendationsResponse } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "") ?? "";

export async function fetchRecommendations(
  league: League,
  signal?: AbortSignal,
): Promise<RecommendationsResponse> {
  const url = new URL(`${baseUrl}/api/recommendations`, window.location.origin);
  url.searchParams.set("league", league);

  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`The recommendations service returned HTTP ${response.status}.`);
  }
  return response.json() as Promise<RecommendationsResponse>;
}
