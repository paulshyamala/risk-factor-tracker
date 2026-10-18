"""Compare LLM labels against data/gold_labels.xlsx on the held-out test set (scored once, never tuned on).

Scores category, novelty, severity, mentions_ai and the quote check, plus dispute-adjusted and
run-to-run stability views, for both the raw scored run and its rule-applied "_final" version
(apply_rules.py). The final version is the shipped pipeline and leads the report. Also records the
top-5 failure cases chosen in data/eval_errors.xlsx. Writes data/eval_results.json and
data/eval_report.md, and prints a summary.
"""
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import pandas as pd

PIPELINE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PIPELINE_DIR / "data"
GOLD_PATH = DATA_DIR / "gold_labels.xlsx"
GOLD_HASH_PATH = DATA_DIR / "gold_labels.sha256"
LLM_RUN = "test_v1_sonnet"  # the scored run
STABILITY_RUN = "test_v1_sonnet_rep2"  # second labelling of the same rows, for stability only
RESULTS_PATH = DATA_DIR / "eval_results.json"
REPORT_PATH = DATA_DIR / "eval_report.md"
DISPUTES_PATH = DATA_DIR / "gold_disputes.csv"
ERRORS_PATH = DATA_DIR / "eval_errors.xlsx"  # error review sheet; the labeller picks the top 5 there
AFTER_SCORING_NOTE = "test set; recorded after scoring"
META_PATH = DATA_DIR / "gold_meta.csv"  # TF-IDF status and similarity, hidden from the labeller

# One source of truth for the label set: 03_label.py (module name starts with a digit, so load by path).
_spec = importlib.util.spec_from_file_location("label", Path(__file__).with_name("03_label.py"))
_label = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_label)
CATEGORIES = _label.CATEGORIES


def verify_gold_hash():
    expected = GOLD_HASH_PATH.read_text().split()[0]
    actual = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if actual != expected:
        sys.exit(f"ABORT: {GOLD_PATH.name} hash {actual} does not match {GOLD_HASH_PATH.name} ({expected})")


def clean(v):
    """'n/a', empty and null all mean 'no value'."""
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)) \
            or str(v).strip().lower() in ("", "n/a", "nan", "none", "<na>"):
        return None
    return str(v).strip()


def wilson(k, n, z=1.96):
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return None, None
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def accuracy(human, llm):
    k, n = int((human == llm).sum()), len(human)
    lo, hi = wilson(k, n)
    return {"correct": k, "n": n, "accuracy": k / n if n else None, "ci95": [lo, hi]}


def load(run=LLM_RUN):
    """Test-set human labels joined 1:1 with one LLM run (columns suffixed _human / _llm)."""
    gold = pd.read_excel(GOLD_PATH, dtype=object, keep_default_na=False)
    gold = gold[gold.split == "test"]
    llm_path = DATA_DIR / f"llm_labels_{run}.csv"
    llm = pd.read_csv(llm_path, dtype=object, keep_default_na=False)
    missing_llm = sorted(set(gold.paragraph_id) - set(llm.paragraph_id))
    if missing_llm:
        sys.exit(f"ABORT: {len(missing_llm)} test rows missing from {llm_path.name}: {missing_llm}")
    llm = llm[llm.paragraph_id.isin(gold.paragraph_id)]
    merged = gold.merge(llm, on="paragraph_id", suffixes=("_human", "_llm"), validate="1:1")
    if len(merged) != len(gold):
        sys.exit(f"ABORT: joined {len(merged)} rows, expected {len(gold)}")
    for col in merged.columns:
        if col.endswith(("_human", "_llm")):
            merged[col] = merged[col].map(clean)
    return merged


