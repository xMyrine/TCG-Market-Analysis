# Decision log

Newest first. Each entry: what was decided, why, and what it costs.

## 2026-10-14 — One Streamlit app, no backend or JS frontend
The dashboard imports the analysis code directly. Each question is a `Question` in
`analysis/questions.py` whose `answer(silver)` returns an `Answer` (headline, tables, chart,
caveats). Status (not started, waiting, ready) is derived from the data on every run, never
stored. Results are cached on the silver files' modification times, so a pipeline run
invalidates them and a page reload shows the new data. A REST API and a JS frontend would add two
layers to maintain for a single-user local tool. Cost: the analysis runs inside the Streamlit
process, so a slow analysis blocks that page until it finishes, and a later move to a hosted
app means writing an API then.

## 2026-10-12 — Hedonic regression with set-clustered standard errors (Q4)
Era is constant within a set, and cards in a set share demand shocks, so cards are not
independent observations. Clustering by set made SEs 4–9× larger than naive OLS and removed a
spurious "SWSH cheaper than SV" result (naive t = −8, clustered t = −0.9).

## 2026-10-12 — Product kind from extendedData; sealed is the default
The name-only rules misclassified most non-cards (see [data.md](data.md#product-kinds)).
Structured fields (`Number`, `Card Type`, `Rarity`) decide card vs not-a-card; Code Cards get
their own class. Keep `UPC`; do not keep TCGplayer's presale info (presales are identified by
set release date instead).

## 2026-10-12 — Collect prices forward from the live API
TCGCSV's archive is offline. `prices --live` saves the current snapshot per set into the same
bronze layout as archive days, dated by TCGCSV's `last-updated.txt` (not the local clock), and
aborts if TCGCSV refreshes mid-run. Cost: no history before 2026-10-11; the S&P 500 comparison
needs 6–12 months of collection. Free alternatives were reviewed: none offers multi-year daily
history for both games; Cardmarket's public price guide is the candidate second market.

## 2026-10-12 — Fail fast on HTTP 4xx
Client errors are deterministic; retrying them only adds load to a free community server.
Only timeouts, 5xx and 429 are retried.

## 2026-10-12 — One category per game
`catalog` stops if a game's regex matches several categories, so a future "Riftbound Japan"
cannot silently mix a second market into an index.
