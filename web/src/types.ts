// Data contract for the JSON files in public/data/, written by pipeline/src/06_export.py.
// See ../DATA_SCHEMA.md for what each file powers and how each field is computed.

/** The nine codebook labels: eight risk categories plus not_a_risk (codebook.md §2, §7). */
export type Category =
  | 'tariffs/trade'
  | 'AI/tech'
  | 'cyber/data privacy'
  | 'credit/liquidity'
  | 'regulation/legal'
  | 'competition'
  | 'macro'
  | 'other'
  | 'not_a_risk'

/** null for not_a_risk paragraphs, where novelty does not apply. */
export type Novelty = 'genuinely_new' | 'reworded' | null

export type Severity = 1 | 2 | 3

export type Industry = 'Rail' | 'Restaurants' | 'Waste' | 'Apparel' | 'E-commerce/payments'

/** TF-IDF status of a latest-year unit; only these two are LLM candidates. */
export type TfidfStatus = 'new' | 'modified'

/**
 * Every file carries `mock`. It is true for the hand-made placeholder files and false for
 * pipeline output, so the site can show a "mock data" banner.
 */
interface FileFlag {
  mock: boolean
}

/** Array files are wrapped so they can carry the flag too: { mock, data: [...] }. */
export interface ListFile<T> extends FileFlag {
  data: T[]
}

// ---------- summary.json ----------

export interface Spotlight {
  ticker: string
  name: string
  /** 2–3 sentences. */
  summary: string
  memo_url: string
}

export interface Summary extends FileFlag {
  /** ISO 8601 timestamp of the export run. */
  generated_at: string
  /** Claude model id used for labelling. */
  model: string
  codebook_version: string
  n_companies: number
  n_units_latest: number
  /** Share of latest units with TF-IDF status "kept" (0–1). */
  pct_kept: number
  /** Latest units sent to the LLM (TF-IDF status new or modified). */
  n_candidates: number
  /** Candidates the LLM labelled genuinely_new. */
  n_genuinely_new: number
  n_companies_added_tariff_risk: number
  n_companies_added_ai_risk: number
  /** Category accuracy on the 40-paragraph test set (0–1). */
  llm_accuracy_test: number
  /** Share of LLM labels whose proof quote appears verbatim in the paragraph (0–1). */
  quote_valid_rate: number
  /** 3–5 sentences. */
  headline_findings: string[]
  spotlight: Spotlight
}

// ---------- companies.json ----------

export interface Company {
  ticker: string
  name: string
  industry: Industry
  is_canadian: boolean
  /** YYYY-MM-DD */
  latest_filing_date: string
  /** YYYY-MM-DD */
  prior_filing_date: string
  /** 1 − cosine similarity of latest vs prior Risk Factors (0–1). */
  change_score: number
  /** 1 = highest change_score. */
  rank: number
  n_latest: number
  n_prior: number
  n_new: number
  n_modified: number
  n_kept: number
  n_deleted: number
  n_genuinely_new: number
  /** Genuinely new risks only, by category. All nine keys are present. */
  category_counts: Record<Category, number>
}

export type CompaniesFile = ListFile<Company>

// ---------- risks.json ----------

export interface Risk {
  paragraph_id: string
  ticker: string
  section: string | null
  headline: string | null
  /** First ~600 chars of the unit text. */
  text_excerpt: string
  category: Category
  novelty: Novelty
  severity: Severity | null
  mentions_ai: boolean
  /** Sentence the LLM quoted as evidence. */
  proof: string
  /** Whether proof appears verbatim in the paragraph. */
  quote_valid: boolean
  tfidf_status: TfidfStatus
  /** Best cosine similarity to any prior-year unit (0–1). */
  best_sim: number
  /** First ~300 chars of the most similar prior-year unit. */
  prior_match_excerpt: string
}

export type RisksFile = ListFile<Risk>

// ---------- eval.json ----------

export interface CategoryMetrics {
  category: Category
  /** null when the LLM never predicted this category. */
  precision: number | null
  /** null when the category has no human-labelled examples. */
  recall: number | null
  f1: number | null
  /** Number of human-labelled test examples in this category. */
  support: number
}

export interface Confusion {
  /** Row and column order; rows = human label, columns = LLM label. */
  labels: Category[]
  matrix: number[][]
}

export interface EvalFailure {
  paragraph_id: string
  ticker: string
  text_excerpt: string
  human_label: Category
  llm_label: Category
  why: string
}

export interface Eval extends FileFlag {
  n_test: number
  /** Category accuracy over all test paragraphs, including not_a_risk. */
  accuracy: number
  /** Category accuracy over paragraphs whose human label is not not_a_risk. */
  accuracy_risks_only: number
  per_category: CategoryMetrics[]
  confusion: Confusion
  novelty_accuracy: number
  severity_exact: number
  severity_within_1: number
  quote_valid_rate: number
  /** Share of TF-IDF candidates that humans judged genuinely_new. */
  tfidf_new_genuine_rate: number
  failures: EvalFailure[]
}

// ---------- returns.json ----------

export interface ReturnPoint {
  ticker: string
  change_score: number
  /** 60-trading-day abnormal return after the latest filing, as a decimal (0.05 = +5%). */
  abnormal_return_60d: number
  /** YYYY-MM-DD, latest filing. */
  filing_date: string
}

export type ReturnsFile = ListFile<ReturnPoint>