def score_category(df, run=LLM_RUN):
    human, llm = df.category_human, df.category_llm
    risks = human != "not_a_risk"

    per_category = []
    for c in CATEGORIES:
        support, predicted = int((human == c).sum()), int((llm == c).sum())
        tp = int(((human == c) & (llm == c)).sum())
        precision = tp / predicted if predicted else None
        recall = tp / support if support else None
        if precision is None or recall is None:
            f1 = None
        else:
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_category.append({"category": c, "support": support, "predicted": predicted,
                             "precision": precision, "recall": recall, "f1": f1})

    labels = [c for c in CATEGORIES if (human == c).any() or (llm == c).any()]
    matrix = [[int(((human == h) & (llm == p)).sum()) for p in labels] for h in labels]

    errors = df[human != llm]
    return {
        "run": run,
        "accuracy_all": accuracy(human, llm),
        "accuracy_risks_only": accuracy(human[risks], llm[risks]),
        "per_category": per_category,
        "confusion": {"rows": "human", "columns": "llm", "labels": labels, "matrix": matrix},
        "errors": [{"paragraph_id": r.paragraph_id, "ticker": r.ticker_human, "human": r.category_human,
                    "llm": r.category_llm, "reason": r.reason, "text": r.text[:200]}
                   for r in errors.itertuples()],
    }


def binary_metrics(truth, pred):
    """truth/pred: boolean Series, True = genuinely_new (the positive class)."""
    tp, fp = int((truth & pred).sum()), int((~truth & pred).sum())
    fn, tn = int((truth & ~pred).sum()), int((~truth & ~pred).sum())
    n = tp + fp + fn + tn

    def rate(k, d):
        lo, hi = wilson(k, d)
        return {"value": k / d if d else None, "k": k, "n": d, "ci95": [lo, hi]}
    precision, recall = rate(tp, tp + fp), rate(tp, tp + fn)
    p, r = precision["value"], recall["value"]
    f1 = None if p is None or r is None else (2 * p * r / (p + r) if p + r else 0.0)
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": precision, "recall": recall,
            "f1": f1, "agreement": rate(tp + tn, n)}


def score_novelty(df, run=LLM_RUN):
    """Genuinely-new detection on rows the human treated as a risk."""
    meta = pd.read_csv(META_PATH).set_index("paragraph_id")
    rows = df[df.category_human != "not_a_risk"].copy()
    llm_na = int(rows.novelty_llm.isna().sum())  # LLM said not_a_risk; scored as reworded
    truth = rows.novelty_human == "genuinely_new"
    pred_llm = rows.novelty_llm == "genuinely_new"
    rows["tfidf_status"] = rows.paragraph_id.map(meta.status)
    rows["best_sim"] = rows.paragraph_id.map(meta.best_sim)
    pred_tfidf = rows.tfidf_status == "new"

    def detail(subset):
        return [{"paragraph_id": r.paragraph_id, "ticker": r.ticker_human, "human_category": r.category_human,
                 "tfidf_status": r.tfidf_status, "best_sim": round(float(r.best_sim), 3),
                 "llm_novelty_uncertain": r.novelty_uncertain_llm, "reason": r.reason, "text": r.text[:200]}
                for r in subset.itertuples()]
    return {
        "run": run,
        "rows": len(rows),
        "human_genuinely_new": int(truth.sum()),
        "llm_na_scored_as_reworded": llm_na,
        "llm": binary_metrics(truth, pred_llm),
        "baselines": {
            "always_reworded": binary_metrics(truth, pd.Series(False, index=rows.index)),
            "tfidf_only": binary_metrics(truth, pred_tfidf),
        },
        "false_negatives": detail(rows[truth & ~pred_llm]),
        "false_positives": detail(rows[~truth & pred_llm]),
    }


def as_bool(v):
    v = clean(v)  # pandas may hold missing values as NaN / NA rather than None
    return None if v is None else v.lower() == "true"


def as_int(v):
    v = clean(v)
    return None if v is None else int(float(v))


def rate(k, n):
    lo, hi = wilson(k, n)
    return {"value": k / n if n else None, "k": k, "n": n, "ci95": [lo, hi]}


