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
