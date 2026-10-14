# Data Schema

The site reads five JSON files from `public/data/`. All five are written by `pipeline/src/06_export.py`, which gathers the outputs of the earlier pipeline steps. TypeScript types live in [`src/types.ts`](src/types.ts).

**Envelope.** Every file has a top-level `mock` boolean: `true` for the hand-made placeholder files, `false` for pipeline output. Files that hold a list wrap it as `{ "mock": …, "data": [ … ] }`. `summary.json` and `eval.json` are single objects with `mock` as one of their fields.

**Shared enums.**

| Type | Values |
|---|---|
| `Category` | `tariffs/trade`, `AI/tech`, `cyber/data privacy`, `credit/liquidity`, `regulation/legal`, `competition`, `macro`, `other`, `not_a_risk` (codebook.md §2, §7) |
| `Novelty` | `genuinely_new`, `reworded`, `null` (null for `not_a_risk`) |
| `Industry` | `Rail`, `Restaurants`, `Waste`, `Apparel`, `E-commerce/payments` |

Rates and shares are decimals from 0 to 1. Dates are `YYYY-MM-DD`.

## summary.json

**Powers:** the landing page, including the headline numbers, key findings and company spotlight.
**Produced from:** all steps; `02_diff.py` (unit counts), `03_label.py` (labels), `04_eval.py` (accuracy).

| Field | Type | Meaning |
|---|---|---|
| `generated_at` | string | ISO 8601 timestamp of the export run |
| `model` | string | Claude model id used for labelling |
| `codebook_version` | string | Version of codebook.md the labels follow |
| `n_companies` | number | Companies in the sample (25) |
| `n_units_latest` | number | Risk units in the latest filings |
| `pct_kept` | number | Share of latest units whose TF-IDF status is `kept` |
| `n_candidates` | number | Latest units with TF-IDF status `new` or `modified`, all sent to the LLM |
| `n_genuinely_new` | number | Candidates the LLM labelled `genuinely_new` |
| `n_companies_added_tariff_risk` | number | Companies with ≥ 1 genuinely new `tariffs/trade` risk |
| `n_companies_added_ai_risk` | number | Companies with ≥ 1 genuinely new risk where `mentions_ai` is true |
| `llm_accuracy_test` | number | Category accuracy on the 40-paragraph test set |
| `quote_valid_rate` | number | Share of LLM labels whose `proof` appears verbatim in the paragraph |
| `headline_findings` | string[] | 3–5 one-sentence findings |
| `spotlight.ticker` | string | Featured company |
| `spotlight.name` | string | Its display name |
| `spotlight.summary` | string | 2–3 sentences on what changed |
| `spotlight.memo_url` | string | Link to the written memo |

## companies.json

**Powers:** the company ranking table and the per-company pages.
**Produced from:** `01_fetch.py` (filing dates), `02_diff.py` (`change_scores.csv`), `03_label.py` (genuinely new counts).

| Field | Type | Meaning |
|---|---|---|
| `ticker` | string | Ticker symbol |
| `name` | string | Company display name |
| `industry` | Industry | Peer group |
| `is_canadian` | boolean | One of the five Canadian 10-K filers |
| `latest_filing_date` | string | Filing date of the latest 10-K |
| `prior_filing_date` | string | Filing date of the prior 10-K |
| `change_score` | number | 1 − cosine similarity (TF-IDF) of latest vs prior Risk Factors |
| `rank` | number | 1 = highest `change_score` |
| `n_latest` / `n_prior` | number | Risk units in each filing |
| `n_new` / `n_modified` / `n_kept` | number | Latest units by TF-IDF status (best_sim < 0.50 / 0.50–0.80 / ≥ 0.80) |
| `n_deleted` | number | Prior units with no latest match ≥ 0.50 |
| `n_genuinely_new` | number | Candidates labelled `genuinely_new` |
| `category_counts` | Record<Category, number> | Genuinely new risks by category; all nine keys present |

## risks.json

**Powers:** the risk browser, a filterable list of every labelled candidate with its evidence and prior-year match.
**Produced from:** `02_diff.py` (text, TF-IDF status and matches), `03_label.py` (LLM labels).

| Field | Type | Meaning |
|---|---|---|
| `paragraph_id` | string | `{ticker}_latest_{nnn}` |
| `ticker` | string | Ticker symbol |
| `section` | string \| null | Section heading the unit sits under |
| `headline` | string \| null | Risk headline, if detected as a separate block |
| `text_excerpt` | string | First ~600 characters of the unit |
| `category` | Category | LLM category label |
| `novelty` | Novelty | LLM novelty label |
| `severity` | 1 \| 2 \| 3 \| null | LLM severity (codebook §5); null for `not_a_risk` |
| `mentions_ai` | boolean | Explicit AI mention (codebook §6) |
| `proof` | string | Sentence the LLM quoted as evidence |
| `quote_valid` | boolean | Whether `proof` appears verbatim in the unit |
| `tfidf_status` | `"new"` \| `"modified"` | TF-IDF status that made it a candidate |
| `best_sim` | number | Best cosine similarity to any prior-year unit |
| `prior_match_excerpt` | string | First ~300 characters of the closest prior-year unit |

## eval.json

**Powers:** the methodology / evaluation page: accuracy, confusion matrix and failure examples.
**Produced from:** `04_eval.py`, comparing `gold_labels.xlsx` (human) with `llm_labels.csv` on the 40 test paragraphs.

| Field | Type | Meaning |
|---|---|---|
| `n_test` | number | Test-set size (40) |
| `accuracy` | number | Category accuracy, `not_a_risk` included as a class |
| `accuracy_risks_only` | number | Category accuracy where the human label is not `not_a_risk` |
| `per_category[]` | object[] | One row per Category: `precision`, `recall`, `f1` (null when undefined), `support` (human count) |
| `confusion.labels` | Category[] | Row/column order |
| `confusion.matrix` | number[][] | 9×9 counts; rows = human label, columns = LLM label |
| `novelty_accuracy` | number | Agreement on `novelty` |
| `severity_exact` | number | Exact severity agreement |
| `severity_within_1` | number | Severity agreement within one level |
| `quote_valid_rate` | number | Share of test-set proofs found verbatim |
| `tfidf_new_genuine_rate` | number | Share of TF-IDF candidates that humans judged `genuinely_new` |
| `failures[]` | object[] | Disagreements: `paragraph_id`, `ticker`, `text_excerpt`, `human_label`, `llm_label`, `why` |

## returns.json

**Powers:** the "does change predict returns?" scatter plot.
**Produced from:** `05_returns.py` (yfinance prices), joined with `change_score` from `02_diff.py`.

| Field | Type | Meaning |
|---|---|---|
| `ticker` | string | Ticker symbol |
| `change_score` | number | As in companies.json |
| `abnormal_return_60d` | number | 60-trading-day abnormal return after the latest filing (0.05 = +5%) |
| `filing_date` | string | Latest filing date (event date) |