def score_severity(df):
    h, l = df.severity_human.map(as_int), df.severity_llm.map(as_int)
    both = h.notna() & l.notna()
    h, l = h[both].astype(int), l[both].astype(int)
    return {
        "rows": int(both.sum()),
        "exact": rate(int((h == l).sum()), len(h)),
        "within_1": rate(int(((h - l).abs() <= 1).sum()), len(h)),
        "confusion": {"rows": "human", "columns": "llm", "labels": [1, 2, 3],
                      "matrix": [[int(((h == a) & (l == b)).sum()) for b in (1, 2, 3)] for a in (1, 2, 3)]},
        "llm_higher": int((l > h).sum()),
        "llm_lower": int((l < h).sum()),
    }


def score_mentions_ai(df):
    truth, pred = df.mentions_ai_human.map(as_bool), df.mentions_ai_llm.map(as_bool)
    m = binary_metrics(truth.astype(bool), pred.astype(bool))
    return {"rows": len(df), "tp": m["tp"], "fp": m["fp"], "fn": m["fn"], "tn": m["tn"],
            "agreement": m["agreement"], "precision": m["precision"], "recall": m["recall"]}


def score_quote(df, run=LLM_RUN):
    valid = df.quote_valid.map(as_bool).fillna(False)
    return {"run": run, **rate(int(valid.sum()), len(df))}


def score_dispute_adjusted(df, strict):
    """Same headline metrics with disputed (paragraph_id, field) pairs removed."""
    disputes = pd.read_csv(DISPUTES_PATH)
    excluded = {f: set(disputes[disputes.field == f].paragraph_id) & set(df.paragraph_id)
                for f in ("category", "novelty", "severity", "mentions_ai")}
    keep = {f: df[~df.paragraph_id.isin(ids)] for f, ids in excluded.items()}
    cat = keep["category"]
    nov = keep["novelty"]
    nov = nov[nov.category_human != "not_a_risk"]
    nov_m = binary_metrics(nov.novelty_human == "genuinely_new", nov.novelty_llm == "genuinely_new")
    adjusted = {
        "category_accuracy": rate(int((cat.category_human == cat.category_llm).sum()), len(cat)),
        "novelty_precision": nov_m["precision"],
        "novelty_recall": nov_m["recall"],
        "severity_exact": score_severity(keep["severity"])["exact"],
        "mentions_ai_agreement": score_mentions_ai(keep["mentions_ai"])["agreement"],
    }
    strict_view = {
        "category_accuracy": strict["category"]["accuracy_all"],
        "novelty_precision": strict["novelty"]["llm"]["precision"],
        "novelty_recall": strict["novelty"]["llm"]["recall"],
        "severity_exact": strict["severity"]["exact"],
        "mentions_ai_agreement": strict["mentions_ai"]["agreement"],
    }
    after = disputes[disputes.note.astype(str).str.contains(AFTER_SCORING_NOTE, regex=False)]
    return {"excluded_rows": {f: sorted(ids) for f, ids in excluded.items()},
            "added_after_scoring": [{"paragraph_id": r.paragraph_id, "field": r.field}
                                    for r in after.itertuples() if r.paragraph_id in set(df.paragraph_id)],
            "strict": strict_view, "adjusted": adjusted}


def score_stability(df, df2, runs=(LLM_RUN, STABILITY_RUN)):
    """Agreement between the scored run and the repeat run, plus novelty on the repeat run."""
    a, b = df.set_index("paragraph_id"), df2.set_index("paragraph_id").loc[df.paragraph_id]
    conv = {"category": str, "novelty": str, "severity": as_int, "mentions_ai": as_bool}
    agreement = {}
    for f, fn in conv.items():
        x = [None if v is None else fn(v) for v in a[f"{f}_llm"]]
        y = [None if v is None else fn(v) for v in b[f"{f}_llm"]]
        agreement[f] = rate(sum(u == v for u, v in zip(x, y)), len(x))
    rep2 = score_novelty(df2, run=runs[1])
    return {"runs": list(runs), "agreement": agreement,
            "rep2_novelty": {"precision": rep2["llm"]["precision"], "recall": rep2["llm"]["recall"],
                             "note": "stability check only, not a score"}}


