# Government catalyst tracker

Tracks federal incentive programs (CHIPS, IRA 45X, DOE loans, DPA Title III) as stock
catalysts. A daily GitHub Action pulls public feeds, scores each event by **incentive
quality × pipeline stage × materiality**, emails you anything above threshold, and
publishes a dashboard to GitHub Pages.

> Descriptive triage, not a predictive signal. The score ranks what's worth your
> attention — it does not forecast returns.

## How it works

```
feeds → normalize → resolve (recipient→ticker) → score → route → diff → email + dashboard
```

- **Feeds** (`src/feeds/`): Federal Register (NOFOs/rules, stage 2) and USAspending
  (awards with dollar amounts, stage 4). Both free public APIs, no key.
- **Scoring** (`src/score.py`): the 0–10 model. Quality tiers 1–5 (offtake/floor → R&D),
  stage multiplier, materiality = award ÷ market cap.
- **Routing** (`src/route.py`): score ≥ 7 → immediate email, 3–7 → daily digest, else log.
- **Crosswalk** (`data/crosswalk.csv`): recipient legal name → ticker + market cap.
  Hand-maintained — **grow this** as new recipients appear; matches drive materiality.

## One-time setup

1. **Create a public GitHub repo** and push this folder:
   ```sh
   git init && git add . && git commit -m "initial catalyst tracker"
   git branch -M main
   git remote add origin https://github.com/<you>/govt-catalyst-tracker.git
   git push -u origin main
   ```
2. **Gmail app password**: Google Account → Security → 2-Step Verification → App passwords.
   Generate one for "Mail".
3. **Add repo secrets** (Settings → Secrets and variables → Actions → New secret):
   - `MAIL_USERNAME` — your gmail address
   - `MAIL_APP_PASSWORD` — the app password from step 2
   - `MAIL_TO` — where digests go (can be the same gmail)
4. **Enable Pages**: Settings → Pages → Source = "GitHub Actions". After the first run the
   dashboard is live at `https://<you>.github.io/govt-catalyst-tracker/`.
   Put that URL in `DASHBOARD_URL` in `src/run.py` so emails link to it.
5. **Run it once manually**: Actions tab → `poll-catalysts` → Run workflow. Check your inbox
   and the dashboard.

The schedule (`.github/workflows/poll.yml`) then runs every morning at 11:00 UTC.

## Run locally

```sh
pip install -r requirements.txt
py src/run.py        # uses `py` on Windows; prints the digest if MAIL_* env vars are unset
```

This writes `docs/data/catalysts.json` (dashboard data) and `data/snapshot.json` (diff state).
Open `docs/index.html` in a browser to see the dashboard against local data.

## Known limitations (v1)

- **Cron is best-effort** — Actions schedules can lag 5–15 min and auto-disable after ~60
  days of repo inactivity. Fine for a daily digest; it won't beat the wires by minutes.
- **Public repo = public dashboard.** Only public data lives here — watchlist tickers and
  government awards. Never commit positions or API keys (secrets stay in repo settings).
- **Entity resolution is the bottleneck.** Most USAspending recipients won't match the seed
  crosswalk until you expand it. Market caps in the crosswalk are illustrative — update them.
- **No `surprise` factor and no dissemination/wires check yet** — both deferred from v1 to
  keep scoring deterministic.

## Extending it

- Add a feed: drop a `src/feeds/<name>.py` with a `fetch(program, lookback_days)` returning
  `base_record(...)` items, then import it in `src/run.py`.
- Add a program: append to `programs:` in `config.yml` — no code change.
- Tune routing: edit `thresholds:` in `config.yml`.
