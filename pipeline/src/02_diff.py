"""Group Risk Factors into risk units, score each company's year-over-year change, and flag
new / modified / kept / deleted units with TF-IDF cosine similarity."""
import argparse
import re
import sqlite3
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font
from openpyxl.worksheet.datavalidation import DataValidation
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

KEPT_T = 0.80  # best match >= KEPT_T: unit kept (substantively unchanged)
NEW_T = 0.50   # best match < NEW_T: unit new (latest) or deleted (prior); in between: modified
GOLD_SIZE, GOLD_DEV, GOLD_PER_TICKER, GOLD_SEED = 60, 20, 3, 42
MIN_CHARS = 200
MIN_LONE_HEADLINE_CHARS = 60  # headlines with no body are kept down to this length
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "filings.db"
GOLD_PATH = DATA_DIR / "gold_labels.xlsx"

# Label dropdowns for the gold sheet (codebook.md sections 2, 4-6).
LABEL_OPTIONS = {
    "category": ["tariffs/trade", "AI/tech", "cyber/data privacy", "credit/liquidity",
                 "regulation/legal", "competition", "macro", "other", "not_a_risk"],
    "novelty": ["genuinely_new", "reworded", "n/a"],
    "novelty_uncertain": ["TRUE", "FALSE"],
    "severity": ["1", "2", "3", "n/a"],
    "mentions_ai": ["TRUE", "FALSE"],
    "rationale": None,
}

BULLET_RE = re.compile(r"^[•●◦▪\-–]")
SUMMARY_RE = re.compile(r"summary of risk|risk factors summary|summary risk factors", re.I)
TERMINAL = tuple(".;:?!")
# A sentence boundary inside a block: terminal punctuation, optional closing quote, space, capital.
SENTENCE_BREAK_RE = re.compile(r"[.!?][\"”’)]?\s+[A-Z“\"]")
# Enumerated list items such as "(ii) ..." or "(b) ...".
ENUM_ITEM_RE = re.compile(r"^\((?:[ivx]+|[a-z])\)")
ITEM_1A_RE = re.compile(r"^item\s*1a\b", re.I)


def load_filings():
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql(
            "SELECT ticker, pair_position, fiscal_year, text_clean FROM filings "
            "WHERE pair_position IN ('latest', 'prior') ORDER BY ticker, pair_position",
            conn,
        )


def strip_closers(block):
    """Drop trailing quotes/brackets so 'risk."' and 'risk.)' count as ending in '.'."""
    return block.rstrip("\"”’)] ")


def is_bullet(block):
    return bool(BULLET_RE.match(block))


def is_heading(block):
    return len(block) < 150 and not is_bullet(block) and not strip_closers(block).endswith(TERMINAL)


def is_headline(block):
    """A one- or two-sentence block under 400 chars ending in '.'."""
    return (len(block) < 400 and not is_bullet(block)
            and strip_closers(block).endswith(".")
            and len(SENTENCE_BREAK_RE.findall(strip_closers(block)[:-1])) <= 1)


def attaches(block):
    """Bullets, "(ii)"-style list items and lowercase continuations (e.g. list items without
    bullet glyphs, or text split by a page break) belong to the preceding unit."""
    return is_bullet(block) or block[0].islower() or bool(ENUM_ITEM_RE.match(block))


def summary_span(blocks):
    """Indices of the Risk Factors Summary: from its heading, through any intro text and the
    bullet list (with its short group headings / "...risks:" lead-ins), up to the first longer
    non-bullet block. Ending at the first detected headline instead would swallow real risk
    factors whenever headline detection misses (e.g. XYZ's two-sentence headlines)."""
    for start, block in enumerate(blocks):
        if is_heading(block) and SUMMARY_RE.search(block):
            seen_bullet = False
            for end in range(start + 1, len(blocks)):
                b = blocks[end]
                if is_bullet(b):
                    seen_bullet = True
                elif seen_bullet and not (is_heading(b) or (len(b) < 150 and b.endswith(":"))):
                    return range(start, end)
            break
    return range(0)