def pct(r):
    """'85.0% (95% CI 70.9–92.9%) — 34/40' from a rate dict (category accuracy uses accuracy/correct keys)."""
    value, k = r.get("value", r.get("accuracy")), r.get("k", r.get("correct"))
    if value is None:
        return f"n/a ({k}/{r['n']})"
    return f"{100 * value:.1f}% (95% CI {100 * r['ci95'][0]:.1f}–{100 * r['ci95'][1]:.1f}%) — {k}/{r['n']}"


def num(x):
    return "–" if x is None else f"{x:.2f}"


def run_metadata(run):
    first = json.loads((DATA_DIR / "llm_runs" / f"{run}.jsonl").open().readline())
    return {k: first.get(k) for k in ("model", "prompt_version", "prompt_hash", "codebook_version")}


def score_all(run, stability_run):
    """Every metric for one scored run (strict, dispute-adjusted, stability)."""
    df, df2 = load(run), load(stability_run)
    res = {"run": run, "category": score_category(df, run), "novelty": score_novelty(df, run),
           "severity": score_severity(df), "mentions_ai": score_mentions_ai(df), "quote": score_quote(df, run)}
    res["dispute_adjusted"] = score_dispute_adjusted(df, res)
    res["stability"] = score_stability(df, df2, (run, stability_run))
    return res


