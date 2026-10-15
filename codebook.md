# Risk-Factor Change Tracker — Annotation Codebook

**Version:** 1.3\
**Last updated:** 2026-10-15
**Purpose:** Consistent human and LLM labelling of candidate new risk-factor paragraphs in SEC Form 10-K filings.

## 1. Annotation Principles

1. Label the central risk described in the paragraph, not every risk mentioned.
2. Classify the underlying cause of the risk rather than its downstream consequence.
3. Use evidence from the filing. Do not infer facts the company does not disclose.
4. Assign one primary category per paragraph, using the definitions and tie-break rules below.
5. Distinguish category, novelty, severity, and AI presence. These are separate fields.
6. Apply the same rules to human and LLM annotations.
7. Use `not_a_risk` for paragraphs that do not disclose an identifiable risk, including headings, introductions, cross-references, and purely descriptive text.
8. Use `other` only when a genuine business risk exists but none of the eight specific risk categories applies.

## 2. Risk Categories

### 2.1 `tariffs/trade`

**Definition:** Risks arising from government trade policies or restrictions affecting the company's operations, costs, sales, or supply chains.

**Includes:**

* Import tariffs, customs duties, and retaliatory trade measures.

* Export controls, trade sanctions, and restrictions on cross-border commerce.

* Trade-agreement changes affecting market access or sourcing.

**Excludes:**

* Widespread supply-chain disruption without a specific trade-policy cause → `macro`.

* Dependence on one key supplier → `other`, unless another category is the primary risk.

* General inflation or currency movements without a direct trade-policy cause → `macro`.

**Tie-break:** If a tariff or trade restriction causes higher costs, reduced demand, or disrupted supply, classify it as `tariffs/trade`, not `macro`.

**Example:** “Changes in tariff policy regarding merchandise produced in, and raw materials sourced from, certain countries have and could continue to adversely affect our business.”

**Why:** The risk is caused by government trade policy affecting merchandise and raw-material sourcing. Therefore, the category is `tariffs/trade`, rather than `macro` or `other`.

### 2.2 `AI/tech`

**Definition:** Risks arising from artificial intelligence, automated systems, software technology, technological change, or dependence on technology.

**Includes:**

* Failure, unreliability, or misuse of AI systems.

* Failure to adopt, integrate, or maintain important technology.

* Technological obsolescence or software-system failures.

**Excludes:**

* Cyberattacks exploiting AI or other technology → `cyber/data privacy`.

* Laws regulating AI or technology → `regulation/legal`.

* Competitors gaining market share through technological advantages → `competition`.

**Tie-break:** Use `AI/tech` when the primary concern is the company's own technology, its implementation, or technological reliability. Use `competition` when the central concern is losing customers or market share to a rival.

**Example:** “Moreover, because some AI technologies are relatively new, such as generative AI, many of the potential risks regarding their use are currently unknown.”

**Why:** The central concern is uncertainty about the reliability and risks of adopting emerging AI technology. This fits `AI/tech` because it concerns the technology itself, rather than a specific cyberattack or a law regulating AI.

### 2.3 `cyber/data privacy`

**Definition:** Risks involving unauthorized access, cyberattacks, information-security failures, data breaches, or improper collection, use, or disclosure of data.

**Includes:**

* Ransomware, phishing, hacking, and other cyber intrusions.

* Exposure, theft, loss, or misuse of customer or employee information.

* Security failures involving vendors, cloud services, or third-party systems.

**Excludes:**

* General software failures without a security or privacy dimension → `AI/tech`.

* Privacy legislation or data-protection compliance as the primary risk → `regulation/legal`.

* AI reliability or implementation risks unrelated to security or privacy → `AI/tech`.

**Tie-break:** AI-enabled phishing, ransomware, or data theft is `cyber/data privacy`, regardless of the technology used.

**Example:** “Threats to information and operational technology systems associated with cybersecurity risks and cyber incidents or attacks continue to grow.”