def group_filing(text):
    """Group one filing's blocks into risk units. Returns (units, summary_blocks_excluded)."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    blocks = [b for b in blocks if not ITEM_1A_RE.match(b)]  # "Item 1A. Risk Factors." titles
    excluded = summary_span(blocks)
    units, section, i = [], None, 0
    current = None  # unit that following bullets / continuations attach to
    while i < len(blocks):
        block = blocks[i]
        nxt = blocks[i + 1] if i + 1 < len(blocks) else None
        if i in excluded:
            # Still track headings, so the first units after the summary get the right section.
            if is_heading(block):
                section = block
        elif attaches(block):
            if current is None:
                # No lead-in (e.g. straight after a heading): start a unit of its own.
                current = {"section": section, "headline": None, "text": block, "lone": False}
                units.append(current)
            else:
                current["text"] += "\n" + block
        elif is_heading(block):
            section, current = block, None
        elif is_headline(block):
            current = {"section": section, "headline": block, "text": block, "lone": False}
            units.append(current)
            if nxt is None or is_heading(nxt) or is_headline(nxt):
                current["lone"] = True  # no body: keep the headline as its own unit
            elif not attaches(nxt):
                current["text"] += "\n\n" + nxt
                i += 1  # body consumed
            # else: the headline is the lead-in; following bullets/continuations attach to it
        else:
            current = {"section": section, "headline": None, "text": block, "lone": False}
            units.append(current)
        i += 1
    return units, len(excluded)


def split_paragraphs(filings):
    """Group every filing into risk units. Returns (kept, dropped, excluded_counts):
    units under MIN_CHARS go to dropped, except headlines with no body, which only need
    MIN_LONE_HEADLINE_CHARS. Ids count kept units only."""
    kept, dropped, excluded_counts = [], [], {}
    for f in filings.itertuples():
        units, excluded_counts[(f.ticker, f.pair_position)] = group_filing(f.text_clean)
        index = 0
        for unit in units:
            lone = unit.pop("lone")
            row = {"ticker": f.ticker, "pair_position": f.pair_position, **unit, "char_len": len(unit["text"])}
            if row["char_len"] < (MIN_LONE_HEADLINE_CHARS if lone else MIN_CHARS):
                row["lone_headline"] = lone
                dropped.append(row)
            else:
                index += 1
                kept.append({"paragraph_id": f"{f.ticker}_{f.pair_position}_{index:03d}", **row})
    return pd.DataFrame(kept), pd.DataFrame(dropped), excluded_counts


def company_scores(units):
    """ChangeScore = 1 - cosine(latest, prior) over each filing's joined units, with one
    vectorizer fit on all filings so every company shares the same vocabulary weights."""
    docs = units.groupby(["ticker", "pair_position"]).text.apply("\n\n".join).unstack()
    vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True, min_df=2)
    vectorizer.fit(pd.concat([docs.latest, docs.prior]))
    latest, prior = vectorizer.transform(docs.latest), vectorizer.transform(docs.prior)
    sims = (latest.multiply(prior)).sum(axis=1).A1  # rows are L2-normalised: dot = cosine
    return pd.Series(1 - sims, index=docs.index, name="change_score")


def match_units(units):
    """Per ticker, compare every latest unit with every prior unit. Adds status, best_sim and
    (latest rows only) the top 3 prior matches."""
    out = []
    for ticker, g in units.groupby("ticker"):
        latest = g[g.pair_position == "latest"].reset_index(drop=True)
        prior = g[g.pair_position == "prior"].reset_index(drop=True)
        vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True, min_df=1)
        vectorizer.fit(g.text)
        sims = cosine_similarity(vectorizer.transform(latest.text), vectorizer.transform(prior.text))

        latest["best_sim"] = sims.max(axis=1)
        latest["status"] = ["kept" if s >= KEPT_T else "modified" if s >= NEW_T else "new"
                            for s in latest.best_sim]
        top = sims.argsort(axis=1)[:, ::-1][:, :3]
        for k in range(3):
            latest[f"match_{k + 1}_id"] = prior.paragraph_id.to_numpy()[top[:, k]]
            latest[f"match_{k + 1}"] = prior.text.to_numpy()[top[:, k]]
            latest[f"match_{k + 1}_sim"] = sims[range(len(latest)), top[:, k]]

        prior["best_sim"] = sims.max(axis=0)
        prior["status"] = ["matched" if s >= NEW_T else "deleted" for s in prior.best_sim]
        out += [latest, prior]
    return pd.concat(out, ignore_index=True)


def summarize(matched, scores):
    latest = matched[matched.pair_position == "latest"]
    counts = matched.groupby("ticker").status.value_counts().unstack(fill_value=0)
    table = pd.DataFrame({
        "change_score": scores,
        "n_latest": latest.groupby("ticker").size(),
        "n_prior": matched[matched.pair_position == "prior"].groupby("ticker").size(),
        **{f"n_{s}": counts.get(s, 0) for s in ("new", "modified", "kept", "deleted")},
    })
    table["pct_new"] = table.n_new / table.n_latest
    new_chars = latest[latest.status == "new"].groupby("ticker").char_len.sum()
    table["new_chars_share"] = new_chars.reindex(table.index, fill_value=0) / latest.groupby("ticker").char_len.sum()
    return table.rename_axis("ticker").reset_index().sort_values("change_score", ascending=False)


def export_gold(matched):
    """Sample the gold set from latest "new"/"modified" units and write the labelling sheet.
    Status and similarity scores go to gold_meta.csv only, so they can't anchor the labeller."""
    candidates = matched[(matched.pair_position == "latest") & matched.status.isin(["new", "modified"])]
    print(f"gold candidates: {len(candidates)} "
          f"({(candidates.status == 'new').sum()} new, {(candidates.status == 'modified').sum()} modified) "
          f"from {candidates.ticker.nunique()} tickers")
    shuffled = candidates.sample(frac=1, random_state=GOLD_SEED)
    capped = shuffled.groupby("ticker", sort=False).head(GOLD_PER_TICKER)  # keeps shuffled order
    if len(capped) < GOLD_SIZE:
        print(f"Only {len(capped)} candidates available at {GOLD_PER_TICKER} per ticker; "
              f"need {GOLD_SIZE}. Not writing the gold sample.")
        return
    gold = capped.head(GOLD_SIZE).copy()
    gold["split"] = ["dev"] * GOLD_DEV + ["test"] * (GOLD_SIZE - GOLD_DEV)
    gold = gold.sort_values(["split", "ticker"], key=lambda c: c.map({"dev": 0, "test": 1}) if c.name == "split" else c)

    gold[["paragraph_id", "status", "best_sim", "match_1_sim", "match_2_sim", "match_3_sim"]].to_csv(
        DATA_DIR / "gold_meta.csv", index=False)
    # Label columns sit right after the text, so they're visible without scrolling past the matches.
    sheet = gold[["paragraph_id", "ticker", "split", "section", "text"]].copy()
    for col in LABEL_OPTIONS:
        sheet[col] = None
    sheet[["match_1", "match_2", "match_3"]] = gold[["match_1", "match_2", "match_3"]]

    with pd.ExcelWriter(GOLD_PATH, engine="openpyxl") as writer:
        sheet.to_excel(writer, sheet_name="gold", index=False)
        ws = writer.sheets["gold"]
        n = len(sheet) + 1
        for idx, col in enumerate(sheet.columns, start=1):
            letter = ws.cell(row=1, column=idx).column_letter
            ws.column_dimensions[letter].width = 80 if col in ("text", "match_1", "match_2", "match_3") else 18
            options = LABEL_OPTIONS.get(col)
            if options:
                dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
                dv.add(f"{letter}2:{letter}{n}")
                ws.add_data_validation(dv)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        for cell in ws[1]:
            cell.font = Font(bold=True)
        ws.freeze_panes = "A2"
    print(f"wrote {GOLD_PATH} and {DATA_DIR / 'gold_meta.csv'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", action="store_true", help="also export the gold labelling sample")
    parser.add_argument("--force", action="store_true", help="with --gold, overwrite an existing gold_labels.xlsx")
    args = parser.parse_args()
    if args.gold and GOLD_PATH.exists() and not args.force:
        parser.error(f"{GOLD_PATH} already exists (it may hold hand labels); pass --force to overwrite")

    units, dropped, excluded = split_paragraphs(load_filings())
    print(f"{len(units):,} units kept, {len(dropped):,} dropped (< {MIN_CHARS} chars), "
          f"{sum(excluded.values()):,} summary blocks excluded")

    scores = company_scores(units)
    matched = match_units(units)
    table = summarize(matched, scores)

    columns = ["paragraph_id", "ticker", "pair_position", "section", "headline", "text", "char_len",
               "status", "best_sim"] + [f"match_{k}{s}" for k in (1, 2, 3) for s in ("_id", "", "_sim")]
    matched[columns].to_csv(DATA_DIR / "paragraphs.csv", index=False)
    table.to_csv(DATA_DIR / "change_scores.csv", index=False)
    print(matched[matched.pair_position == "latest"].status.value_counts().to_string())
    print(f"deleted: {(matched.status == 'deleted').sum()}")
    print(f"wrote {DATA_DIR / 'paragraphs.csv'} and {DATA_DIR / 'change_scores.csv'}")
    if args.gold:
        export_gold(matched)


if __name__ == "__main__":
    main()
