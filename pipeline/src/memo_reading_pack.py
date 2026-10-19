"""Build the UNP reading pack for the memo -> output/unp_reading_pack.md.

Sections: overview (filing dates, ChangeScore, paragraph counts), genuinely new risk paragraphs grouped by
topic, other changed paragraphs, added tariff/AI sentences (with UNP_latest_012 marked up), and MD&A
paragraphs that mention key words. The MD&A text is data/unp_mdna_latest.txt; pass --fetch-mdna to
(re)download it from UNP's latest 10-K with edgartools.

Usage: python memo_reading_pack.py [--out PATH] [--fetch-mdna]
"""
import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd

from added_sentences import split_sentences

TICKER = "UNP"
PIPELINE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PIPELINE_DIR / "data"
OUT = PIPELINE_DIR.parent / "output" / "unp_reading_pack.md"
MDNA_PATH = DATA_DIR / "unp_mdna_latest.txt"
FOCUS_PARAGRAPH = "UNP_latest_012"  # kept paragraph with appended tariff sentences

# Topics assigned by reading each genuinely new paragraph. The script checks that these ids are exactly
# the current genuinely new UNP paragraphs, so a relabel or re-run of 02_diff can't silently drop one.
TOPICS = [
    ("Merger completion and regulatory approval", ["UNP_latest_022", "UNP_latest_025", "UNP_latest_028"]),
    ("If the merger is not completed: termination fees and fallout",
     ["UNP_latest_023", "UNP_latest_024", "UNP_latest_026", "UNP_latest_027"]),
    ("While the merger is pending: restrictions, uncertainty and staff",
     ["UNP_latest_029", "UNP_latest_030", "UNP_latest_031"]),
    ("Merger-related litigation", ["UNP_latest_032"]),
    ("Integration and the combined company",
     ["UNP_latest_033", "UNP_latest_034", "UNP_latest_035", "UNP_latest_036", "UNP_latest_037", "UNP_latest_038"]),
    ("Combined-company debt and financing", ["UNP_latest_040", "UNP_latest_041", "UNP_latest_042"]),
]
MDNA_KEYWORDS = [  # (label, pattern, case-insensitive)
    ("merger", r"\bmergers?\b", True),
    ("Norfolk Southern", r"\bNorfolk Southern\b", False),
    ("tariff", r"\btariffs?\b", True),
    ("operating ratio", r"\boperating ratio\b", True),
    ("volume or carloads", r"\bvolumes?\b|\bcarloads?\b", True),
    ("guidance or outlook", r"\bguidance\b|\boutlook\b", True),
]


def fetch_mdna():
    from edgar import Company, set_identity
    set_identity("Paul Shyamala p4reddy@uwaterloo.ca")
    with sqlite3.connect(DATA_DIR / "filings.db") as conn:
        accession = conn.execute("SELECT accession_no FROM filings WHERE ticker = ? AND pair_position = 'latest'",
                                 (TICKER,)).fetchone()[0]
    filing = next(f for f in Company(TICKER).get_filings(form="10-K") if f.accession_no == accession)
    text = filing.obj().management_discussion
    if not text:
        raise SystemExit("edgartools found no Item 7 (MD&A); slice it from the full text like the Item 1A fallback")
    MDNA_PATH.write_text(text)


def is_true(series):
    return series.astype(str).str.lower() == "true"


