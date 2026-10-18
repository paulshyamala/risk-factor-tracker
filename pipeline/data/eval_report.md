# Evaluation report: LLM labels vs human gold labels

## How to read this

- **Test set:** 40 hand-labelled candidate paragraphs, held out from prompt development.
- **Only the first run is scored** (`test_v1_sonnet`). A second labelling of the same rows (`test_v1_sonnet_rep2`) is used only to show run-to-run stability.
- **Headline numbers are for the shipped pipeline:** the scored run after `apply_rules.py` enforces the codebook rule "if uncertain about novelty, label reworded" (`test_v1_sonnet_final`). Raw-vs-final is shown below.
- **Strict numbers use the frozen human labels**, even where the LLM looks right. Dispute-adjusted numbers (secondary) drop rows listed in `gold_disputes.csv`.
- Intervals are 95% Wilson score intervals; with 40 rows they are wide.

Model `claude-sonnet-5-5`, prompt v1 (hash `d119bf014e64`), codebook v1.3, gold sheet SHA-256 `b0565807cc38`.

## Raw vs final (rule applied)

The rule changed 1 test row(s): MCD_latest_035.

| metric | raw (`test_v1_sonnet`) | final (`test_v1_sonnet_final`) |
|---|---|---|
| Category accuracy | 85.0% (95% CI 70.9–92.9%) — 34/40 | 85.0% (95% CI 70.9–92.9%) — 34/40 |
| Novelty precision | 100.0% (95% CI 64.6–100.0%) — 7/7 | 100.0% (95% CI 61.0–100.0%) — 6/6 |
| Novelty recall | 100.0% (95% CI 64.6–100.0%) — 7/7 | 85.7% (95% CI 48.7–97.4%) — 6/7 |
| Novelty F1 | 1.00 | 0.92 |
| Severity exact | 64.1% (95% CI 48.4–77.3%) — 25/39 | 64.1% (95% CI 48.4–77.3%) — 25/39 |
| Severity within 1 | 97.4% (95% CI 86.8–99.5%) — 38/39 | 97.4% (95% CI 86.8–99.5%) — 38/39 |
| mentions_ai agreement | 95.0% (95% CI 83.5–98.6%) — 38/40 | 95.0% (95% CI 83.5–98.6%) — 38/40 |

## Category

| | result |
|---|---|
| Accuracy, all rows | 85.0% (95% CI 70.9–92.9%) — 34/40 |
| Accuracy, real risks only | 84.6% (95% CI 70.3–92.8%) — 33/39 |

| category | support | predicted | precision | recall | F1 |
|---|---|---|---|---|---|
| tariffs/trade | 2 | 2 | 1.00 | 1.00 | 1.00 |
| AI/tech | 4 | 4 | 1.00 | 1.00 | 1.00 |
| cyber/data privacy | 2 | 2 | 1.00 | 1.00 | 1.00 |
| credit/liquidity | 4 | 2 | 1.00 | 0.50 | 0.67 |
| regulation/legal | 9 | 8 | 0.88 | 0.78 | 0.82 |
| competition | 2 | 3 | 0.33 | 0.50 | 0.40 |
| M&A/transactions | 6 | 6 | 1.00 | 1.00 | 1.00 |
| macro | 2 | 2 | 1.00 | 1.00 | 1.00 |
| other | 8 | 10 | 0.70 | 0.88 | 0.78 |
| not_a_risk | 1 | 1 | 1.00 | 1.00 | 1.00 |

Confusion matrix (rows = human, columns = LLM):

| human \ LLM | tariffs/trade | AI/tech | cyber/data privacy | credit/liquidity | regulation/legal | competition | M&A/transactions | macro | other | not_a_risk |
|---|---|---|---|---|---|---|---|---|---|---|
| tariffs/trade | 2 | · | · | · | · | · | · | · | · | · |
| AI/tech | · | 4 | · | · | · | · | · | · | · | · |
| cyber/data privacy | · | · | 2 | · | · | · | · | · | · | · |
| credit/liquidity | · | · | · | 2 | 1 | · | · | · | 1 | · |
| regulation/legal | · | · | · | · | 7 | 1 | · | · | 1 | · |
| competition | · | · | · | · | · | 1 | · | · | 1 | · |
| M&A/transactions | · | · | · | · | · | · | 6 | · | · | · |
| macro | · | · | · | · | · | · | · | 2 | · | · |
| other | · | · | · | · | · | 1 | · | · | 7 | · |
| not_a_risk | · | · | · | · | · | · | · | · | · | 1 |

