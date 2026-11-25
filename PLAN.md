# arXiv Explorer — Rebuild Plan

Decisions from the planning interview (2026-11-25). The old Dash app (commit `07ac9c5`) used a frozen
April-2020 snapshot; this rebuild keeps the same idea but refreshes weekly and runs on a custom domain.

## Decisions

| Topic | Decision |
|---|---|
| Language / framework | Python, **Dash** (current version) + Plotly |
| Data source | **NASA ADS API**: has arXiv categories (`arxiv_class`) *and* citation counts (verified 2026-11-25) |
| Metric | For each arXiv category and year first posted to arXiv: the **top 3 most-cited papers** |
| Years | All years (1991 → present) |
| Hosting | **Fly.io** (small shared-CPU machine, ~$2–5/month) |
| Domain | Not bought yet — buy at Cloudflare or Porkbun (at-cost pricing) |
| Refresh | **Weekly**, via a free scheduled GitHub Action |
| Repo | Rewrite in place on the `rebuild` branch; the old code stays in git history |

## Features

1. **Category treemap**: arXiv group → category, sized by paper count. Click to drill down.
2. **Top-papers dot chart** (replaces the heatmap): x = publication year, y = citations (log scale), one dot per
   top paper. Hover shows the title; click selects the paper.
3. **Paper detail panel**: title, authors, year, citations, abstract, and links (arXiv abstract/PDF, ADS,
   Connected Papers via `https://www.connectedpapers.com/api/redirect/arxiv/<id>`, so no ID lookup is needed).
4. **Search + shareable URLs**: a searchable box over category names and paper titles. The selection lives in the URL
   (e.g. `/?cat=cs.LG&paper=1706.03762`) via `dcc.Location`.

## Architecture

```
GitHub Action (weekly cron)
  └─ python -m pipeline.fetch        ← queries ADS, writes data/*.json(l)
  └─ commit data if changed
  └─ flyctl deploy                   ← Docker image = app code + data files
Fly.io machine
  └─ gunicorn app:server             ← Dash app reads data files into memory at startup
```

The data is small (~158 categories × ~35 years × 3 papers ≈ 14k rows), so no database is needed. It's stored as
sorted JSON Lines rather than parquet so the weekly git diffs stay small and readable.

### Pipeline (`pipeline/`)
- `taxonomy.py`: arXiv group/category names. Scrape https://arxiv.org/category_taxonomy once and commit
  the result as `data/taxonomy.json`, re-scraping only when categories change.
- `fetch.py`:
  - **Category counts**: one `rows=0` query per category (ADS's public API doesn't support facets) → `data/categories.json`.
  - **Top papers**: for each (category, year), query
    `arxiv_class:"<cat>" <posting-year filter>`, `sort=citation_count desc`, `rows=3` → `data/top_papers.jsonl`.
    ADS's `year` is the *journal* year, so the posting year is matched via the arXiv identifier:
    `identifier:2017arXiv*` (2008+), an OR over old archive prefixes `arXiv\:hep-th/03*` (≤2006), both for 2007.
- **Staying under ADS's 5,000 requests/day limit**: a full refresh is ~4,900 queries. Each run refreshes the most
  stale pairs first (recent 5 years after 6 days, older years after 27 days) and stops when
  `X-RateLimit-Remaining` drops to 100. Progress is saved every 200 queries.
- The ADS token comes from the `ADS_API_TOKEN` env var (a GitHub secret in CI, `.env` locally — never committed).

### App (`app.py`)
- Load the parquet files at startup. All filtering is in-memory with pandas.
- Fix the old TODOs: show an empty-state message for categories with no qualifying papers, and handle
  categories that appear in two groups (e.g. Numerical Analysis in math and cs) by keying on the category ID.

### Tooling
- `uv` + `pyproject.toml` (replaces conda / requirements.txt / runtime.txt / Procfile / Makefile).
- Archive-level codes `astro-ph`, `cond-mat`, `q-bio` are added as "(general)" categories, since ADS still tags older
  papers with them (e.g. 105k astro-ph papers from before the 2009 split).
- `ruff` for lint/format, a few `pytest` tests for the pipeline's parsing and merge logic.
- `Dockerfile` + `fly.toml` for deployment.

## Milestones

Status (2026-11-25): 1–3 and 6 done; 4–5 written (Dockerfile, fly.toml, workflow) but need your Fly/GitHub accounts.

1. **Verify ADS** (do this first): get a token at https://ui.adsabs.harvard.edu/user/settings/token and run test
   queries for one physics, one math and one CS category. Check that `arxiv_class` filtering works, how CS
   citation counts compare with Semantic Scholar/Google Scholar, and the rate-limit headers. If coverage is
   poor, fall back to arXiv metadata for the categories + OpenAlex for the citations.
2. **Pipeline**: taxonomy + fetch + incremental merge, run locally to produce the data files.
3. **App**: treemap → dot chart → detail panel, then search + URL state. Run locally with `uv run python app.py`.
4. **Deploy**: `fly launch`, `fly deploy`; buy the domain; `fly certs add <domain>` and add the DNS records Fly prints.
5. **Automate**: GitHub Action with weekly cron (`ADS_API_TOKEN`, `FLY_API_TOKEN` secrets).
6. **Clean up**: remove old files (`environment.yml`, `Procfile`, `runtime.txt`, `notebooks/`, old CSVs), update the README.
