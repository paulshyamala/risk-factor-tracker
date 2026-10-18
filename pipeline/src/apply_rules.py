"""Enforce codebook rules on LLM labels after labelling (post-processing, not a prompt change).

Rule (codebook §4, "Uncertain novelty"): if uncertain, label reworded. Any row with
novelty = genuinely_new and novelty_uncertain = true becomes novelty = reworded; novelty_uncertain
stays true. For every raw data/llm_labels_<run>.csv this writes data/llm_labels_<run>_final.csv with
an extra rule_applied column. Raw files are never modified.
"""
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def apply_rules(labels):
    out = labels.copy()
    uncertain = out.novelty_uncertain.astype(str).str.strip().str.lower() == "true"
    hit = (out.novelty == "genuinely_new") & uncertain
    out.loc[hit, "novelty"] = "reworded"
    out["rule_applied"] = hit
    return out, list(out.loc[hit, "paragraph_id"])


def main():
    for path in sorted(DATA_DIR.glob("llm_labels_*.csv")):
        if path.stem.endswith("_final"):
            continue
        labels = pd.read_csv(path, dtype=object, keep_default_na=False)
        final, changed = apply_rules(labels)
        out_path = path.with_name(f"{path.stem}_final.csv")
        final.to_csv(out_path, index=False)
        print(f"{path.stem.removeprefix('llm_labels_'):22} {len(changed)} row(s) changed {changed} -> {out_path.name}")


if __name__ == "__main__":
    main()
