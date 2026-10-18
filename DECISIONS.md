# Methodology Decisions

A running log of methodology decisions for the Risk-Factor Change Tracker. Each entry states the decision and the one-line reason behind it.

## Data / extraction

- **2026-10-14** — Universe: 25 companies (5 Canadian 10-K filers + 20 US peers), two most recent 10-Ks each, 10-K/As excluded. Reason: one clean year-over-year pair per company.
- **2026-10-14** — `pair_position` (`latest`/`prior`) is used instead of fiscal-year labels. Reason: GAP, LULU, NKE, UAA and VFC label fiscal years differently; only "this filing vs last filing" matters.
- **2026-10-14** — SHOP uses the fallback extraction (slice from "Item 1A" to the next Item 1B/1C/2 heading at line start). Reason: edgartools returned no Item 1A for Shopify.
- **2026-10-14** — Cleaning removes page footers (repeated short lines, page numbers, "Table of Contents", NSC-style "K11" labels) and rejoins sentences split by page breaks. Reason: page breaks create fake paragraph splits and year-specific footers create fake changes.
- **2026-10-14** — Page-break rejoin also merges when the previous block is >= 200 chars without terminal punctuation, regardless of the next block's case. Reason: page breaks before capitalised words (e.g. 'Amazon in the U.S.') left mid-sentence fragments that registered as false changes. Gold sample regenerated after this fix, before any labelling.
- **2026-10-14** — Guards on that rule: it never merges a bullet onto the previous list item, zero-width/direction marks are ignored when checking for terminal punctuation, and "p.8"-style page numbers count as footers. Reason: without them the rule glued "...; and" list items together (18 cases), merged two WCN paragraphs whose full stop was followed by an invisible U+200E mark, and pulled CSX's "CSX 2025 Form 10-K p.8" footer into a sentence.

## Paragraph grouping ("risk units")

- **2026-10-14** — Text is grouped into risk units instead of filtering by length: a 1–2 sentence headline (< 400 chars, ends in ".") is prepended to the block after it; bullets, lowercase-start blocks and "(ii)"-style items attach to the preceding unit; section headings are stored in `section`, not kept as text. Units under 200 chars are dropped, except lone headlines of 60+ chars. Reason: a plain 200-char filter dropped ~3,000 pieces, including most risk headlines, the clearest statement of each risk.
- **2026-10-14** — Risk Factors Summary sections are excluded. Reason: they repeat the headlines from the body and would double-count risks. SBUX's prior filing has a summary and its latest doesn't, so excluding it also stops an artificial length drop.
- **2026-10-14** — "Item 1A" title blocks are skipped. Reason: they are titles, not risks, and the two-sentence headline rule was attaching them as headlines to intro paragraphs.
- **2026-10-14** — Known quirks, accepted: AMZN uses title-case headlines, which land in `section` (and one 157-char headline is dropped in both years); CP and UNP put headlines inline in the paragraph text; some short body paragraphs are merged with the next paragraph by the 2-sentence headline rule. Reason: each affects both years equally, so the diff is not biased.

## Scoring

- **2026-10-14** — ChangeScore = 1 − cosine similarity of TF-IDF vectors of the latest vs prior filing (joined risk units), with the vectorizer fit on all 50 documents. Reason: transparent, no AI involved in the core metric.
- **2026-10-14** — Paragraph status thresholds: kept ≥ 0.80, modified 0.50–0.80, new < 0.50; prior units with no match ≥ 0.50 are "deleted". Status: initial values, to be confirmed by the eyeball check.
- **2026-10-14** — Thresholds confirmed at KEPT_T = 0.80, NEW_T = 0.50 after the eyeball check. Of 9 "new" examples from the top 3 changers, 4 were genuinely new and 5 were rewrites or split paragraphs. Lowering NEW_T would not separate the two, because both score low. Reason for keeping: TF-IDF status is used only for candidate retrieval; genuine novelty is decided by the novelty label (human, then LLM).
- **2026-10-14** — LLM candidate set = "new" + "modified" units (best_sim < 0.80). Reason: companies often add new risk language inside existing paragraphs (e.g., NKE has 0 "new" units), which shows up as "modified"; labelling only "new" units would miss those risks.
- **2026-10-14** — Sampled kept units at 0.80–0.85 were near-identical paragraphs, confirming the kept cutoff.
- **2026-10-14** — Deleted-paragraph analysis deferred: most "deleted" units in SBUX and EBAY are old versions of rewritten risks, not risks that were dropped. To revisit after LLM labelling.
- **2026-10-14** — The gold sample hides TF-IDF status and similarity scores from the labeller. Reason: avoid anchoring the novelty judgment.

## Gold set