def load_failures():
    """The 5 cases picked in the error review sheet; abort unless exactly 5, each with verdict and why."""
    from openpyxl import load_workbook
    ws = load_workbook(ERRORS_PATH, read_only=True, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    picked = [dict(zip(rows[0], r)) for r in rows[1:] if str(dict(zip(rows[0], r))["pick_top5"]).strip().upper() == "TRUE"]
    incomplete = [r["paragraph_id"] for r in picked if not clean(r["verdict"]) or not clean(r["why"])]
    if len(picked) != 5 or incomplete:
        sys.exit(f"ABORT: {ERRORS_PATH.name} needs exactly 5 rows with pick_top5 = TRUE, each with verdict and why "
                 f"(found {len(picked)} picked; missing verdict/why: {incomplete})")
    return [{"paragraph_id": r["paragraph_id"], "ticker": r["ticker"], "field": r["field"],
             "human_value": r["human_value"], "llm_value": r["llm_value"], "verdict": r["verdict"],
             "why": r["why"], "evidence": r["evidence"], "text": r["text"][:300]} for r in picked]


def record_disputes(failures):
    """Sync the after-scoring rows of gold_disputes.csv with the current top-5 verdicts: add
    human_label_debatable failures not yet recorded, and remove after-scoring rows whose verdict is no
    longer human_label_debatable. Rows recorded before scoring (dev set) are never touched; nor are
    the gold labels. Returns (added, removed)."""
    disputes = pd.read_csv(DISPUTES_PATH, dtype=str, keep_default_na=False)
    debatable = {(f["paragraph_id"], f["field"].split(" ")[0]) for f in failures if f["verdict"] == "human_label_debatable"}
    after = disputes.note.str.contains(AFTER_SCORING_NOTE, regex=False)
    stale = after & ~pd.Series([(p, f) in debatable for p, f in zip(disputes.paragraph_id, disputes.field)], index=disputes.index)
    removed = [(r.paragraph_id, r.field) for r in disputes[stale].itertuples()]
    disputes = disputes[~stale]
    runs = {r: load(r).set_index("paragraph_id") for r in (LLM_RUN, STABILITY_RUN, f"{LLM_RUN}_final")}
    added = []
    for f in failures:
        if f["verdict"] != "human_label_debatable":
            continue
        field = f["field"].split(" ")[0]  # "novelty (stability)" -> "novelty"
        if ((disputes.paragraph_id == f["paragraph_id"]) & (disputes.field == field)).any():
            continue
        human = runs[LLM_RUN].at[f["paragraph_id"], f"{field}_human"]
        # The disputed LLM value: the one that differs from the human label (for the stability row,
        # the repeat run and the rule-applied scored run).
        values = {r: runs[r].at[f["paragraph_id"], f"{field}_llm"] for r in runs}
        llm_value = next(v for v in values.values() if str(v) != str(human))
        agreeing = [r for r, v in values.items() if str(v) == str(llm_value)]
        fmt_v = (lambda v: str(v).upper()) if field == "mentions_ai" else str  # match existing TRUE/FALSE style
        added.append({"paragraph_id": f["paragraph_id"], "field": field, "human_value": fmt_v(human),
                      "llm_value": fmt_v(llm_value), "models_agreeing": "; ".join(agreeing),
                      "note": f"{AFTER_SCORING_NOTE}. {f['why']}"})
    if added or removed:
        pd.concat([disputes, pd.DataFrame(added)], ignore_index=True).to_csv(DISPUTES_PATH, index=False)
    return added, removed


def pct_short(r):
    value = r.get("value", r.get("accuracy"))
    return "n/a" if value is None else f"{100 * value:.1f}%"


def headline_rows(res):
    """(label, rate-or-number) pairs shown in the raw-vs-final table."""
    n = res["novelty"]["llm"]
    return [("Category accuracy", res["category"]["accuracy_all"]), ("Novelty precision", n["precision"]),
            ("Novelty recall", n["recall"]), ("Novelty F1", n["f1"]),
            ("Severity exact", res["severity"]["exact"]), ("Severity within 1", res["severity"]["within_1"]),
            ("mentions_ai agreement", res["mentions_ai"]["agreement"])]


def write_report(results):
    fin, raw, meta, failures = results["final"], results["raw"], results["meta"], results["failures"]
    c, n, sv, ai, q, da, st = (fin[k] for k in ("category", "novelty", "severity", "mentions_ai", "quote",
                                                 "dispute_adjusted", "stability"))
    L = ["# Evaluation report: LLM labels vs human gold labels", "",
         "## How to read this", "",
         f"- **Test set:** {c['accuracy_all']['n']} hand-labelled candidate paragraphs, held out from prompt development.",
         f"- **Only the first run is scored** (`{LLM_RUN}`). A second labelling of the same rows "
         f"(`{STABILITY_RUN}`) is used only to show run-to-run stability.",
         "- **Headline numbers are for the shipped pipeline:** the scored run after `apply_rules.py` enforces the "
         "codebook rule \"if uncertain about novelty, label reworded\" (`" + fin["run"] + "`). "
         "Raw-vs-final is shown below.",
         "- **Strict numbers use the frozen human labels**, even where the LLM looks right. "
         "Dispute-adjusted numbers (secondary) drop rows listed in `gold_disputes.csv`.",
         "- Intervals are 95% Wilson score intervals; with 40 rows they are wide.", "",
         f"Model `{meta['model']}`, prompt {meta['prompt_version']} (hash `{meta['prompt_hash'][:12]}`), "
         f"codebook v{meta['codebook_version']}, gold sheet SHA-256 `{meta['gold_sha256'][:12]}`.", "",
         "## Raw vs final (rule applied)", "",
         f"The rule changed {results['rule_changes']['count']} test row(s): {', '.join(results['rule_changes']['rows']) or 'none'}.", "",
         "| metric | raw (`" + raw["run"] + "`) | final (`" + fin["run"] + "`) |", "|---|---|---|"]
    for (label, r), (_, f) in zip(headline_rows(raw), headline_rows(fin)):
        L.append(f"| {label} | {num(r) if not isinstance(r, dict) else pct(r)} | {num(f) if not isinstance(f, dict) else pct(f)} |")

    L += ["", "## Category", "",
          "| | result |", "|---|---|",
          f"| Accuracy, all rows | {pct(c['accuracy_all'])} |",
          f"| Accuracy, real risks only | {pct(c['accuracy_risks_only'])} |", "",
          "| category | support | predicted | precision | recall | F1 |", "|---|---|---|---|---|---|"]
    L += [f"| {m['category']} | {m['support']} | {m['predicted']} | {num(m['precision'])} | {num(m['recall'])} | {num(m['f1'])} |"
          for m in c["per_category"]]
    labels = c["confusion"]["labels"]
    L += ["", "Confusion matrix (rows = human, columns = LLM):", "",
          "| human \\ LLM | " + " | ".join(labels) + " |", "|---" * (len(labels) + 1) + "|"]
    L += [f"| {lab} | " + " | ".join(str(v) if v else "·" for v in row) + " |"
          for lab, row in zip(labels, c["confusion"]["matrix"])]
    L += ["", f"Disagreements ({len(c['errors'])}):", "", "| paragraph | human | LLM | LLM reason |", "|---|---|---|---|"]
    L += [f"| {e['paragraph_id']} | {e['human']} | {e['llm']} | {e['reason']} |" for e in c["errors"]]

    L += ["", "## Novelty (genuinely new vs reworded)", "",
          f"Scored on the {n['rows']} test rows the human labelled as a risk; {n['human_genuinely_new']} are genuinely new. "
          "Agreement is shown for completeness but is not the headline metric: always answering \"reworded\" scores "
          f"{100 * n['baselines']['always_reworded']['agreement']['value']:.0f}%.", "",
          "| method | precision | recall | F1 | agreement |", "|---|---|---|---|---|"]
    for name, m in (("**LLM (final)**", n["llm"]), ("Always \"reworded\"", n["baselines"]["always_reworded"]),
                    ("TF-IDF only (status = new)", n["baselines"]["tfidf_only"])):
        L.append(f"| {name} | {pct(m['precision'])} | {pct(m['recall'])} | {num(m['f1'])} | {pct(m['agreement'])} |")
    m = n["llm"]
    L += ["", f"LLM confusion: TP {m['tp']}, FP {m['fp']}, FN {m['fn']}, TN {m['tn']}."]
    for key, title in (("false_negatives", "False negatives"), ("false_positives", "False positives")):
        if n[key]:
            L += ["", f"{title}:", "", "| paragraph | TF-IDF | best_sim | LLM uncertain | LLM reason |", "|---|---|---|---|---|"]
            L += [f"| {e['paragraph_id']} | {e['tfidf_status']} | {e['best_sim']} | {e['llm_novelty_uncertain']} | {e['reason']} |"
                  for e in n[key]]

    L += ["", "## Severity", "", f"Rows where both human and LLM gave a severity: {sv['rows']}.", "",
          "| | result |", "|---|---|",
          f"| Exact agreement | {pct(sv['exact'])} |", f"| Within one level | {pct(sv['within_1'])} |",
          f"| LLM rated higher / lower than human | {sv['llm_higher']} / {sv['llm_lower']} |", "",
          "| human \\ LLM | 1 | 2 | 3 |", "|---|---|---|---|"]
    L += [f"| {lab} | " + " | ".join(str(v) for v in row) + " |" for lab, row in zip((1, 2, 3), sv["confusion"]["matrix"])]

    L += ["", "## AI mentions (`mentions_ai`)", "", f"All {ai['rows']} rows; TRUE is the positive class.", "",
          "| | result |", "|---|---|", f"| Agreement | {pct(ai['agreement'])} |",
          f"| Precision | {pct(ai['precision'])} |", f"| Recall | {pct(ai['recall'])} |", "",
          f"TP {ai['tp']}, FP {ai['fp']}, FN {ai['fn']}, TN {ai['tn']}."]

    L += ["", "## Quote check", "",
          f"Share of LLM proof quotes found verbatim in the paragraph (after normalising whitespace, quotes and dashes): "
          f"{pct(q)}."]

    L += ["", "## Top 5 cases", "", "Chosen during error review to show distinct failure types.", ""]
    for i, f in enumerate(failures, start=1):
        L += [f"**{i}. {f['paragraph_id']} — {f['field']}** (human `{f['human_value']}`, LLM `{f['llm_value']}`; "
              f"verdict: {f['verdict'].replace('_', ' ')})", "", f"{f['why']}", "", f"> {f['evidence']}", ""]

    excl = {k: len(v) for k, v in da["excluded_rows"].items()}
    L += ["## Dispute-adjusted (secondary)", "",
          f"Rows excluded per field: category {excl['category']}, novelty {excl['novelty']}, "
          f"severity {excl['severity']}, mentions_ai {excl['mentions_ai']}."]
    if da["added_after_scoring"]:
        L += ["", "Test rows added to `gold_disputes.csv` **after scoring** (during error review): "
              + ", ".join(f"{d['paragraph_id']} ({d['field']})" for d in da["added_after_scoring"])
              + ". The strict numbers above are unaffected."]
    L += ["", "| metric | strict | dispute-adjusted |", "|---|---|---|"]
    names = {"category_accuracy": "Category accuracy", "novelty_precision": "Novelty precision",
             "novelty_recall": "Novelty recall", "severity_exact": "Severity exact", "mentions_ai_agreement": "mentions_ai agreement"}
    L += [f"| {names[k]} | {pct(da['strict'][k])} | {pct(da['adjusted'][k])} |" for k in names]

    L += ["", "## Stability (run-to-run)", "",
          f"Agreement between `{st['runs'][0]}` and `{st['runs'][1]}` on the same {c['accuracy_all']['n']} rows:", "",
          "| field | agreement |", "|---|---|"]
    L += [f"| {f} | {pct(r)} |" for f, r in st["agreement"].items()]
    r2 = st["rep2_novelty"]
    L += ["", f"Novelty on the repeat run against the human labels (stability check, not a score): "
          f"precision {pct(r2['precision'])}, recall {pct(r2['recall'])}.", ""]
    REPORT_PATH.write_text("\n".join(L))


def print_extra(res):
    sv, ai, q, da, st = res["severity"], res["mentions_ai"], res["quote"], res["dispute_adjusted"], res["stability"]
    print(f"\n=== Severity ({sv['rows']} rows) ===\nexact {pct(sv['exact'])}\nwithin 1 {pct(sv['within_1'])}\n"
          f"LLM higher {sv['llm_higher']}, lower {sv['llm_lower']}\nconfusion (rows human 1-3, cols LLM 1-3): {sv['confusion']['matrix']}")
    print(f"\n=== mentions_ai ({ai['rows']} rows) ===\nTP {ai['tp']} FP {ai['fp']} FN {ai['fn']} TN {ai['tn']}\n"
          f"agreement {pct(ai['agreement'])}\nprecision {pct(ai['precision'])}\nrecall {pct(ai['recall'])}")
    print(f"\n=== Quote check ===\n{pct(q)}")
    print("\n=== Dispute-adjusted ===\nexcluded:", {f: len(v) for f, v in da["excluded_rows"].items()})
    for k in da["strict"]:
        print(f"  {k:24} strict {pct(da['strict'][k])}  |  adjusted {pct(da['adjusted'][k])}")
    print("\n=== Stability ===")
    for f, r in st["agreement"].items():
        print(f"  {f:12} {pct(r)}")
    print(f"  rep2 novelty precision {pct(st['rep2_novelty']['precision'])}, recall {pct(st['rep2_novelty']['recall'])}")


def print_novelty(res):
    print(f"\n=== Novelty ({res['rows']} rows where human category != not_a_risk; "
          f"{res['human_genuinely_new']} human genuinely_new; "
          f"{res['llm_na_scored_as_reworded']} LLM n/a scored as reworded) ===")
    m = res["llm"]
    print(f"LLM: TP {m['tp']}  FP {m['fp']}  FN {m['fn']}  TN {m['tn']}")

    def cell(r):
        if r["value"] is None:
            return f"  –   ({r['k']}/{r['n']})"
        return f"{r['value']:.3f} ({r['k']}/{r['n']}, CI {r['ci95'][0]:.2f}–{r['ci95'][1]:.2f})"
    print(f"\n{'method':18}{'precision':>30}{'recall':>30}{'f1':>8}{'agreement':>30}")
    for name, x in (("LLM", m), ("always reworded", res["baselines"]["always_reworded"]),
                    ("TF-IDF only", res["baselines"]["tfidf_only"])):
        print(f"{name:18}{cell(x['precision']):>30}{cell(x['recall']):>30}{fmt(x['f1']):>8}{cell(x['agreement']):>30}")
    for key, name in (("false_negatives", "False negatives (human new, LLM reworded)"),
                      ("false_positives", "False positives (LLM new, human reworded)")):
        print(f"\n{name}: {len(res[key])}")
        for e in res[key]:
            print(f"  {e['paragraph_id']} ({e['ticker']}) human_cat={e['human_category']} tfidf={e['tfidf_status']} "
                  f"best_sim={e['best_sim']} llm_uncertain={e['llm_novelty_uncertain']}\n"
                  f"    reason: {e['reason']}\n    text:   {e['text']!r}")


def fmt(x):
    return "  –  " if x is None else f"{x:.3f}"


def print_category(res):
    for key, name in (("accuracy_all", "all rows"), ("accuracy_risks_only", "risks only (human != not_a_risk)")):
        a = res[key]
        print(f"Accuracy, {name}: {a['correct']}/{a['n']} = {a['accuracy']:.3f}  "
              f"(95% Wilson CI {a['ci95'][0]:.3f}–{a['ci95'][1]:.3f})")
    print(f"\n{'category':20}{'support':>8}{'pred':>6}{'prec':>8}{'recall':>8}{'f1':>8}")
    for m in res["per_category"]:
        print(f"{m['category']:20}{m['support']:>8}{m['predicted']:>6}{fmt(m['precision']):>8}"
              f"{fmt(m['recall']):>8}{fmt(m['f1']):>8}")
    labels, matrix = res["confusion"]["labels"], res["confusion"]["matrix"]
    short = [l[:8] for l in labels]
    print("\nConfusion (rows = human, columns = LLM):")
    print(" " * 20 + "".join(f"{s:>9}" for s in short))
    for label, row in zip(labels, matrix):
        print(f"{label:20}" + "".join(f"{v:>9}" for v in row))
    print(f"\nDisagreements ({len(res['errors'])}):")
    for e in res["errors"]:
        print(f"  {e['paragraph_id']} ({e['ticker']}): human={e['human']}  llm={e['llm']}\n"
              f"    reason: {e['reason']}\n    text:   {e['text']!r}")


def main():
    verify_gold_hash()
    failures = load_failures()
    added, removed = record_disputes(failures)
    raw = score_all(LLM_RUN, STABILITY_RUN)
    final = score_all(f"{LLM_RUN}_final", f"{STABILITY_RUN}_final")
    fin_labels = pd.read_csv(DATA_DIR / f"llm_labels_{LLM_RUN}_final.csv", dtype=str, keep_default_na=False)
    changed = sorted(fin_labels.loc[fin_labels.rule_applied.str.lower() == "true", "paragraph_id"])
    changed = [p for p in changed if p in set(load(LLM_RUN).paragraph_id)]
    results = {"meta": {**run_metadata(LLM_RUN), "gold_sha256": GOLD_HASH_PATH.read_text().split()[0]},
               **{k: v for k, v in raw.items() if k != "run"},  # raw numbers keep their original top-level keys
               "raw": raw, "final": final, "failures": failures,
               "rule_changes": {"count": len(changed), "rows": changed}}
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str) + "\n")
    write_report(results)
    print(f"disputes added after scoring: {[(a['paragraph_id'], a['field']) for a in added] or 'none'}; "
          f"removed (verdict changed): {removed or 'none'}")
    print(f"rule changed {len(changed)} test row(s): {changed}")
    print(f"\n{'metric':24}{'raw':>14}{'final':>14}")
    for (label, r), (_, f) in zip(headline_rows(raw), headline_rows(final)):
        show = lambda x: num(x) if not isinstance(x, dict) else f"{pct_short(x)} ({x.get('k', x.get('correct'))}/{x['n']})"
        print(f"{label:24}{show(r):>14}{show(f):>14}")
    print_novelty(final["novelty"])
    print(f"\nwrote {RESULTS_PATH} and {REPORT_PATH}")


if __name__ == "__main__":
    main()