**Why:** The paragraph concerns threats to information systems and operational technology arising from cyber incidents. This fits `cyber/data privacy` because the primary risk is unauthorized access, disruption, or compromise of systems—not ordinary technology failure.

### 2.4 `credit/liquidity`

**Definition:** Risks involving the company's ability to meet financial obligations, obtain funding, maintain liquidity, or collect amounts owed to it.

**Includes:**

* Debt maturities, refinancing risk, leverage, and covenant breaches.

* Cash-flow shortfalls or inability to access credit and capital markets.

* Customer defaults, counterparty credit losses, and delayed receivables.

**Excludes:**

* Broad interest-rate changes affecting the economy → `macro`.

* Legal penalties or regulatory fines as the primary risk → `regulation/legal`.

* Operating losses without a specific financing, liquidity, or credit exposure → the relevant underlying category or `other`.

**Tie-break:** Interest-rate changes affecting the company's own debt are `credit/liquidity` when the paragraph focuses on debt servicing, refinancing, or funding access. Broader economic effects are `macro`.

**Example:** “Furthermore, if we determine the need for additional short-term liquidity, there is no assurance that such financing, if pursued and obtained, would be adequate or on terms acceptable to us.”

**Why:** The risk is the company’s ability to secure sufficient short-term funding on acceptable terms. This fits `credit/liquidity`, rather than `macro`, because the focus is on the company’s own financing access.

### 2.5 `regulation/legal`

**Definition:** Risks arising from laws, regulations, government investigations, litigation, legal liabilities, or compliance obligations.

**Includes:**

* Lawsuits, class actions, investigations, and enforcement actions.

* Changes in legislation, licensing rules, or industry-specific regulations.

* Potential fines, penalties, or liability for noncompliance.

**Excludes:**

* Tariffs and trade restrictions as the primary cause → `tariffs/trade`.

* Cyber incidents where the incident itself is the central risk → `cyber/data privacy`.

* Ordinary competitive pressure without a legal or regulatory cause → `competition`.

**Tie-break:** Data privacy laws, AI legislation, minimum-wage laws, labour laws, climate disclosure requirements, and carbon taxes are `regulation/legal` when compliance or enforcement is the central risk.

**Example:** “We are and in the future could become the subject of governmental investigations, regulatory actions, whistleblower lawsuits and other legal proceedings.”

**Why:** The central risk is exposure to government investigations, enforcement actions, and litigation. This fits `regulation/legal` because the risk arises from legal proceedings and regulatory scrutiny.

### 2.6 `competition`

**Definition:** Risks arising from competitors, substitutes, pricing pressure, changing consumer preferences, or the company's ability to retain customers and market share.

**Includes:**

* Competitors reducing prices or introducing competing products.

* Loss of customers or market share to existing or new rivals.

* New entrants, substitutes, or shifts in consumer loyalty.

**Excludes:**

* Technological implementation or reliability problems within the company → `AI/tech`.

* Tariff-driven price disadvantages → `tariffs/trade`.

* Economy-wide reductions in consumer spending without a company-specific competitive cause → `macro`.

**Tie-break:** A rival's AI advantage is `competition` when the paragraph emphasizes market share, customer retention, or competitive position. Use `AI/tech` when the company's own technology is the central exposure.

**Example:** “The quick service restaurant (“QSR”) pizza category and the food service and food delivery markets in general are highly competitive and such competition could adversely affect our operating results.”

**Why:** The paragraph identifies competition in Domino’s core markets as the central risk to its operating results. This fits `competition`, rather than `macro`, because the concern is industry-specific competitive pressure, not an economy-wide downturn.

### 2.7 `M&A/transactions`

**Definition:** Risks arising from mergers, acquisitions, divestitures, spin-offs or separations, including deal completion, regulatory approval of the deal, integration of acquired businesses, and separation costs.

**Includes:**

* Pending merger approvals and closing conditions.

* Integration of acquired operations, systems, or workforces.

* Costs and disruption from divesting or separating a business.

**Excludes:**

* Debt raised for a deal when financing is the central risk → `credit/liquidity`.