- **2026-10-15** — Codebook v1.3 adds `M&A/transactions`. Reason: after labelling, most genuinely new risks in "other" were about specific deals (UNP–NSC merger, Dickies and Depop divestitures); leaving them in "other" would hide the largest new-risk theme. Added before any LLM labelling; affected "other" rows remapped (6 rows: UNP_latest_022, UNP_latest_034, NSC_latest_006, VFC_latest_029, ETSY_latest_088, QSR_latest_017).
- **2026-10-15** — Codebook v1.3 adds "Labelling notes" (§10) recording rules applied during gold labelling. Reason: the LLM receives the same guidance the labeller used.
- **2026-10-15** — Gold split re-drawn, stratified by human novelty (seed 42; dev gets round(20 × 11/60) = 4 of the 11 genuinely new rows). Reason: the original random split put 1 of 10 genuinely new rows in dev, leaving no signal for tuning the novelty judgment. Re-drawn before any LLM output existed.
- **2026-10-15** — First measurement of TF-IDF vs human novelty (60 gold rows): 11 of 22 TF-IDF "new" rows and 0 of 38 "modified" rows were judged genuinely new. Mean best_sim is 0.169 for genuinely_new vs 0.606 for reworded.

## LLM labelling

- **2026-10-15** — claude-haiku-5-5 rejects any temperature other than the default, so temperature is not set (logged as "api_default"). Output is constrained by a forced tool call with enum-only fields. Run-to-run stability is measured by labelling the dev set twice.
- **2026-10-15** — Gold labels stay frozen after LLM outputs are seen, even where the LLM looks right. Disputed cases are recorded in the evaluation rather than changing the answer key.
- **2026-10-15** — Model: claude-sonnet-5-5. Reason: on the 20 dev rows, Haiku found 0 of 4 genuinely new risks (1 on a rerun) and changed category on 3 rows between runs; Sonnet found 3 of 4 with higher category agreement (18/20 vs 14/20). Projected full-run cost ≈ $4 vs ≈ $0.19. Novelty recall is the project's main output, so it decides the model.
- **2026-10-15** — Novelty agreement is not used as a headline metric: labelling every row "reworded" scores 16/20 on dev. Genuinely-new recall and precision are reported instead.
- **2026-10-15** — Prompt v2 adds one severity calibration line. Reason: Sonnet v1 rated 5 human severity-2 rows as 1. Only one change was made, to limit overfitting on a 20-row dev set.
- **2026-10-15** — Rows where both models disagreed with the human label in the same way are recorded in gold_disputes.csv; the gold labels are not changed.
- **2026-10-15** — Prompt v2 (severity calibration line) made no measurable difference on dev (severity 11/20 in both; row-level changes looked like run-to-run noise). Reverted to v1, the simpler prompt that adds nothing beyond the codebook. Prompt frozen at v1 from here.
- **2026-10-15** — The test set is labelled twice. Only the first run (test_v1_sonnet) is scored; the second (test_v1_sonnet_rep2) is used only to measure run-to-run stability.
- **2026-10-15** — MAX_TOKENS raised from 800 to 1500 after EBAY_latest_010 hit the output limit twice (very long supporting sentence). Setting change only; prompt v1 unchanged (same prompt_hash). Only that row was re-run.

## Evaluation

- **2026-10-18** — The codebook rule "if uncertain about novelty, label reworded" is enforced in code after labelling (apply_rules.py), because the model sometimes returned genuinely_new while flagging itself uncertain. Raw outputs are kept; published counts and the headline evaluation use the rule-applied version.
- **2026-10-18** — The headline evaluation is strict, against the frozen gold labels. Test rows judged human_label_debatable during error review were added to gold_disputes.csv after scoring; they affect only the secondary dispute-adjusted numbers.

## Sentence-level additions

- **2026-10-18** — Blind spot found: paragraph-level TF-IDF similarity hides sentences inserted into otherwise unchanged paragraphs. "Kept" paragraphs (similarity >= 0.80) were never sent to the LLM. A tariff sanity check found tariff language rising sharply while no genuinely new tariff paragraphs were labelled. Example: UNP_latest_012 (kept, 0.821) appended five tariff sentences, including that tariffs adversely affected demand and costs in fiscal 2025.
- **2026-10-18** — Method: every latest-year sentence is compared with every prior-year sentence of the same ticker (rapidfuzz ratio, lowercased). A sentence is "added" if its best match is below 85. Threshold checks showed 85 cannot fully separate rewording from additions, so theme counts use a stricter rule: an added sentence counts as a new tariff (or AI) mention only if its best prior match contains no tariff (or AI) term.
- **2026-10-18** — Reporting: paragraph-level novelty (LLM) and sentence-level theme additions are reported side by side as complementary measures. The sentence-level measure uses no LLM and has no gold-set evaluation; it is validated by manual spot-checks only.
