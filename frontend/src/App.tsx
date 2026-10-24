import { useCallback, useEffect, useState } from "react";
import { Activity, ArrowDownUp, Layers, RefreshCw, Search, ShieldCheck, Sparkles, Target } from "lucide-react";

import { fetchParlays, fetchPlayerProps, fetchRecommendations } from "./api";
import type {
  League,
  Parlay,
  ParlaysResponse,
  PlayerPropQuote,
  PlayerPropsResponse,
  Recommendation,
  RecommendationsResponse,
} from "./types";

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

function marketLabel(statId: string) {
  const labels: Record<string, string> = {
    passing_yards: "Pass yards",
    passing_tds: "Pass TDs",
    rushing_yards: "Rush yards",
    rushing_tds: "Rush TDs",
    receiving_yards: "Receiving yards",
    receptions: "Receptions",
    anytime_td: "Anytime TD",
  };
  return labels[statId] ?? statId.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function teamLabel(teamId: string | null) {
  return teamId?.replace(/_NFL$/, "").replaceAll("_", " ") ?? "NFL";
}

function bookmakerLabel(bookmakerId: string) {
  const labels: Record<string, string> = {
    draftkings: "DraftKings",
    fanduel: "FanDuel",
    espnbet: "ESPN BET",
  };
  return labels[bookmakerId] ?? bookmakerId.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function PlayerPropRow({ quote, index }: { quote: PlayerPropQuote; index: number }) {
  return (
    <article className="prop-row" style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}>
      <div className="prop-player">
        <strong>{quote.player_name}</strong>
        <span>{teamLabel(quote.team_id)}{quote.opponent_team_id && ` vs ${teamLabel(quote.opponent_team_id)}`} · {quote.period_id === "game" ? "Full game" : quote.period_id}</span>
      </div>
      <div className="prop-market">
        <span className="market-tag">{marketLabel(quote.stat_id)}</span>
        <strong className={quote.side_id === "over" ? "over-pick" : "under-pick"}>
          {quote.side_id.toUpperCase()} {quote.line}
        </strong>
      </div>
      <div className="prop-bookmaker">
        <span>{bookmakerLabel(quote.bookmaker_id)}</span>
        <strong>{formatOdds(quote.odds)}</strong>
      </div>
      <span className="confidence">
        <Activity size={14} aria-hidden="true" />
        {Math.round(quote.probability * 100)}% to hit
      </span>
    </article>
  );
}

function ParlayCard({ parlay, index }: { parlay: Parlay; index: number }) {
  return (
    <article className="pick-card parlay-card" style={{ animationDelay: `${index * 55}ms` }}>
      <div className="pick-topline">
        <span className="market-tag">{parlay.leg_count}-leg parlay</span>
        <span className="confidence">
          <Activity size={14} aria-hidden="true" />
          {Math.round(parlay.probability * 100)}% est. to hit
        </span>
      </div>
      <ol className="parlay-legs">
        {parlay.legs.map((leg) => (
          <li key={leg.leg_id}>
            <div>
              <strong>{leg.description}</strong>
              <span>{leg.matchup} · {leg.source === "prop" ? marketLabel(leg.market) : marketNames[leg.market] ?? leg.market}</span>
            </div>
            <span className="parlay-leg-odds">{formatOdds(leg.odds)}</span>
          </li>
        ))}
      </ol>
      {parlay.notes.map((note) => (
        <p className="pick-reason" key={note}>{note}</p>
      ))}
      <div className="pick-footer">
        <span>Combined odds</span>
        <strong>{formatOdds(parlay.american_odds)}</strong>
      </div>
    </article>
  );
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
  const [activeTab, setActiveTab] = useState<"picks" | "props" | "parlays">("picks");
  const [legCount, setLegCount] = useState(3);
  const [parlayData, setParlayData] = useState<ParlaysResponse | null>(null);
  const [parlaysLoading, setParlaysLoading] = useState(false);
  const [parlaysError, setParlaysError] = useState<string | null>(null);
  const [league, setLeague] = useState<League>("nfl");
  const [data, setData] = useState<RecommendationsResponse | null>(null);
  const [propData, setPropData] = useState<PlayerPropsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [propsLoading, setPropsLoading] = useState(false);
  const [propsError, setPropsError] = useState<string | null>(null);
  const [playerSearch, setPlayerSearch] = useState("");
  const [marketFilter, setMarketFilter] = useState("all");
  const [sideFilter, setSideFilter] = useState<"all" | "over" | "under">("all");
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

  const loadPlayerProps = useCallback(async (signal?: AbortSignal) => {
    setPropsLoading(true);
    setPropsError(null);
    try {
      setPropData(await fetchPlayerProps(signal));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setPropsError(cause instanceof Error ? cause.message : "Unable to load NFL player props.");
    } finally {
      if (!signal?.aborted) setPropsLoading(false);
    }
  }, []);

  const loadParlays = useCallback(async (signal?: AbortSignal) => {
    setParlaysLoading(true);
    setParlaysError(null);
    try {
      setParlayData(await fetchParlays(league, legCount, signal));
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setParlaysError(cause instanceof Error ? cause.message : "Unable to load suggested parlays.");
    } finally {
      if (!signal?.aborted) setParlaysLoading(false);
    }
  }, [league, legCount]);

  useEffect(() => {
    const controller = new AbortController();
    if (activeTab === "props") {
      void loadPlayerProps(controller.signal);
    } else if (activeTab === "parlays") {
      void loadParlays(controller.signal);
    } else {
      void load(controller.signal);
    }
    return () => controller.abort();
  }, [activeTab, load, loadPlayerProps, loadParlays, refreshCount]);

  const recommendations = data?.recommendations ?? [];
  const quotes = propData?.props ?? [];
  const visibleQuotes = quotes.filter((quote) => {
    const matchesMarket = marketFilter === "all" || quote.stat_id === marketFilter;
    const matchesSide = sideFilter === "all" || quote.side_id === sideFilter;
    const query = playerSearch.trim().toLowerCase();
    const matchesPlayer = !query || `${quote.player_name} ${quote.team_id ?? ""}`.toLowerCase().includes(query);
    return matchesMarket && matchesSide && matchesPlayer;
  });
  const marketOptions = [...new Set(quotes.map((quote) => quote.stat_id))].sort();
  const parlays = parlayData?.parlays ?? [];
  const isLoading = activeTab === "props" ? propsLoading : activeTab === "parlays" ? parlaysLoading : loading;
  const activeError = activeTab === "props" ? propsError : activeTab === "parlays" ? parlaysError : error;
  const lastUpdated =
    activeTab === "props" ? propData?.refreshed_at : activeTab === "parlays" ? parlayData?.refreshed_at : data?.refreshed_at;
  const formattedLastUpdated = lastUpdated
    ? new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" }).format(
        new Date(lastUpdated),
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

      <section className="dashboard" aria-label="Game picks and NFL player props">
        <div className="view-tabs" role="tablist" aria-label="Dashboard views">
          <button
            id="picks-tab"
            role="tab"
            aria-selected={activeTab === "picks"}
            aria-controls="picks-panel"
            className={activeTab === "picks" ? "active" : ""}
            onClick={() => setActiveTab("picks")}
          >
            <Activity size={16} /> Game picks
          </button>
          <button
            id="props-tab"
            role="tab"
            aria-selected={activeTab === "props"}
            aria-controls="props-panel"
            className={activeTab === "props" ? "active" : ""}
            onClick={() => setActiveTab("props")}
          >
            <Target size={16} /> NFL player props
          </button>
          <button
            id="parlays-tab"
            role="tab"
            aria-selected={activeTab === "parlays"}
            aria-controls="parlays-panel"
            className={activeTab === "parlays" ? "active" : ""}
            onClick={() => setActiveTab("parlays")}
          >
            <Layers size={16} /> Suggested parlays
          </button>
        </div>

        <div className="section-heading">
          <div>
            <div className="eyebrow subdued">
              {activeTab === "props" ? "SPORTSBOOK LINES" : activeTab === "parlays" ? "COMBINED PICKS" : "YOUR DASHBOARD"}
            </div>
            <h2>{activeTab === "props" ? "NFL player props" : activeTab === "parlays" ? "Suggested parlays" : "Top recommendations"}</h2>
          </div>
          <button
            className={`refresh-button${isLoading ? " is-loading" : ""}`}
            onClick={() => setRefreshCount((count) => count + 1)}
            disabled={isLoading}
            aria-label={
              activeTab === "props" ? "Refresh player props" : activeTab === "parlays" ? "Refresh parlays" : "Refresh recommendations"
            }
          >
            <RefreshCw size={16} />
            <span>Refresh</span>
          </button>
        </div>

        <div className="toolbar">
          {activeTab === "picks" || activeTab === "parlays" ? (
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
              {activeTab === "parlays" && (
                <label className="market-filter leg-select">
                  <span className="sr-only">Number of legs</span>
                  <select value={legCount} onChange={(event) => setLegCount(Number(event.target.value))}>
                    {[2, 3, 4].map((count) => (
                      <option key={count} value={count}>{count} legs</option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          ) : (
            <div className="prop-controls">
              <label className="prop-search">
                <Search size={15} aria-hidden="true" />
                <span className="sr-only">Search players or teams</span>
                <input
                  type="search"
                  value={playerSearch}
                  onChange={(event) => setPlayerSearch(event.target.value)}
                  placeholder="Search players or teams"
                />
              </label>
              <label className="market-filter">
                <span className="sr-only">Filter by market</span>
                <select value={marketFilter} onChange={(event) => setMarketFilter(event.target.value)}>
                  <option value="all">All markets</option>
                  {marketOptions.map((market) => (
                    <option key={market} value={market}>{marketLabel(market)}</option>
                  ))}
                </select>
              </label>
              <label className="market-filter">
                <span className="sr-only">Filter by over or under</span>
                <select value={sideFilter} onChange={(event) => setSideFilter(event.target.value as "all" | "over" | "under")}>
                  <option value="all">Over &amp; under</option>
                  <option value="over">Over</option>
                  <option value="under">Under</option>
                </select>
              </label>
            </div>
          )}
          <div className="result-meta">
            <ArrowDownUp size={14} />
            <span>{isLoading ? "Updating" : activeTab === "props" ? `${visibleQuotes.length} lines` : activeTab === "parlays" ? `${parlays.length} parlays` : `${recommendations.length} picks`}</span>
            {formattedLastUpdated && !isLoading && <span className="updated-time">· {formattedLastUpdated}</span>}
          </div>
        </div>

        <div
          role="tabpanel"
          id={`${activeTab}-panel`}
          aria-labelledby={`${activeTab}-tab`}
          tabIndex={0}
        >
        {activeError && (
          <div className="message-panel error-panel" role="alert">
            <div>
              <strong>
                {activeTab === "props"
                  ? "Couldn’t load player props"
                  : activeTab === "parlays"
                    ? "Couldn’t load suggested parlays"
                    : "Couldn’t load recommendations"}
              </strong>
              <p>{activeError} Check that the API is running and reachable from this device.</p>
            </div>
            <button onClick={() => setRefreshCount((count) => count + 1)}>Try again</button>
          </div>
        )}

        {isLoading && activeTab !== "props" && <LoadingCards />}
        {isLoading && activeTab === "props" && (
          <div className="prop-list" aria-label="Loading player props" aria-busy="true">
            {[0, 1, 2, 3].map((item) => <div className="prop-row prop-skeleton" key={item}><span /><span /><span /></div>)}
          </div>
        )}

        {activeTab === "picks" && !loading && !error && recommendations.length > 0 && (
          <div className="pick-grid">
            {recommendations.map((item, index) => (
              <RecommendationCard key={`${item.game_id}-${item.bet_type}`} item={item} index={index} />
            ))}
          </div>
        )}

        {activeTab === "picks" && !loading && !error && recommendations.length === 0 && (
          <div className="message-panel empty-panel">
            <span className="empty-icon"><Activity size={21} /></span>
            <strong>No high-confidence picks yet</strong>
            <p>Try another league or check back when this week’s games are available.</p>
          </div>
        )}

        {activeTab === "parlays" && !parlaysLoading && !parlaysError && parlays.length > 0 && (
          <div className="pick-grid">
            {parlays.map((parlay, index) => (
              <ParlayCard key={parlay.legs.map((leg) => leg.leg_id).join("|")} parlay={parlay} index={index} />
            ))}
          </div>
        )}

        {activeTab === "parlays" && !parlaysLoading && !parlaysError && parlays.length === 0 && (
          <div className="message-panel empty-panel">
            <span className="empty-icon"><Layers size={21} /></span>
            <strong>No suggested parlays yet</strong>
            <p>There aren’t enough priced, high-confidence legs to build a {legCount}-leg parlay. Try fewer legs or another league.</p>
          </div>
        )}

        {activeTab === "props" && !propsLoading && !propsError && visibleQuotes.length > 0 && (
          <div className="prop-list">
            {visibleQuotes.map((quote, index) => (
              <PlayerPropRow key={`${quote.event_id}-${quote.odd_id}-${quote.bookmaker_id}`} quote={quote} index={index} />
            ))}
          </div>
        )}

        {activeTab === "props" && !propsLoading && !propsError && visibleQuotes.length === 0 && (
          <div className="message-panel empty-panel">
            <span className="empty-icon"><Target size={21} /></span>
            <strong>{quotes.length > 0 ? "No matching player props" : "No player props available"}</strong>
            <p>{quotes.length > 0 ? "Try a different player search or market." : "Props may not be posted yet, or the odds feed may be unavailable."}</p>
          </div>
        )}
        </div>
      </section>

      <footer className="disclaimer">
        <ShieldCheck size={17} />
        <p>For informational purposes only. Predictions are not guarantees or financial advice. Please wager responsibly.</p>
      </footer>
    </main>
  );
}
