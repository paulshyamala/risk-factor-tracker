"""Write MOCK versions of the five site JSON files to web/public/data/, so the frontend can be
built before labelling, evaluation and returns exist.

Real: tickers, names, industries, filing dates, change scores, TF-IDF counts and unit text
(from paragraphs.csv and change_scores.csv). Fake: every LLM label, eval metric and return.
Fake prose is prefixed "[MOCK]" and every file carries "mock": true.
Run after 02_diff.py; 06_export.py later overwrites these files with real data."""
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "pipeline" / "data"
OUT = ROOT / "web" / "public" / "data"
rng = np.random.default_rng(42)

CATS = ["tariffs/trade", "AI/tech", "cyber/data privacy", "credit/liquidity", "regulation/legal",
        "competition", "M&A/transactions", "macro", "other", "not_a_risk"]
COMPANIES = {  # ticker: (display name, industry, is_canadian)
    "SHOP": ("Shopify Inc.", "E-commerce/payments", True),
    "CP": ("Canadian Pacific Kansas City Limited", "Rail", True),
    "QSR": ("Restaurant Brands International Inc.", "Restaurants", True),
    "LULU": ("lululemon athletica inc.", "Apparel", True),
    "WCN": ("Waste Connections, Inc.", "Waste", True),
    "UNP": ("Union Pacific Corporation", "Rail", False),
    "CSX": ("CSX Corporation", "Rail", False),
    "NSC": ("Norfolk Southern Corporation", "Rail", False),
    "MCD": ("McDonald's Corporation", "Restaurants", False),
    "YUM": ("Yum! Brands, Inc.", "Restaurants", False),
    "DPZ": ("Domino's Pizza, Inc.", "Restaurants", False),
    "WEN": ("The Wendy's Company", "Restaurants", False),
    "CMG": ("Chipotle Mexican Grill, Inc.", "Restaurants", False),
    "SBUX": ("Starbucks Corporation", "Restaurants", False),
    "WM": ("Waste Management, Inc.", "Waste", False),
    "RSG": ("Republic Services, Inc.", "Waste", False),
    "NKE": ("NIKE, Inc.", "Apparel", False),
    "GAP": ("Gap Inc.", "Apparel", False),
    "UAA": ("Under Armour, Inc.", "Apparel", False),
    "VFC": ("V.F. Corporation", "Apparel", False),
    "AMZN": ("Amazon.com, Inc.", "E-commerce/payments", False),
    "EBAY": ("eBay Inc.", "E-commerce/payments", False),
    "ETSY": ("Etsy, Inc.", "E-commerce/payments", False),
    "PYPL": ("PayPal Holdings, Inc.", "E-commerce/payments", False),
    "XYZ": ("Block, Inc.", "E-commerce/payments", False),
}
KEYWORDS = [  # rough keyword guess so mock categories look plausible against the real text
    ("tariffs/trade", r"tariff|trade polic|export control|sanction|import"),
    ("M&A/transactions", r"merger|acquisition|divest|spin-off|separation"),
    ("cyber/data privacy", r"cyber|breach|ransomware|hack|personal (data|information)|privacy"),
    ("AI/tech", r"artificial intelligence|\bAI\b|machine learning|technology|software|systems"),
    ("credit/liquidity", r"indebtedness|debt|credit rating|liquidity|financing|borrow"),
    ("regulation/legal", r"regulat|litigation|law|legal|compliance|government"),
    ("competition", r"compet|market share|consumer preferences"),
    ("macro", r"econom|inflation|interest rate|currency|geopolitic|recession"),
]
AI_RE = re.compile(r"artificial intelligence|\bAI\b|machine learning|generative|large language", re.I)


def r3(x):
    return None if x is None else round(float(x), 3)


def first_sentence(text):
    body = text.split("\n\n", 1)[-1] if "\n\n" in text else text
    m = re.match(r"(.+?[.!?])(\s|$)", body.replace("\n", " "))
    return m.group(1) if m else body[:200]


