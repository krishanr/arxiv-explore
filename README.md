# arXiv Explorer

An interactive site showing the most-cited arXiv preprints in every category, year by year.

- **Treemap** of arXiv groups and categories, sized by number of papers. Click to zoom in or select.
- **Dot chart** of the top 3 most-cited papers first posted in each year, for the selected category, group, or all of arXiv.
- **Paper panel** with authors, abstract, and links to arXiv, NASA ADS, and Connected Papers.
- **Search** across categories and paper titles. The URL saves the current view, so links can be shared.

Citation counts come from the [NASA Astrophysics Data System](https://ui.adsabs.harvard.edu/) (ADS), which indexes all of arXiv
and tags papers with their arXiv categories. The data refreshes weekly.

## Layout

```
app.py                 Dash app (reads data/ at startup)
pipeline/ads.py        ADS API client and query building
pipeline/fetch.py      weekly refresh: top papers per (category, year)
pipeline/taxonomy.py   scrape arXiv's category names (run rarely)
data/                  generated data, committed to git
tests/                 pytest tests for the pipeline
```

## Local development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python app.py            # http://127.0.0.1:8050
uv run pytest && uv run ruff check .
```

### Refreshing data

Get a free ADS token at https://ui.adsabs.harvard.edu/user/settings/token and put it in `.env`:

```
ADS_API_TOKEN=...
```

Then:

```bash
uv run python -m pipeline.fetch                  # refresh what's stale
uv run python -m pipeline.fetch --max-queries 50 # small test run
uv run python -m pipeline.taxonomy               # only if arXiv adds/renames categories
```

ADS allows about 5,000 queries a day, and a full refresh needs about the same. Each run therefore refreshes the most
stale (category, year) pairs and stops before the limit: recent years after a week, older years after a month.
Progress is saved as it goes, so re-running just picks up where it left off.

**How papers are matched to years:** ADS's `year` field is the *journal* year, so the pipeline matches on the arXiv
identifier instead (`2017arXiv*` for new-style IDs, `arXiv:hep-th/03*` etc. for pre-2007 ones). A paper's year is
therefore the year it was first posted to arXiv.

## Deploying to Fly.io

One-time setup:

```bash
curl -L https://fly.io/install.sh | sh   # install flyctl
fly auth signup                          # or: fly auth login
fly launch --no-deploy                   # uses fly.toml; pick a unique app name if asked
fly deploy                               # build and deploy; prints the *.fly.dev URL
```

The app scales to zero when idle, so the first visit after a quiet spell takes a few seconds. For always-on, set
`min_machines_running = 1` in `fly.toml`, at a cost of a few dollars a month.

### Custom domain

1. Buy a domain, e.g. at Cloudflare Registrar or Porkbun (both sell at cost).
2. `fly certs add yourdomain.com` (and `fly certs add www.yourdomain.com`).
3. `fly ips list`, then at your registrar add an **A** record (IPv4) and an **AAAA** record (IPv6) for `@`, plus a
   **CNAME** `www` → `<app-name>.fly.dev`. On Cloudflare, set these to "DNS only" (grey cloud) so Fly can issue the
   certificate.
4. `fly certs check yourdomain.com` until it shows as issued.

### Automatic weekly refresh

`.github/workflows/refresh-and-deploy.yml` runs every Monday. It also runs on pushes to `main`, and from the
"Run workflow" button in GitHub's Actions tab. It lints, tests, refreshes the data, commits it, and deploys. In the
GitHub repo, open **Settings → Secrets and variables → Actions** and add:

- `ADS_API_TOKEN`: your ADS token
- `FLY_API_TOKEN`: output of `fly tokens create deploy`

## History

Version 1 (commit `07ac9c5`) was a Dash app on Heroku. It used a one-time April 2020 snapshot of arXiv's internal
citation data, building on [this Kaggle notebook](https://www.kaggle.com/steubk/arxiv-taxonomy-e-top-influential-papers).
