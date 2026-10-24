import type { League, ParlaysResponse, PlayerPropsResponse, RecommendationsResponse } from "./types";

const baseUrl = import.meta.env.VITE_API_BASE_URL?.replace(/\/+$/, "") ?? "";

export async function fetchParlays(
  league: League,
  legs: number,
  signal?: AbortSignal,
): Promise<ParlaysResponse> {
  const url = new URL(`${baseUrl}/api/parlays`, window.location.origin);
  url.searchParams.set("league", league);
  url.searchParams.set("legs", String(legs));

  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`The parlays service returned HTTP ${response.status}.`);
  }
  return response.json() as Promise<ParlaysResponse>;
}

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

export async function fetchPlayerProps(signal?: AbortSignal): Promise<PlayerPropsResponse> {
  const url = new URL(`${baseUrl}/api/player-props`, window.location.origin);
  url.searchParams.set("league", "nfl");

  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`The player-props service returned HTTP ${response.status}.`);
  }
  return response.json() as Promise<PlayerPropsResponse>;
}