def guess_category(text):
    for cat, pat in KEYWORDS:
        if re.search(pat, text, re.I):
            return cat
    return "other"


def write(name, obj):
    (OUT / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


scores = pd.read_csv(DATA / "change_scores.csv")
paras = pd.read_csv(DATA / "paragraphs.csv")
with sqlite3.connect(DATA / "filings.db") as conn:
    dates = pd.read_sql("SELECT ticker, pair_position, filing_date FROM filings WHERE pair_position IS NOT NULL", conn)
dates = dates.pivot(index="ticker", columns="pair_position", values="filing_date")

# ---- risks: ~120 real candidate units (one per ticker first, then random fill), fake labels ----
cands = paras[(paras.pair_position == "latest") & paras.status.isin(["new", "modified"])]
first = cands.groupby("ticker").sample(1, random_state=42)
rest = cands.drop(first.index).sample(120 - len(first), random_state=42)
picked = pd.concat([first, rest]).sort_values("paragraph_id")
risks = []
for r in picked.itertuples():
    category = "not_a_risk" if rng.random() < 0.05 else guess_category(r.text)
    is_risk = category != "not_a_risk"
    p_new = 0.65 if r.status == "new" else 0.25
    risks.append({
        "paragraph_id": r.paragraph_id,
        "ticker": r.ticker,
        "section": r.section if isinstance(r.section, str) else None,
        "headline": r.headline if isinstance(r.headline, str) else None,
        "text_excerpt": r.text[:600],
        "category": category,
        "novelty": ("genuinely_new" if rng.random() < p_new else "reworded") if is_risk else None,
        "severity": int(rng.choice([1, 2, 3], p=[0.3, 0.5, 0.2])) if is_risk else None,
        "mentions_ai": bool(AI_RE.search(r.text)),
        "proof": first_sentence(r.text),
        "quote_valid": bool(rng.random() < 0.95),
        "tfidf_status": r.status,
        "best_sim": r3(r.best_sim),
        "prior_match_excerpt": r.match_1[:300],
    })
write("risks.json", {"mock": True, "data": risks})
rdf = pd.DataFrame(risks)
gn = rdf[rdf.novelty == "genuinely_new"]

# ---- companies: real names, industries, dates, scores and counts; mock genuinely-new counts ----
companies = []
for rank, s in enumerate(scores.sort_values("change_score", ascending=False).itertuples(), start=1):
    name, industry, is_canadian = COMPANIES[s.ticker]
    counts = gn[gn.ticker == s.ticker].category.value_counts()
    companies.append({
        "ticker": s.ticker, "name": name, "industry": industry, "is_canadian": is_canadian,
        "latest_filing_date": dates.loc[s.ticker, "latest"], "prior_filing_date": dates.loc[s.ticker, "prior"],
        "change_score": r3(s.change_score), "rank": rank,
        "n_latest": int(s.n_latest), "n_prior": int(s.n_prior), "n_new": int(s.n_new),
        "n_modified": int(s.n_modified), "n_kept": int(s.n_kept), "n_deleted": int(s.n_deleted),
        "n_genuinely_new": int(counts.sum()),
        "category_counts": {c: int(counts.get(c, 0)) for c in CATS},
    })
write("companies.json", {"mock": True, "data": companies})

# ---- eval: square confusion over CATS summing to 40, metrics derived from it ----
I = CATS.index
support = np.array([5, 4, 4, 3, 6, 4, 3, 5, 3, 3])  # human labels per category (CATS order), sums to 40
assert len(support) == len(CATS)
matrix = np.diag(support).astype(int)
CONFUSIONS = [("macro", "tariffs/trade"), ("regulation/legal", "cyber/data privacy"), ("AI/tech", "competition"),
              ("other", "macro"), ("regulation/legal", "credit/liquidity"), ("not_a_risk", "other"),
              ("M&A/transactions", "regulation/legal")]  # (human, llm): 7 plausible confusions
for i, j in [(I(h), I(l)) for h, l in CONFUSIONS]:
    matrix[i, i] -= 1
    matrix[i, j] += 1
assert matrix.sum() == 40
tp, pred, true = np.diag(matrix), matrix.sum(axis=0), matrix.sum(axis=1)
per_category = []
for k, c in enumerate(CATS):
    p = tp[k] / pred[k] if pred[k] else None
    rcl = tp[k] / true[k] if true[k] else None
    f1 = 2 * p * rcl / (p + rcl) if p and rcl else (0.0 if p is not None and rcl is not None else None)
    per_category.append({"category": c, "precision": r3(p), "recall": r3(rcl), "f1": r3(f1), "support": int(true[k])})
risk_rows = [k for k, c in enumerate(CATS) if c != "not_a_risk"]
test = cands.sample(5, random_state=7)  # any candidates; the real file uses test-set failures
failure_pairs = [(I(h), I(l)) for h, l in CONFUSIONS[:5]]
failures = [{
    "paragraph_id": g.paragraph_id, "ticker": g.ticker, "text_excerpt": g.text[:400],
    "human_label": CATS[i], "llm_label": CATS[j],
    "why": f"[MOCK] Placeholder explanation of why the model chose {CATS[j]} over {CATS[i]}.",
} for g, (i, j) in zip(test.itertuples(), failure_pairs)]
evaluation = {
    "mock": True, "n_test": 40,
    "accuracy": r3(tp.sum() / 40),
    "accuracy_risks_only": r3(tp[risk_rows].sum() / matrix[risk_rows].sum()),
    "per_category": per_category,
    "confusion": {"labels": CATS, "matrix": matrix.tolist()},
    "novelty_accuracy": 0.775, "severity_exact": 0.6, "severity_within_1": 0.925,
    "quote_valid_rate": r3(rdf.quote_valid.mean()), "tfidf_new_genuine_rate": 0.45,
    "failures": failures,
}
write("eval.json", evaluation)

# ---- returns: real scores and filing dates, fake abnormal returns ----
returns = [{"ticker": c["ticker"], "change_score": c["change_score"],
            "abnormal_return_60d": r3(rng.normal(0, 0.06)), "filing_date": c["latest_filing_date"]}
           for c in companies]
write("returns.json", {"mock": True, "data": returns})

# ---- summary ----
latest = paras[paras.pair_position == "latest"]
spot = next(c for c in companies if c["ticker"] == "UNP")
summary = {
    "mock": True,
    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "model": "claude-haiku-5-5",
    "codebook_version": "1.2",
    "n_companies": len(companies),
    "n_units_latest": int(len(latest)),
    "pct_kept": r3((latest.status == "kept").mean()),
    "n_candidates": int(latest.status.isin(["new", "modified"]).sum()),
    "n_genuinely_new": int(len(gn)),
    "n_companies_added_tariff_risk": int(gn[gn.category == "tariffs/trade"].ticker.nunique()),
    "n_companies_added_ai_risk": int(gn[gn.mentions_ai].ticker.nunique()),
    "llm_accuracy_test": evaluation["accuracy"],
    "quote_valid_rate": evaluation["quote_valid_rate"],
    "headline_findings": [
        "[MOCK] Starbucks rewrote its Risk Factors more than any other company in the sample.",
        "[MOCK] Union Pacific added a block of new risks tied to its proposed merger with Norfolk Southern.",
        "[MOCK] Tariff risk was the most common genuinely new category across restaurants and apparel.",
        "[MOCK] Most changes elsewhere were rewording rather than new risks.",
    ],
    "spotlight": {
        "ticker": spot["ticker"], "name": spot["name"],
        "summary": f"[MOCK] Union Pacific added {spot['n_new']} new risk units, almost all about the proposed "
                   "merger. Its prior-year risks were carried over unchanged.",
        "memo_url": "memo.pdf",
    },
}
write("summary.json", summary)
print({f.name: f.stat().st_size for f in sorted(OUT.glob("*.json"))})
print("risks", len(risks), "tickers", rdf.ticker.nunique(), "genuinely_new", len(gn), "confusion total", int(matrix.sum()))
