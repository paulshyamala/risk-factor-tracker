# Findings

Comparing the two most recent annual reports (Form 10-K, "Risk Factors" section) of 25 companies in rail, restaurants, waste, apparel and e-commerce/payments.

**1. Most of what companies say about risk is copied forward from last year.**
80% of this year's risk paragraphs are close matches for a paragraph in last year's report. Of the 351 paragraphs that did change, Claude judged 54 (15%) to describe a genuinely new risk rather than a rewording of an old one. Those 54 come from 15 of the 25 companies.

Source: `pipeline/data/paragraphs.csv`, latest-year paragraphs with TF-IDF status `kept` (1,408 of 1,759). `pipeline/data/llm_labels_all_v1_sonnet_final.csv`, rows with `novelty == genuinely_new` (54 of 351), after the codebook's "if uncertain, label reworded" rule is applied.

**2. The largest source of new risks is mergers and deals, mostly one merger.**
30 of the 54 new risks are about mergers, acquisitions or divestitures. 26 of those come from Union Pacific (18) and Norfolk Southern (8) describing their planned merger; the rest are Etsy's sale of Depop (3) and one at Yum! Brands.

Source: `pipeline/data/llm_labels_all_v1_sonnet_final.csv`, rows with `novelty == genuinely_new` and `category == M&A/transactions`, counted by ticker.

**3. Tariffs did not appear as a new risk heading, but tariff language was added inside existing risks at 15 of 25 companies.**
No company added a paragraph whose main subject is a new tariff risk; every tariff-focused paragraph that changed was judged a rewording of last year's (one Starbucks paragraph was borderline and was resolved as a rewording under the 'if uncertain, label reworded' rule). But a sentence-by-sentence comparison finds 59 new sentences mentioning tariffs, spread across 15 companies. Some sit inside paragraphs that otherwise did not change. Union Pacific, for example, added five tariff sentences to its paragraph on government regulation, including that tariffs "adversely affected demand for our services and increased our costs" in fiscal 2025.

Source: no tariff paragraph labelled new: `llm_labels_all_v1_sonnet_final.csv`, `novelty == genuinely_new` and `category == tariffs/trade` (0 rows). New tariff sentences: `pipeline/data/added_sentences.csv` and `added_by_ticker.csv`, column `tariff_theme_new`. That is a latest-year sentence with no prior-year sentence scoring 85 or more (rapidfuzz ratio), that mentions a tariff term, and whose closest prior-year sentence does not. Union Pacific example: `added_sentences.csv`, `paragraph_id == UNP_latest_012` (5 rows).

**4. AI shows up both as a new risk and inside old ones.**
9 companies wrote a genuinely new risk paragraph that mentions AI. Counting individual sentences, 19 of the 25 companies added at least one new sentence about AI, often a phrase like "including artificial intelligence" added to an existing risk about technology, privacy or regulation.

Source: `llm_labels_all_v1_sonnet_final.csv`, tickers with `novelty == genuinely_new` and `mentions_ai == True` (9). `added_by_ticker.csv`, tickers with `ai_theme_new > 0` (19).

**5. The AI labelling held up against hand-checked answers.**
On 40 paragraphs labelled by hand and kept aside for testing, Claude found 6 of the 7 genuinely new risks and raised no false alarms (6 of 6 of its "new" calls were right). Using the text-similarity screen alone would have flagged 15 paragraphs to catch those 7, so fewer than half its flags (47%) were new. Every one of Claude's 40 supporting quotes appears word for word in the filing.

Source: `pipeline/data/eval_results.json`, `final.novelty.llm` (precision 6/6, recall 6/7), `final.novelty.baselines.tfidf_only` (precision 7/15), `final.quote` (40/40). Full report: `pipeline/data/eval_report.md`.

## Caveats

- **Small, narrow sample.** 25 companies and one pair of years (latest vs prior 10-K). The findings describe these filings, not companies in general.
- **The test set is small.** With only 7 genuinely new risks in the 40 test paragraphs, the 95% confidence interval for recall runs from about 49% to 97%.
- **Sentence-level counts are not formally evaluated.** The new-tariff and new-AI sentence counts (findings 3 and 4) use no AI model. They were checked by reading random samples, not against a hand-labelled answer set.
- **"New tariff sentence" means a new sentence that mentions tariffs, not a company's first-ever tariff disclosure.** Several of these companies already discussed tariffs last year; the count shows where that language grew.
- **No link to stock returns.** Across the 25 companies, how much the Risk Factors changed showed no detectable relationship with the stock's return relative to the S&P 500 (SPY) over the 60 trading days after filing (Spearman ρ = 0.23, p = 0.27, n = 25). Source: `pipeline/data/returns.csv`.
