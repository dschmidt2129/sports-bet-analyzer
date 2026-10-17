import { useCallback, useEffect, useState } from "react";
import { Activity, ArrowDownUp, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";

import { fetchRecommendations } from "./api";
import type { League, Recommendation, RecommendationsResponse } from "./types";

const leagueOptions: { value: League; label: string }[] = [
  { value: "nfl", label: "NFL" },
  { value: "college-football", label: "College football" },
];

const marketNames: Record<string, string> = {
  spread: "Point spread",
  moneyline: "Moneyline",
  total: "Game total",
  prop: "Player prop",
};

function formatOdds(odds: number | null) {
  if (odds === null) return "Odds unavailable";
  return odds > 0 ? `+${odds}` : `${odds}`;
}

function RecommendationCard({ item, index }: { item: Recommendation; index: number }) {
  return (
    <article className="pick-card" style={{ animationDelay: `${index * 55}ms` }}>
      <div className="pick-topline">
        <span className="market-tag">{marketNames[item.bet_type] ?? item.bet_type}</span>
        <span className="confidence">
          <Activity size={14} aria-hidden="true" />
          {Math.round(item.probability * 100)}% confidence
        </span>
      </div>
      <div className="matchup">
        <span>{item.away_team_name}</span>
        <span className="at-sign">@</span>
        <span>{item.home_team_name}</span>
      </div>
      <h2 className="pick-selection">{item.selection}</h2>
      <p className="pick-reason">{item.reasoning}</p>
      <div className="pick-footer">
        <span>Market odds</span>
        <strong>{formatOdds(item.odds)}</strong>
      </div>
    </article>
  );
}

function LoadingCards() {
  return (
    <div className="pick-grid" aria-label="Loading recommendations" aria-busy="true">
      {[0, 1, 2].map((item) => (
        <div className="pick-card skeleton-card" key={item}>
          <span className="skeleton skeleton-pill" />
          <span className="skeleton skeleton-title" />
          <span className="skeleton skeleton-line" />
          <span className="skeleton skeleton-line short" />
        </div>
      ))}
    </div>
  );
}

export default function App() {
  const [league, setLeague] = useState<League>("nfl");
  const [data, setData] = useState<RecommendationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshCount, setRefreshCount] = useState(0);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchRecommendations(league, signal);
      setData(result);
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setError(cause instanceof Error ? cause.message : "Unable to load recommendations.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [league]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load, refreshCount]);

  const recommendations = data?.recommendations ?? [];
  const lastUpdated = data
    ? new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(
        new Date(data.refreshed_at),
      )
    : null;

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#" aria-label="Sports Bet Analyzer home">
          <span className="brand-mark"><Activity size={21} strokeWidth={2.5} /></span>
          <span>SPORTS<span className="brand-light"> / ANALYZER</span></span>
        </a>
        <span className="live-indicator"><span /> INSIGHTS, NOT GUARANTEES</span>
      </header>

      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow"><Sparkles size={15} /> WEEKLY EDGE</div>
          <h1>Find your<br /><span>next best pick.</span></h1>
          <p>Data-backed football insights, ranked by model confidence.</p>
        </div>
        <div className="hero-art" aria-hidden="true">
          <div className="art-ring ring-one" />
          <div className="art-ring ring-two" />
          <div className="art-ball">🏈</div>
          <span className="art-orbit orbit-one" />
          <span className="art-orbit orbit-two" />
        </div>
      </section>

      <section className="dashboard" aria-label="Recommendations">
        <div className="section-heading">
          <div>
            <div className="eyebrow subdued">YOUR DASHBOARD</div>
            <h2>Top recommendations</h2>
          </div>
          <button
            className={`refresh-button${loading ? " is-loading" : ""}`}
            onClick={() => setRefreshCount((count) => count + 1)}
            disabled={loading}
            aria-label="Refresh recommendations"
          >
            <RefreshCw size={16} />
            <span>Refresh</span>
          </button>
        </div>

        <div className="toolbar">
          <div className="league-tabs" role="group" aria-label="Filter by league">
            {leagueOptions.map((option) => (
              <button
                key={option.value}
                className={league === option.value ? "active" : ""}
                onClick={() => setLeague(option.value)}
                aria-pressed={league === option.value}
              >
                {option.label}
              </button>
            ))}
          </div>
          <div className="result-meta">
            <ArrowDownUp size={14} />
            <span>{loading ? "Updating" : `${recommendations.length} picks`}</span>
            {lastUpdated && !loading && <span className="updated-time">· {lastUpdated}</span>}
          </div>
        </div>

        {error && (
          <div className="message-panel error-panel" role="alert">
            <div>
              <strong>Couldn’t load recommendations</strong>
              <p>{error} Check that the API is running and reachable from this device.</p>
            </div>
            <button onClick={() => setRefreshCount((count) => count + 1)}>Try again</button>
          </div>
        )}

        {loading && <LoadingCards />}

        {!loading && !error && recommendations.length > 0 && (
          <div className="pick-grid">
            {recommendations.map((item, index) => (
              <RecommendationCard key={`${item.game_id}-${item.bet_type}`} item={item} index={index} />
            ))}
          </div>
        )}

        {!loading && !error && recommendations.length === 0 && (
          <div className="message-panel empty-panel">
            <span className="empty-icon"><Activity size={21} /></span>
            <strong>No high-confidence picks yet</strong>
            <p>Try another league or check back when this week’s games are available.</p>
          </div>
        )}
      </section>

      <footer className="disclaimer">
        <ShieldCheck size={17} />
        <p>For informational purposes only. Predictions are not guarantees or financial advice. Please wager responsibly.</p>
      </footer>
    </main>
  );
}