Disagreements (6):

| paragraph | human | LLM | LLM reason |
|---|---|---|---|
| CMG_latest_041 | credit/liquidity | other | Stock price volatility from missing guidance fits no specific category and restates the prior-year risk of missing market expectations. |
| ETSY_latest_013 | other | competition | Central risk is losing sellers and buyers through poor support perception, largely restating match 1 with an added note on disbursement holds. |
| MCD_latest_015 | regulation/legal | other | Intellectual property protection risk fits no specific category; the AI mention only adds an example to existing IP risks already disclosed. |
| PYPL_latest_019 | credit/liquidity | regulation/legal | Prior-year match 1 already covers crypto licensing and regulatory risk; the GENIUS Act is a new regulation added to the same exposure. |
| WEN_latest_014 | regulation/legal | competition | Nearly identical to the last sentences of prior-year match 1, with only "litigation" added; the risk is reduced demand from consumer health concerns. |
| WM_latest_024 | competition | other | Central risk is workforce attraction and retention, already disclosed in the prior-year workforce risk; the added employment-regulation compliance language is secondary. |

## Novelty (genuinely new vs reworded)

Scored on the 39 test rows the human labelled as a risk; 7 are genuinely new. Agreement is shown for completeness but is not the headline metric: always answering "reworded" scores 82%.

| method | precision | recall | F1 | agreement |
|---|---|---|---|---|
| **LLM (final)** | 100.0% (95% CI 61.0–100.0%) — 6/6 | 85.7% (95% CI 48.7–97.4%) — 6/7 | 0.92 | 97.4% (95% CI 86.8–99.5%) — 38/39 |
| Always "reworded" | n/a (0/0) | 0.0% (95% CI 0.0–35.4%) — 0/7 | – | 82.1% (95% CI 67.3–91.0%) — 32/39 |
| TF-IDF only (status = new) | 46.7% (95% CI 24.8–69.9%) — 7/15 | 100.0% (95% CI 64.6–100.0%) — 7/7 | 0.64 | 79.5% (95% CI 64.5–89.2%) — 31/39 |

LLM confusion: TP 6, FP 0, FN 1, TN 32.

False negatives:

| paragraph | TF-IDF | best_sim | LLM uncertain | LLM reason |
|---|---|---|---|---|
| MCD_latest_035 | new | 0.181 | True | Central risk is the company's own AI tools underperforming and creating operational, data integrity and algorithmic risks, with added AI-specific regulatory and ethics exposure beyond the prior year's brief AI mention. |

## Severity

Rows where both human and LLM gave a severity: 39.

| | result |
|---|---|
| Exact agreement | 64.1% (95% CI 48.4–77.3%) — 25/39 |
| Within one level | 97.4% (95% CI 86.8–99.5%) — 38/39 |
| LLM rated higher / lower than human | 5 / 9 |

| human \ LLM | 1 | 2 | 3 |
|---|---|---|---|
| 1 | 5 | 5 | 0 |
| 2 | 3 | 17 | 0 |
| 3 | 1 | 5 | 3 |

## AI mentions (`mentions_ai`)

All 40 rows; TRUE is the positive class.

| | result |
|---|---|
| Agreement | 95.0% (95% CI 83.5–98.6%) — 38/40 |
| Precision | 80.0% (95% CI 37.6–96.4%) — 4/5 |
| Recall | 80.0% (95% CI 37.6–96.4%) — 4/5 |

TP 4, FP 1, FN 1, TN 34.

## Quote check

Share of LLM proof quotes found verbatim in the paragraph (after normalising whitespace, quotes and dashes): 100.0% (95% CI 91.2–100.0%) — 40/40.

## Top 5 cases

Chosen during error review to show distinct failure types.

**1. PYPL_latest_019 — category** (human `credit/liquidity`, LLM `regulation/legal`; verdict: human label debatable)

