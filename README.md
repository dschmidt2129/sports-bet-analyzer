# Sports Bet Analyzer

A React mobile-friendly interface for high-confidence NFL and college football
bet recommendations, packaged for Android with Capacitor. A Python FastAPI
backend retains the existing ESPN integration, SQLite history, and prediction
logic.

> **Informational use only.** This tool does not place bets, guarantee
> outcomes, or constitute financial advice. Sports betting involves risk;
> bet only what you can afford to lose, and check your local laws and age
> requirements before wagering.

## Architecture

- `frontend/` contains the React + TypeScript + Vite UI and Capacitor Android
  project configuration.
- `src/sports_bet_analyzer/api.py` exposes recommendations at
  `/api/recommendations?league=all|nfl|college-football`.
- `player_prop_service.py` fetches and caches sportsbook player-prop quotes from
  SportsGameOdds at `/api/player-props?league=nfl`.
- `parlay.py` builds suggested 2–4 leg parlays from game picks and player props
  at `/api/parlays?league=all|nfl|college-football&legs=2..4`. See
  [Suggested parlays](#suggested-parlays).
- `storage.py` records timestamped player-prop quotes and eventual outcomes in
  `player_prop_snapshots` for future model training.
- `recommendation_service.py` coordinates the existing ESPN client, predictor,
  recommender, and SQLite history store.
- `espn_client.py` fetches ESPN scores, team stats, odds, and FPI ratings.
- `tools/train_offline.py` trains model weights from the locally cached game
  history. Training dependencies stay out of the runtime API.

## Run the backend

```bash
python -m venv .venv
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m uvicorn sports_bet_analyzer.api:app --app-dir src --reload
```

The API is available at `http://127.0.0.1:8000`; its interactive docs are at
`http://127.0.0.1:8000/docs`. For an Android device to access the API, run it
with `--host 0.0.0.0` and configure `VITE_API_BASE_URL` in `frontend/.env.local`
to an HTTPS URL reachable from that device. Do not expose an unencrypted API
port directly to the public internet. For a separately hosted web UI, set
`ALLOWED_ORIGINS` to a comma-separated list of its exact origins.

To enable player props, put your SportsGameOdds API key in the project-root
`.env` file. It is ignored by Git and loaded automatically when the backend
starts. The key is optional; without it, `/api/player-props` returns an empty
list and the rest of the API continues to work. To recreate the local file from
the template in PowerShell:

```powershell
Copy-Item .env.example .env
```

Then replace the blank `SPORTSGAMEODDS_API_KEY` value in `.env`. An environment
variable already set by the shell takes precedence over the file.

Player-prop responses are cached for ten minutes to match the free tier's update
cadence and reduce API usage. Quotes are saved with capture timestamps; only
settled rows with the required player-stat features are returned by the
training-data query.

## Suggested parlays

`/api/parlays` combines priced game picks and player props (props need a
SportsGameOdds key) into the highest-probability parlays of the requested size.

- Legs from different games are treated as independent; combined odds are the
  product of the legs' decimal odds.
- Legs from the same game are priced with a Gaussian copula using fixed,
  conservative pairwise correlations (for example, an over and a receiving-yards
  over are positively correlated). These correlations are heuristics, **not**
  fitted to historical data, so same-game probabilities are rough estimates.
  Sportsbooks also price same-game parlays differently from the naive product.
- Contradictory same-game legs (such as spread and moneyline on opposite teams,
  or the same player/stat twice) are excluded.
- Game picks and props come from different providers, so they are matched to the
  same game by normalized team names.

## Run the web UI

```bash
cd frontend
npm install
npm run dev
```

For local browser development, Vite proxies `/api` requests to
`http://127.0.0.1:8000`. Set `VITE_API_BASE_URL` only when the backend is at a
different address.

## Build and run on Android

Install Node.js and the Android Studio SDK/NDK toolchain. Set the API base URL
to a backend address reachable from the Android device (prefer HTTPS):

```bash
cd frontend
npm install
Copy-Item .env.example .env.local
# Edit .env.local and set VITE_API_BASE_URL
npm run build
npm run cap:sync
npm run cap:open:android
```

In Android Studio, select a device or emulator and run the `app` configuration.
The emulator cannot reach a backend running on the host using `localhost`; use
an HTTPS deployment or the emulator's host-loopback address instead.

## Backfilling history

The backend persists snapshots as it refreshes current games. To catch the
history up on earlier weeks, run:

```bash
python tools/backfill_history.py --league nfl --start-week 1 --end-week 3
```

Repeat with `--league college-football` for NCAA Football. The default range is
regular-season week 1 through the league's typical max week.
Backfilling stores completed game results only; ESPN does not provide the
historical weekly team stats needed to create reliable training snapshots.

## Training the model

Requires completed games in the SQLite history database:

```bash
python tools/train_offline.py --league nfl
```

This writes `src/sports_bet_analyzer/model_weights/spread.json`, which
`predictor.py` picks up automatically. Repeat per league and bet type as data
accumulates. Training uses snapshots collected by the live service; legacy
snapshots without verified provenance are ignored.
Team snapshots record their capture time and are not overwritten by refreshes
for three days, preserving the first snapshot in that window.

When trained weights are unavailable, recommendations use current scoring
stats and FPI blended with de-vigged market prices. This cold-start estimate is
a conservative heuristic, not a calibrated model; its weights and scoring
scales should be evaluated with walk-forward historical data before relying on
its probabilities.

## Data source limitations

ESPN's API is public but unofficial and undocumented; endpoints and query
parameters may change without notice. The client logs request failures and
returns empty results so an unavailable endpoint does not crash the service.