def build():
    labels = pd.read_csv(DATA_DIR / "llm_labels_all_v1_sonnet_final.csv", dtype=str, keep_default_na=False)
    labels = labels.set_index("paragraph_id")
    paras = pd.read_csv(DATA_DIR / "paragraphs.csv", keep_default_na=False).set_index("paragraph_id")
    scores = pd.read_csv(DATA_DIR / "change_scores.csv").reset_index(drop=True)
    rank = int(scores.index[scores.ticker == TICKER][0]) + 1
    score = scores[scores.ticker == TICKER].iloc[0]
    with sqlite3.connect(DATA_DIR / "filings.db") as conn:
        dates = dict(conn.execute("SELECT pair_position, filing_date FROM filings WHERE ticker = ? "
                                  "AND pair_position IS NOT NULL", (TICKER,)).fetchall())
    added = pd.read_csv(DATA_DIR / "added_sentences.csv", keep_default_na=False)
    added_themes = added[(added.ticker == TICKER) & (is_true(added.tariff_theme_new) | is_true(added.ai_theme_new))]
    mdna = MDNA_PATH.read_text()
    mdna_paras = [p.strip() for p in re.split(r"\n\s*\n", mdna) if p.strip()]

    new_ids = set(labels[(labels.ticker == TICKER) & (labels.novelty == "genuinely_new")].index)
    assigned = [p for _, ids in TOPICS for p in ids]
    if set(assigned) != new_ids or len(assigned) != len(new_ids):
        raise SystemExit(f"TOPICS out of date: unassigned {sorted(new_ids - set(assigned))}, "
                         f"no longer new {sorted(set(assigned) - new_ids)}")

    L = [f"# Union Pacific ({TICKER}) — reading pack", "",
         "Prepared for the company memo. Sources: `pipeline/data/` (filings.db, paragraphs.csv, change_scores.csv, "
         "llm_labels_all_v1_sonnet_final.csv, added_sentences.csv) and the latest 10-K MD&A (`unp_mdna_latest.txt`).", "",
         "## Overview", "", "| | |", "|---|---|",
         f"| Latest 10-K filed | {dates['latest']} |", f"| Prior 10-K filed | {dates['prior']} |",
         f"| ChangeScore | {score.change_score:.3f} (rank {rank} of {len(scores)}) |",
         f"| Risk units: latest / prior | {int(score.n_latest)} / {int(score.n_prior)} |",
         f"| New / modified / kept / deleted | {int(score.n_new)} / {int(score.n_modified)} / {int(score.n_kept)} / {int(score.n_deleted)} |",
         f"| Genuinely new (LLM, rule applied) | {len(new_ids)} |", "",
         f"## 1. Genuinely new risk paragraphs ({len(new_ids)})", "",
         "Grouped by topic (topics assigned by reading the text). Each shows the LLM's category, severity and proof sentence.", ""]
    for topic, ids in TOPICS:
        L += [f"### {topic} ({len(ids)})", ""]
        for p in ids:
            sev = labels.at[p, "severity"]
            sev = str(int(float(sev))) if sev else "n/a"
            L += [f"**{p}** · {labels.at[p, 'category']} · severity {sev}", "",
                  f"*Proof:* \"{labels.at[p, 'proof']}\"", "", paras.at[p, "text"], ""]

    other = [p for p in labels[labels.ticker == TICKER].index if p not in new_ids]
    L += [f"## 2. Other changed paragraphs ({len(other)})", "",
          "Modified paragraphs, or new paragraphs the LLM judged a rewording.", "",
          "| paragraph | TF-IDF | category | novelty | first 300 characters |", "|---|---|---|---|---|"]
    for p in other:
        L.append(f"| {p} | {paras.at[p, 'status']} | {labels.at[p, 'category']} | {labels.at[p, 'novelty']} | "
                 + paras.at[p, "text"][:300].replace("\n", " ").replace("|", "\\|") + " |")

    L += ["", f"## 3. Added tariff and AI sentences ({len(added_themes)})", "",
          "Sentences with no prior-year sentence scoring 85+ (rapidfuzz ratio) that mention a tariff or AI term "
          "their closest prior sentence lacks (`tariff_theme_new` / `ai_theme_new`).", "",
          "| paragraph | status | theme | sentence |", "|---|---|---|---|"]
    for r in added_themes.itertuples():
        theme = "tariff" if str(r.tariff_theme_new).lower() == "true" else "AI"
        L.append(f"| {r.paragraph_id} | {r.status} | {theme} | {r.sentence} |")
    new_sentences = set(added[added.paragraph_id == FOCUS_PARAGRAPH].sentence)
    L += ["", f"### {FOCUS_PARAGRAPH} in full (TF-IDF status {paras.at[FOCUS_PARAGRAPH, 'status']}, "
              f"similarity {paras.at[FOCUS_PARAGRAPH, 'best_sim']:.3f})", "",
          "**[NEW]** marks sentences with no prior-year sentence scoring 85 or more.", ""]
    L += [f"- **[NEW]** {s}" if s in new_sentences else f"- {s}" for s in split_sentences(paras.at[FOCUS_PARAGRAPH, "text"])]

    L += ["", "## 4. MD&A context (latest 10-K, Item 7)", "",
          f"Extracted with edgartools (`management_discussion`); {len(mdna):,} characters, {len(mdna_paras)} paragraphs. "
          "Every paragraph mentioning each keyword is shown in full; a paragraph can appear under more than one keyword.", ""]
    counts = {}
    for name, pattern, ignore_case in MDNA_KEYWORDS:
        hits = [p for p in mdna_paras if re.search(pattern, p, re.I if ignore_case else 0)]
        counts[name] = len(hits)
        L += [f"### {name} ({len(hits)} paragraph{'s' if len(hits) != 1 else ''})", ""]
        L += ["*No paragraph mentions this keyword.*", ""] if not hits else [x for h in hits for x in (h, "")]
    return "\n".join(L), counts


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT, help=f"output markdown (default {OUT})")
    parser.add_argument("--fetch-mdna", action="store_true", help="re-download the MD&A text first")
    args = parser.parse_args()
    if args.fetch_mdna or not MDNA_PATH.exists():
        fetch_mdna()
    text, counts = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text)
    print(f"MD&A keyword paragraphs: {counts}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
