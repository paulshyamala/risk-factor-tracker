"""Find sentences added to each company's Risk Factors this year, at sentence level (no LLM).

Paragraph matching (02_diff.py) misses risk language added inside paragraphs that still score as
"kept" or "modified". This compares every latest-year sentence with every prior-year sentence of the
same ticker: a sentence whose best fuzzy match is below ADDED_T is "added". Added sentences are tagged
with themes (tariff, AI) and joined to their paragraph's TF-IDF status and LLM labels.

Because the threshold can't fully separate rewording from real additions, theme counts use a stricter
test: an added sentence is a *new* tariff (or AI) mention only if its best prior match has no tariff
(or AI) term (tariff_theme_new / ai_theme_new).

Outputs: data/added_sentences.csv (one row per added sentence) and data/added_by_ticker.csv.
"""
import re
from pathlib import Path

import pandas as pd
from rapidfuzz import fuzz, process

ADDED_T = 85      # best fuzz.ratio below this against all prior sentences = added
MIN_SENTENCE = 40  # shorter pieces are fragments (list stubs, headings)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LABELS_PATH = DATA_DIR / "llm_labels_all_v1_sonnet_final.csv"

THEMES = {
    "tariff": re.compile(r"\btariffs?\b|\btrade wars?\b|\btrade polic(?:y|ies)\b|\bimport duties\b|"
                         r"\banti-dumping\b|\bcountervailing\b|\bde minimis\b", re.I),
    "ai": re.compile(r"\bAI\b|\bartificial intelligence\b|\bmachine learning\b|\bgenerative AI\b|"
                     r"\blarge language models?\b|\bLLMs?\b", re.I),
}

# Periods inside these must not end a sentence; they are masked before splitting and restored after.
ABBREVIATIONS = ["U.S.", "U.K.", "E.U.", "Inc.", "e.g.", "i.e.", "No.", "approx.", "Corp.", "Co.", "Ltd.", "vs."]
_MASK = "⁣"  # invisible separator, never present in filings
_ABBR_RE = re.compile("|".join(re.escape(a) for a in sorted(ABBREVIATIONS, key=len, reverse=True)))
# A boundary is whitespace after . ! or ? (optionally followed by a closing quote/bracket, which stays with
# its sentence), before a sentence-like start; line breaks (bullets, joined blocks) are boundaries too.
_SPLIT_RE = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"”’)]))\s+(?=[A-Z0-9“\"(•])|\n+")


def split_sentences(text):
    masked = _ABBR_RE.sub(lambda m: m.group(0).replace(".", _MASK), text)
    pieces = (p.replace(_MASK, ".").strip() for p in _SPLIT_RE.split(masked))
    return [p for p in pieces if len(p) >= MIN_SENTENCE]


def normalise(sentence):
    return re.sub(r"\s+", " ", sentence.lower()).strip()


def sentences_frame(units):
    rows = [{"paragraph_id": u.paragraph_id, "ticker": u.ticker, "pair_position": u.pair_position,
             "status": u.status, "sentence": s}
            for u in units.itertuples() for s in split_sentences(u.text)]
    return pd.DataFrame(rows)


def find_added(sents):
    out = []
    for ticker, g in sents.groupby("ticker"):
        latest, prior = g[g.pair_position == "latest"], g[g.pair_position == "prior"]
        choices = [normalise(s) for s in prior.sentence]
        for r in latest.itertuples():
            match, score, idx = process.extractOne(normalise(r.sentence), choices, scorer=fuzz.ratio)
            if score < ADDED_T:
                out.append({"paragraph_id": r.paragraph_id, "ticker": ticker, "status": r.status,
                            "sentence": r.sentence, "best_prior_match": prior.sentence.iat[idx],
                            "best_prior_paragraph": prior.paragraph_id.iat[idx], "best_score": round(score, 1)})
    return pd.DataFrame(out)


def by_ticker(added, tickers):
    def counts(mask, prefix):
        c = added[mask].groupby(["ticker", "status"]).size().unstack(fill_value=0)
        c = c.reindex(index=tickers, columns=["kept", "modified", "new"], fill_value=0)
        c.columns = [f"{prefix}_{s}" for s in c.columns]
        c.insert(0, prefix, c.sum(axis=1))
        return c
    table = pd.concat([counts(added.ticker.notna(), "added"), counts(added.tariff, "tariff"),
                       counts(added.ai, "ai"), counts(added.tariff_theme_new, "tariff_theme_new"),
                       counts(added.ai_theme_new, "ai_theme_new")], axis=1)
    return table.rename_axis("ticker").reset_index()


def main():
    units = pd.read_csv(DATA_DIR / "paragraphs.csv", keep_default_na=False)
    sents = sentences_frame(units)
    added = find_added(sents)
    for theme, pattern in THEMES.items():
        added[theme] = added.sentence.str.contains(pattern)
        added[f"prior_has_{theme}"] = added.best_prior_match.str.contains(pattern)
        added[f"{theme}_theme_new"] = added[theme] & ~added[f"prior_has_{theme}"]
    labels = pd.read_csv(LABELS_PATH, dtype=str, keep_default_na=False).set_index("paragraph_id")
    added["llm_category"] = added.paragraph_id.map(labels.category)
    added["llm_novelty"] = added.paragraph_id.map(labels.novelty)
    added.to_csv(DATA_DIR / "added_sentences.csv", index=False)

    table = by_ticker(added, sorted(units.ticker.unique()))
    table.sort_values(["tariff_theme_new", "ai_theme_new"], ascending=False).to_csv(DATA_DIR / "added_by_ticker.csv", index=False)
    latest_n = (sents.pair_position == "latest").sum()
    print(f"{latest_n:,} latest-year sentences; {len(added):,} added (best prior match < {ADDED_T}); "
          f"{int(added.tariff.sum())} tariff ({int(added.tariff_theme_new.sum())} new theme), "
          f"{int(added.ai.sum())} AI ({int(added.ai_theme_new.sum())} new theme)")
    print(f"wrote {DATA_DIR / 'added_sentences.csv'} and {DATA_DIR / 'added_by_ticker.csv'}")


if __name__ == "__main__":
    main()