Text is entirely about crypto regulation, licensing (NYDFS) and the GENIUS Act, which is regulation/legal by definition; nothing in it concerns funding or liquidity.

> Our customer cryptocurrency offerings may subject us to additional regulations, licensing requirements, or other obligations or liabilities.

**2. WEN_latest_014 — category** (human `regulation/legal`, LLM `competition`; verdict: genuinely ambiguous)

Text names 'consumer or regulatory concerns or litigation' as joint causes of lower demand; the human chose the regulatory cause and the LLM the consumer-preference cause (competition), and the codebook's dominant-risk rule doesn't settle it.

> The Wendy’s system may also be adversely impacted by consumer or regulatory concerns or litigation regarding the nutritional aspects of the products we sell, the ingredients in our products or the cooking processes or packaging used in our restaurants.

**3. MCD_latest_015 — mentions_ai** (human `FALSE`, LLM `TRUE`; verdict: human label debatable)

Text explicitly says 'artificial intelligence (AI)-driven tools'; codebook 6 counts any explicit AI mention as true.

> Moreover, rapid technological developments, including artificial intelligence (AI)-driven tools, may increase our exposure to existing intellectual property risks, including theft or unlicensed use, intellectual property disputes and enforcement challenges.

**4. MCD_latest_035 — novelty (stability)** (human `genuinely_new`, LLM `scored run: genuinely_new; repeat run: reworded (both novelty_uncertain = true)`; verdict: genuinely ambiguous)

There is a brief sentence about AI but it's not the whole risk. The main risk in the latest year is AI, whle the main risk in the prior year is not.

> In addition, the artificial intelligence tools we are incorporating into certain aspects of our business may not generate the intended efficiencies and may impact our business results. → current: In addition, the AI tools we are incorporating into certain aspects of our business may not generate the intended efficiencies, may increase our exposure to risks (both known and unknown), and could adversely impact our business results.

**5. QSR_latest_017 — severity** (human `3`, LLM `2`; verdict: llm wrong)

Names the Carrols Acquisition and quantifies its effect (about 5% of restaurants now company-operated), meeting codebook 5's tests for severity 3.

> As of the date of this Annual Report on Form 10-K, we directly operated approximately 5% of our total restaurants, primarily as a result of the Carrols Acquisition in May 2024.

## Dispute-adjusted (secondary)

Rows excluded per field: category 1, novelty 0, severity 0, mentions_ai 1.

Test rows added to `gold_disputes.csv` **after scoring** (during error review): PYPL_latest_019 (category), MCD_latest_015 (mentions_ai). The strict numbers above are unaffected.

| metric | strict | dispute-adjusted |
|---|---|---|
| Category accuracy | 85.0% (95% CI 70.9–92.9%) — 34/40 | 87.2% (95% CI 73.3–94.4%) — 34/39 |
| Novelty precision | 100.0% (95% CI 61.0–100.0%) — 6/6 | 100.0% (95% CI 61.0–100.0%) — 6/6 |
| Novelty recall | 85.7% (95% CI 48.7–97.4%) — 6/7 | 85.7% (95% CI 48.7–97.4%) — 6/7 |
| Severity exact | 64.1% (95% CI 48.4–77.3%) — 25/39 | 64.1% (95% CI 48.4–77.3%) — 25/39 |
| mentions_ai agreement | 95.0% (95% CI 83.5–98.6%) — 38/40 | 97.4% (95% CI 86.8–99.5%) — 38/39 |

## Stability (run-to-run)

Agreement between `test_v1_sonnet_final` and `test_v1_sonnet_rep2_final` on the same 40 rows:

| field | agreement |
|---|---|
| category | 92.5% (95% CI 80.1–97.4%) — 37/40 |
| novelty | 97.5% (95% CI 87.1–99.6%) — 39/40 |
| severity | 85.0% (95% CI 70.9–92.9%) — 34/40 |
| mentions_ai | 100.0% (95% CI 91.2–100.0%) — 40/40 |

Novelty on the repeat run against the human labels (stability check, not a score): precision 100.0% (95% CI 61.0–100.0%) — 6/6, recall 85.7% (95% CI 48.7–97.4%) — 6/7.