* General regulation not specific to a transaction → `regulation/legal`.

**Tie-break:** If the risk exists only because of a specific transaction, use `M&A/transactions`.

**Example:** TBD.

### 2.8 `macro`

**Definition:** Risks arising from broad economic, financial-market, geopolitical, or environmental conditions affecting the company.

**Includes:**

* Recession, inflation, unemployment, or declining consumer spending.

* Foreign-exchange movements and broad interest-rate changes.

* Widespread supply-chain disruption, commodity-price volatility, war, or geopolitical conflict.

**Excludes:**

* Tariff-driven cost increases or trade restrictions → `tariffs/trade`.

* Company-specific borrowing or refinancing difficulties → `credit/liquidity`.

* Company-specific legal or regulatory developments → `regulation/legal`.

**Tie-break:** Use `macro` when a broad economic or geopolitical condition is the underlying cause. Use a more specific category when that category directly explains the risk, such as sanctions → `tariffs/trade`.

**Example:** “Apparel purchases are discretionary expenditures that historically have been influenced by domestic and global economic conditions.”

**Why:** The sentence identifies broad economic conditions as a driver of consumer demand. This fits `macro` because the risk arises from economy-wide conditions rather than a company-specific financing problem or a direct competitive threat.

### 2.9 `other`

**Definition:** Genuine business risks that do not fit any of the eight specific categories above.

**Includes:**

* Labour disputes, strikes, or workforce disruptions not primarily involving legal compliance.

* Physical climate events, such as floods or wildfires, that threaten facilities or operations.

**Excludes:**

* Risks that clearly fit one of the eight specific categories.

* Paragraphs without an identifiable risk → `not_a_risk`.

* Widespread economic or supply-chain conditions better classified as `macro`.

**Tie-break:** Use `other` only after considering the eight specific categories. For supply-chain risks, classify widespread disruption affecting an industry or region as `macro`; classify dependence on a particular supplier as `other`, unless a more specific cause dominates.

**Example:** “Shortages of skilled labor and/or qualified employees could impact our operations.”

**Why:** The risk concerns the availability of qualified workers and its effect on operations. This fits `other` when the central concern is workforce availability rather than compliance with labour laws or regulations, or economy-wide conditions.

## 3. General Tie-Break Rules

Apply these rules in order when a paragraph appears to fit multiple categories:

1. **Find the central risk.** Identify what could go wrong and the underlying cause described by the company.
2. **Choose the dominant risk.** Use the main claim and the most concrete supporting details, rather than assigning every category mentioned.
3. **Prefer the specific cause over a general consequence.** For example, tariff-driven inflation belongs to `tariffs/trade`, not `macro`.
4. **Use** **`other`** **only as a last resort.** If a genuine risk exists but no specific category fits, use `other`. If no identifiable risk exists, use `not_a_risk`.

## 4. Novelty Labels

Every candidate paragraph identified as new or modified by the automated matching pipeline receives one novelty label.

### `genuinely_new`

Assign when the paragraph introduces a material risk, cause, exposure, or business consequence not substantively disclosed in the previous year's Risk Factors section.

Examples:

* A newly disclosed exposure to recently imposed tariffs.

* A previously undisclosed dependence on a specific financing source.

* A materially different cyber threat creating a new exposure.

Adding one sentence to an existing paragraph does not automatically make the paragraph genuinely new. The added content must introduce a substantively new risk or materially different exposure.

### `reworded`

Assign when the paragraph substantially restates an existing risk, including when it:

* Uses different wording for the same exposure.

* Adds examples without introducing a materially different risk.

* Adds generic explanatory language or rearranges existing disclosures.

* Expands an existing risk without changing its substantive meaning.

### Comparison procedure

For each candidate new paragraph:

1. Retrieve its **three most similar paragraphs** from the previous year's Risk Factors section using TF-IDF cosine similarity.
2. Display those paragraphs as `match_1`, `match_2`, and `match_3` in the annotation sheet and include them in the LLM prompt.
3. Compare the candidate against these matches to judge whether its risk is substantively new or reworded.
4. If the three matches are insufficient to resolve the question, flag the case as uncertain for human review rather than assuming the risk is new.

