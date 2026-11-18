"""Build output/powerbi/risk_tracker_dashboard.xlsx (the Power BI dashboard's data) from existing outputs.

Reads change_scores.csv, added_by_ticker.csv, llm_labels_all_v1_sonnet_final.csv and the README company
table; cross-checks totals against FINDINGS.md and exits without writing if any check fails.
"""
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
DATA = ROOT / "pipeline" / "data"
OUT = ROOT / "output" / "powerbi" / "risk_tracker_dashboard.xlsx"

cs = pd.read_csv(DATA / "change_scores.csv")
abt = pd.read_csv(DATA / "added_by_ticker.csv")
lab = pd.read_csv(DATA / "llm_labels_all_v1_sonnet_final.csv")

# Company metadata: README "Data and scope" table
meta_rows = []
for line in (ROOT / "README.md").read_text().splitlines():
    m = re.match(r"^\|\s*([A-Z]{1,5})\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*(Yes)?\s*\|$", line)
    if m:
        meta_rows.append({"ticker": m[1], "company": m[2], "industry_group": m[3],
                          "canadian": "Yes" if m[4] else "No"})
meta = pd.DataFrame(meta_rows)

new = lab[lab.novelty == "genuinely_new"]
mentions_ai = lab.mentions_ai.astype(str).str.lower() == "true"

# ---------- cross-checks against FINDINGS.md ----------
checks = []
def check(name, actual, expected):
    checks.append((name, actual, expected, actual == expected))

check("genuinely new risks (labels rows)", len(new), 54)
check("companies with new tariff sentences (tariff_theme_new > 0)", int((abt.tariff_theme_new > 0).sum()), 15)
check("companies with new AI section (genuinely_new & mentions_ai)",
      lab[(lab.novelty == "genuinely_new") & mentions_ai].ticker.nunique(), 9)
check("companies with new AI sentences (ai_theme_new > 0)", int((abt.ai_theme_new > 0).sum()), 19)
pct_kept = cs.n_kept.sum() / cs.n_latest.sum()
check("% latest-year paragraphs unchanged, rounded", round(pct_kept * 100), 80)
# supporting checks
check("companies in change_scores", len(cs), 25)
check("companies in added_by_ticker", len(abt), 25)
check("companies in README table", len(meta), 25)
check("same tickers across all three", set(cs.ticker) == set(abt.ticker) == set(meta.ticker), True)
check("labelled (changed) paragraphs", len(lab), 351)
check("companies with a genuinely new risk", new.ticker.nunique(), 15)
check("kept+modified+new == n_latest for every company",
      bool(((cs.n_kept + cs.n_modified + cs.n_new) == cs.n_latest).all()), True)
for t in ("tariff", "ai"):
    c = f"{t}_theme_new"
    check(f"{c} == kept+modified+new for every company",
          bool((abt[c] == abt[f"{c}_kept"] + abt[f"{c}_modified"] + abt[f"{c}_new"]).all()), True)
check("tariff_theme_new total sentences", int(abt.tariff_theme_new.sum()), 59)
check("new tariff/trade-category risks", int((new.category == "tariffs/trade").sum()), 0)

for name, a, e, ok in checks:
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got {a}, expected {e}")
print(f"      (unchanged share exact: {cs.n_kept.sum()}/{cs.n_latest.sum()} = {pct_kept:.2%})")
if not all(c[3] for c in checks):
    sys.exit("Cross-check mismatch: stopping, no file written.")

# ---------- 1. companies ----------
gn = new.groupby("ticker").size()
companies = (cs.assign(rank=cs.change_score.rank(ascending=False, method="min").astype(int))
             .merge(meta, on="ticker", how="left")
             .rename(columns={"n_kept": "kept", "n_modified": "modified", "n_new": "new", "n_deleted": "deleted"}))
companies["genuinely_new_risks"] = companies.ticker.map(gn).fillna(0).astype(int)
companies = companies[["ticker", "company", "industry_group", "canadian", "change_score", "rank",
                       "kept", "modified", "new", "deleted", "genuinely_new_risks"]].sort_values("rank")

# ---------- 2. paragraph_status ----------
status_map = {"Unchanged": "kept", "Reworded": "modified", "New": "new", "Deleted": "deleted"}
paragraph_status = pd.concat(
    [companies[["ticker", src]].rename(columns={src: "paragraphs"}).assign(status=label)
     for label, src in status_map.items()])
paragraph_status["_o"] = paragraph_status.status.map({k: i for i, k in enumerate(status_map)})
paragraph_status = paragraph_status.merge(companies[["ticker", "rank"]], on="ticker") \
    .sort_values(["rank", "_o"])[["ticker", "status", "paragraphs"]]

# ---------- 3. themes ----------
ai_section = set(lab[(lab.novelty == "genuinely_new") & mentions_ai].ticker)
tariff_section = set(new[new.category == "tariffs/trade"].ticker)
where = {"Kept paragraph": "kept", "Modified paragraph": "modified", "New paragraph": "new"}
rows = []
for _, r in abt.iterrows():
    for theme, prefix, sect in (("Tariffs", "tariff_theme_new", tariff_section), ("AI", "ai_theme_new", ai_section)):
        for w, suffix in where.items():
            rows.append({"ticker": r.ticker, "theme": theme, "where_added": w,
                         "new_sentences": int(r[f"{prefix}_{suffix}"]),
                         "new_section": "Yes" if r.ticker in sect else "No"})
themes = pd.DataFrame(rows).merge(companies[["ticker", "rank"]], on="ticker") \
    .sort_values(["rank", "theme", "where_added"], key=lambda s: s.map({"Tariffs": 0, "AI": 1}) if s.name == "theme" else s,
                 kind="stable").drop(columns="rank")

# ---------- 4. new_risks ----------
new_risks = new[["ticker", "category", "severity"]].copy()
new_risks["severity"] = new_risks.severity.astype(int) if (new_risks.severity % 1 == 0).all() else new_risks.severity
new_risks = new_risks.sort_values(["ticker", "category", "severity"]).reset_index(drop=True)

# ---------- post-build checks ----------
assert themes[themes.theme == "Tariffs"].groupby("ticker").new_sentences.sum().gt(0).sum() == 15
assert themes[themes.theme == "AI"].groupby("ticker").new_sentences.sum().gt(0).sum() == 19
assert themes[(themes.theme == "AI") & (themes.new_section == "Yes")].ticker.nunique() == 9
assert companies.genuinely_new_risks.sum() == len(new_risks) == 54
assert companies[["company", "industry_group"]].notna().all().all()

OUT.parent.mkdir(parents=True, exist_ok=True)
with pd.ExcelWriter(OUT, engine="openpyxl") as xw:
    for name, df in (("companies", companies), ("paragraph_status", paragraph_status),
                     ("themes", themes), ("new_risks", new_risks)):
        df.to_excel(xw, sheet_name=name, index=False)
        print(f"{name}: {len(df)} rows")
print(OUT)
