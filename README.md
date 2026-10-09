# Sports Bet Analyzer

Suggests high-probability NFL / NCAA Football bets (spread, moneyline, totals,
player props) using only free public data from ESPN's API, with a Kivy UI that
packages into an Android APK via Buildozer.

> **Informational use only.** This tool does not place bets, guarantee
> outcomes, or constitute financial advice. Sports betting involves risk;
> bet only what you can afford to lose, and check your local laws/age
> requirements before wagering.

## How it works

- `espn_client.py` pulls scores, team stats, ESPN's own odds (`pickcenter`)
  block, and FPI power ratings from ESPN's public JSON API. Every refresh
  persists a stat snapshot for **every** team in the league (via the
  `/teams` endpoint), including teams on a bye that week - not just teams
  with a scheduled game.
- `storage.py` caches completed games/stat snapshots in a local SQLite file so
  the model can build its own in-season history (no paid historical data
  provider is used).
- `tools/train_offline.py` (desktop only) trains a small logistic-regression
  model per bet type from that history and exports the weights as JSON.
- `predictor.py` / `recommender.py` (mobile-safe, no numpy/pandas/sklearn) load
  those JSON weights and rank upcoming games by predicted probability. Until
  enough in-season history accumulates, recommendations fall back to an
  FPI-differential estimate.
- `app/main.py` is the Kivy UI: tap Refresh to fetch this week's NFL/NCAAF
  games and show bets above a confidence threshold.

## Desktop setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements-dev.txt
pytest
```

Run the app on desktop before packaging:

```bash
python -m sports_bet_analyzer.app.main
```

## Backfilling history

`app/main.py` only fetches the *current* week on each refresh, so any week you
weren't running the app during is otherwise never captured. Catch the local
history store up on earlier weeks with:

```bash
python tools/backfill_history.py --league nfl --start-week 1 --end-week 3
```

Repeat with `--league college-football` for NCAA Football. Defaults to
regular-season week 1 through the league's typical max week.

## Training the model

Requires a season's worth of completed games cached in the local SQLite DB
(the app writes to it as it fetches results):

```bash
python tools/train_offline.py --league nfl
```

This writes `src/sports_bet_analyzer/model_weights/spread.json`, which
`predictor.py` picks up automatically. Repeat per league/bet type as data
accumulates.

## Building for Android

```bash
pip install buildozer
buildozer init          # only if buildozer.spec doesn't already exist
buildozer android debug deploy run
```

The mobile app only requires `requests` and `kivy` (see `requirements.txt`) -
training dependencies (`numpy`) stay in `requirements-dev.txt` and are never
installed on-device, since scientific-Python packages are not reliably
buildable through python-for-android.

## Notes on data sources

ESPN's API is public but unofficial and undocumented; endpoints and query
parameters have changed without notice in the past. All client calls fail
soft (log + empty result) so a broken endpoint degrades gracefully instead of
crashing the app.