The three matches are a practical comparison aid, not proof that the paragraph is new. TF-IDF can miss semantically similar text, so novelty decisions must consider the actual wording and meaning of the candidate and its retrieved matches.

### Uncertain novelty

**Rule: If uncertain, label** **`reworded`.** A paragraph is only `genuinely_new` when the evidence supports it; doubt defaults to the conservative label.

Record the doubt separately in `novelty_uncertain`:

* `true`: the three matches did not resolve the question, and `reworded` was assigned by default.

* `false`: the novelty label reflects a confident judgement.

Every risk paragraph therefore always receives a novelty label, and the rate of `novelty_uncertain = true` can be reported as a measure of how often the annotator or LLM hedged.

## 5. Severity Labels

Severity measures the specificity and apparent materiality of the disclosed risk, not the probability of occurrence or predicted stock-price impact.

### Severity 1 — Generic

Broad or boilerplate language with little company-specific detail.

**Example:** “Economic conditions could adversely affect our business.”

### Severity 2 — Specific

Identifies a concrete company exposure, dependency, or plausible consequence, without quantifying a material impact or describing a clearly significant current event.

**Example:** “Higher freight costs could reduce margins in our North American distribution network.”

### Severity 3 — Highly specific or potentially material

Quantifies exposure, identifies a significant current event, or directly connects the risk to material financial or operational consequences.

**Example:** “New tariffs could increase annual input costs by approximately \$200 million.”

### Severity rules

* Use only evidence in the paragraph.

* Do not assign severity 3 simply because a risk sounds alarming.

* Quantification supports severity 3 but is not mandatory if a concrete current event and material company-specific consequences are disclosed.

* A genuinely new risk can have severity 1.

* Severity and novelty are independent labels.

## 6. AI Presence

Every paragraph receives a separate Boolean field, `mentions_ai`.

* `true`: The paragraph explicitly mentions artificial intelligence, machine learning, generative AI, large language models, or another clearly identified AI technology or application.

* `false`: The paragraph does not explicitly mention an identifiable AI technology or application.

Do not mark generic software, automation, algorithms, or information technology as AI unless the filing provides sufficient context to identify them as AI-related.

An AI mention does not determine the primary risk category. For example:

* AI-enabled phishing → `cyber/data privacy`, `mentions_ai = true`.

* AI-system reliability → `AI/tech`, `mentions_ai = true`.

* Ordinary software outage → `AI/tech`, `mentions_ai = false`.

* A competitor's AI advantage → usually `competition`, `mentions_ai = true`.

This field allows AI-specific findings to be reported without inflating AI counts with conventional technology risks.

## 7. Non-Risk Paragraphs

Use `not_a_risk` when the text does not describe an identifiable business risk or exposure.

Examples include:

* Section headings and subheadings.

* Introductory text that only explains how risks are organized.

* Cross-references to another section without describing a risk.

* Purely descriptive company background or procedural text.

A paragraph should not receive `not_a_risk` merely because it is generic, common across companies, or unlikely to be material. If it identifies an actual potential business harm, assign the appropriate risk category and severity.

Novelty and severity are **not applicable** to `not_a_risk` paragraphs.

### Evaluation treatment

Keep `not_a_risk` as a full class in category evaluation. The LLM can err in both directions — calling a real risk `not_a_risk`, or forcing a heading into a risk category — and excluding these paragraphs would hide both errors.

* Include `not_a_risk` in the category confusion matrix and in overall category accuracy.

* Additionally report **accuracy on real risks only**: category accuracy restricted to paragraphs whose human label is not `not_a_risk`.

* Report how often `not_a_risk` occurs in the human labels as a quality-control statistic.

## 8. Annotation Output Fields

For each candidate paragraph, record:

| Field               | Allowed values or meaning                                                                                                                       |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `paragraph_id`      | Unique paragraph identifier                                                                                                                     |
| `ticker`            | Company ticker                                                                                                                                  |
| `fiscal_year`       | Filing fiscal year                                                                                                                              |
| `filing_date`       | SEC filing date                                                                                                                                 |
| `paragraph_text`    | Exact paragraph text                                                                                                                            |
| `match_1`           | Most similar prior-year paragraph                                                                                                               |
| `match_2`           | Second-most similar prior-year paragraph                                                                                                        |
| `match_3`           | Third-most similar prior-year paragraph                                                                                                         |
| `category`          | One of the ten labels, including `not_a_risk`                                                                                                   |
| `novelty`           | `genuinely_new`, `reworded`, or not applicable                                                                                                  |
| `novelty_uncertain` | `true` or `false`; `true` when `reworded` was assigned by default because the matches did not resolve novelty (not applicable for `not_a_risk`) |
| `severity`          | `1`, `2`, `3`, or not applicable                                                                                                                |
| `mentions_ai`       | `true` or `false`                                                                                                                               |
| `proof`             | *LLM only.* Exact sentence supporting the annotation                                                                                            |
| `quote_valid`       | *LLM only.* Whether `proof` appears verbatim in the paragraph                                                                                   |
| `rationale`         | Brief explanation for ambiguous human labels                                                                                                    |

## 9. Gold-Set Labelling Procedure

The gold set contains 60 randomly selected candidate paragraphs, selected with random seed `42`. Candidates are latest-year paragraphs whose TF-IDF status is new **or** modified, i.e. whose best prior-year match has cosine similarity below 0.80.

* **Development set:** 20 paragraphs, used to refine the LLM prompt.

* **Test set:** 40 paragraphs, reserved for final evaluation.

The dev/test split is stratified by human novelty (`genuinely_new` vs everything else, seed `42`), so both sets contain genuinely new risks in proportion. It was re-drawn after human labelling and before any LLM labelling.

### Sampling safeguards

* Sample only candidate paragraphs identified as new or modified by the automated matching pipeline (best match < 0.80).

* Cap the sample at approximately three paragraphs per company where feasible, so companies with long filings do not dominate the gold set.

* If a company has fewer eligible paragraphs, retain the available examples and document any resulting imbalance.

* Save the sampling seed, selected paragraph IDs, and split assignments so the sample is reproducible.

### Labelling procedure

1. Generate the sample and its prior-year matches before running the LLM classifier.
2. Hide all LLM predictions while manually labelling the 60 paragraphs.
3. Assign category, novelty, severity, and AI presence independently using this codebook.
4. Record brief rationales for ambiguous cases.
5. Freeze the human labels before inspecting LLM predictions.
6. Use the 20 development examples to improve the prompt.
7. Freeze the prompt and model configuration before evaluating the 40 test examples.
8. Evaluate the test set once. Do not tune the prompt on test errors and report the same examples as an untouched test set.

The gold set evaluates classification of candidate paragraphs selected by the matching pipeline. It does not measure the pipeline's ability to detect every genuinely new risk.

## 10. Labelling Notes

These rules were applied during gold labelling and are part of the guidance given to the LLM.

### Novelty

* Compare the candidate against each prior-year match separately. If any single match covers the same risk, label `reworded`.

* If the risk is split across two matches, label `reworded`.

* Ignore matches that are unrelated to the candidate.

* A change in status of an existing risk (e.g. a material weakness now remediated) is `reworded`, not new.

* New examples or regulations added to an existing risk without a materially different exposure are `reworded`.

### Severity

* Generic AI or ESG language with no company-specific detail → severity 1.

### Category

* Risk of failing to meet the company's own ESG/sustainability goals → `other`.

* Internal controls over financial reporting (SOX 404, material weaknesses) → `regulation/legal`.

* Tax-law exposures (e.g. withholding taxes) → `regulation/legal`.

### Scope

* All labels describe the current-year paragraph only. Prior-year matches are used only to judge novelty.
