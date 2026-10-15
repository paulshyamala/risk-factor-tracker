"""Label candidate risk units with Claude, following codebook.md.

Modes: --dev / --test label the gold rows (inputs taken from the frozen gold sheet, so the model sees
exactly what the human labeller saw); --all labels every TF-IDF candidate in paragraphs.csv.
Every API call is logged to data/llm_runs/<run_name>.jsonl; parsed labels go to
data/llm_labels_<run_name>.csv, and reruns skip paragraph_ids already there unless --force.
"""
import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import pandas as pd
from dotenv import load_dotenv

MODEL = "claude-sonnet-5-5"
# Requested 0, but claude-sonnet-5-5 and claude-haiku-5-5 reject any non-default temperature with a 400,
# so it is not sent (the API default of 1 applies). Output is constrained by the enum-valued tool instead.
TEMPERATURE = None
MAX_TOKENS = 1500
PROMPT_VERSION = "v1"
# These models return a 400 on a forced tool_choice; for them the tool is offered with tool_choice
# "auto" plus strict schema validation (the user message already says to answer with the tool).
NO_FORCED_TOOL = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1", "claude-mythos-5-1"}
# Per-model request extras. Sonnet 5.5 can't disable thinking outright; "between_tools" turns it off
# for a single-step call like this, which keeps it comparable to Haiku (forced tool calls skip thinking).
MODEL_EXTRAS = {"claude-sonnet-5-5": {"thinking": {"type": "between_tools"}}}

PIPELINE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PIPELINE_DIR / "data"
CODEBOOK_PATH = PIPELINE_DIR.parent / "codebook.md"
GOLD_PATH = DATA_DIR / "gold_labels.xlsx"
GOLD_HASH_PATH = DATA_DIR / "gold_labels.sha256"
RUNS_DIR = DATA_DIR / "llm_runs"

CATEGORIES = ["tariffs/trade", "AI/tech", "cyber/data privacy", "credit/liquidity", "regulation/legal",
              "competition", "M&A/transactions", "macro", "other", "not_a_risk"]
NOVELTY = ["genuinely_new", "reworded"]
SEVERITY = [1, 2, 3]
OUT_COLUMNS = ["paragraph_id", "ticker", "category", "novelty", "novelty_uncertain", "severity",
               "mentions_ai", "proof", "quote_valid", "reason", "status"]

ROLE = ("You label risk-factor paragraphs from SEC 10-K filings according to the codebook below. "
        "Follow the codebook exactly.")

TOOL = {
    "name": "record_label",
    "description": "Record the codebook labels for the current-year paragraph.",
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": CATEGORIES},
            "novelty": {"anyOf": [{"type": "string", "enum": NOVELTY}, {"type": "null"}],
                        "description": "null only when category is not_a_risk"},
            "novelty_uncertain": {"type": "boolean"},
            "severity": {"anyOf": [{"type": "integer", "enum": SEVERITY}, {"type": "null"}],
                         "description": "null only when category is not_a_risk"},
            "mentions_ai": {"type": "boolean"},
            "proof": {"type": "string",
                      "description": "One complete sentence copied exactly from the current-year paragraph"},
            "reason": {"type": "string", "description": "One short sentence"},
        },
        "required": ["category", "novelty", "novelty_uncertain", "severity", "mentions_ai", "proof", "reason"],
        "additionalProperties": False,
    },
}

INSTRUCTIONS = """Instructions:
- All labels describe the CURRENT-YEAR paragraph only.
- Use the prior-year matches only to decide novelty, following the codebook's Labelling notes.
- If unsure about novelty, label reworded and set novelty_uncertain to true.
- For not_a_risk, set novelty and severity to null.
- proof: copy exactly one complete sentence from the current-year paragraph, character for character, that best supports the category. Do not paraphrase or fix typos.
- reason: one short sentence.
Record your answer with the record_label tool."""


def load_codebook():
    text = CODEBOOK_PATH.read_text()
    version = re.search(r"\*\*Version:\*\*\s*([\d.]+)", text)
    return text, version.group(1) if version else "unknown"


def verify_gold_hash():
    expected = GOLD_HASH_PATH.read_text().split()[0]
    actual = hashlib.sha256(GOLD_PATH.read_bytes()).hexdigest()
    if actual != expected:
        sys.exit(f"ABORT: {GOLD_PATH.name} does not match {GOLD_HASH_PATH.name}\n"
                 f"  expected {expected}\n  actual   {actual}\n"
                 "The frozen human labels have changed. Re-validate and re-snapshot before labelling.")


def build_user_message(row):
    parts = [f"Company: {row['ticker']}",
             f"Section heading: {row['section'] or '(none)'}",
             "",
             "<current_year_paragraph>", row["text"], "</current_year_paragraph>", ""]
    for k in (1, 2, 3):
        parts += [f"<prior_year_match_{k}>", row[f"match_{k}"] or "(none)", f"</prior_year_match_{k}>", ""]
    parts.append(INSTRUCTIONS)
    return "\n".join(parts)


def prompt_hash(system):
    """SHA-256 of the system prompt plus the user-message template (filled with fixed placeholders),
    so any change to the prompt wording or layout changes the hash."""
    placeholder = {"ticker": "{ticker}", "section": "{section}", "text": "{text}",
                   "match_1": "{match_1}", "match_2": "{match_2}", "match_3": "{match_3}"}
    payload = system[0]["text"] + "\n<<USER_TEMPLATE>>\n" + build_user_message(placeholder)
    return hashlib.sha256(payload.encode()).hexdigest()


def validate(label):
    """Return a list of problems with a record_label input (empty if valid)."""
    problems = []
    if label.get("category") not in CATEGORIES:
        problems.append(f"category {label.get('category')!r}")
    for field in ("novelty_uncertain", "mentions_ai"):
        if not isinstance(label.get(field), bool):
            problems.append(f"{field} {label.get(field)!r}")
    for field in ("proof", "reason"):
        if not isinstance(label.get(field), str) or not label.get(field).strip():
            problems.append(f"{field} empty")
    novelty, severity = label.get("novelty"), label.get("severity")
    if label.get("category") == "not_a_risk":
        if novelty is not None or severity is not None:
            problems.append("not_a_risk must have null novelty and severity")
    else:
        if novelty not in NOVELTY:
            problems.append(f"novelty {novelty!r}")
        if severity not in SEVERITY or isinstance(severity, bool):
            problems.append(f"severity {severity!r}")
    return problems


def normalise(text):
    text = text.translate(str.maketrans({"‘": "'", "’": "'", "‛": "'", "′": "'", "“": '"', "”": '"',
                                         "„": '"', "″": '"', "–": "-", "—": "-", "‑": "-", " ": " "}))
    return re.sub(r"\s+", " ", text).strip()


def quote_valid(proof, text):
    return bool(proof) and normalise(proof) in normalise(text)


def request_options(model):
    """tools / tool_choice / extras for a model; see NO_FORCED_TOOL and MODEL_EXTRAS."""
    if model in NO_FORCED_TOOL:
        opts = {"tools": [{**TOOL, "strict": True}], "tool_choice": {"type": "auto"}}
    else:
        opts = {"tools": [TOOL], "tool_choice": {"type": "tool", "name": "record_label"}}
    return {**opts, **MODEL_EXTRAS.get(model, {})}


def model_short_name(model):
    """claude-haiku-5-5 -> haiku"""
    m = re.match(r"claude-([a-z]+)", model)
    return m.group(1) if m else model


def call_once(client, system, row, model):
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        **request_options(model),
        messages=[{"role": "user", "content": build_user_message(row)}],
    )
    tool_use = next((b for b in response.content if b.type == "tool_use"), None)
    label = dict(tool_use.input) if tool_use else None
    problems = validate(label) if label else [f"no tool call (stop_reason={response.stop_reason})"]
    return response, label, problems


def usage_dict(response):
    u = response.usage
    return {"input": u.input_tokens, "output": u.output_tokens,
            "cache_read": u.cache_read_input_tokens or 0, "cache_write": u.cache_creation_input_tokens or 0}


def label_row(client, system, row, log, codebook_version, totals, model, p_hash):
    """Label one row, retrying once on invalid output. Returns the output-CSV record."""
    for attempt in (1, 2):
        response, label, problems = call_once(client, system, row, model)
        usage = usage_dict(response)
        for k, v in usage.items():
            totals[k] += v
        status = "ok" if not problems else ("invalid" if attempt == 1 else "error")
        log.write(json.dumps({
            "paragraph_id": row["paragraph_id"],
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": response.model, "model_requested": model, "request_id": response._request_id,
            "tool_choice": request_options(model)["tool_choice"]["type"],
            "prompt_version": PROMPT_VERSION, "prompt_hash": p_hash, "codebook_version": codebook_version,
            "temperature": TEMPERATURE if TEMPERATURE is not None else "api_default",
            "attempt": attempt, "stop_reason": response.stop_reason,
            "tool_input": label, "raw_content": None if label else [b.model_dump() for b in response.content],
            "usage": usage, "status": status, "problems": problems,
        }) + "\n")
        log.flush()
        if not problems:
            break
    record = {"paragraph_id": row["paragraph_id"], "ticker": row["ticker"], "status": status}
    if label:
        record.update({k: label.get(k) for k in ("category", "novelty", "novelty_uncertain", "severity",
                                                  "mentions_ai", "proof", "reason")})
        record["quote_valid"] = quote_valid(label.get("proof"), row["text"])
    return record


def load_rows(args):
    """Rows to label, each with paragraph_id, ticker, section, text, match_1..3 (and split for gold)."""
    if args.dev or args.test:
        verify_gold_hash()
        gold = pd.read_excel(GOLD_PATH, dtype=object, keep_default_na=False)
        rows = gold[gold.split == ("dev" if args.dev else "test")]
        # Warn if paragraphs.csv has drifted from the frozen sheet (ids are positional).
        paras = pd.read_csv(DATA_DIR / "paragraphs.csv").set_index("paragraph_id").text
        drifted = [p for p, t in zip(rows.paragraph_id, rows.text) if paras.get(p) != t]
        if drifted:
            print(f"WARNING: {len(drifted)} gold rows differ from paragraphs.csv; using the gold sheet text.")
    else:
        paras = pd.read_csv(DATA_DIR / "paragraphs.csv", keep_default_na=False)
        rows = paras[(paras.pair_position == "latest") & paras.status.isin(["new", "modified"])]
    if args.ids:
        rows = rows[rows.paragraph_id.isin(args.ids)]
    if args.limit:
        rows = rows.head(args.limit)
    return rows


def compare_with_gold(results, gold):
    """Per-field agreement with the human labels, then every disagreement."""
    def canon(field, v):
        """Bring CSV strings (LLM) and Excel cells (human) to one form; n/a and blanks -> None."""
        if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() in ("", "n/a", "nan"):
            return None
        if field == "severity":
            return int(float(v))
        if field == "mentions_ai":
            return v if isinstance(v, bool) else str(v).strip().lower() == "true"
        return str(v).strip()
    merged = results[results.status == "ok"].merge(gold, on="paragraph_id", suffixes=("_llm", "_human"))
    n = len(merged)
    print(f"\nAgreement with human labels ({n} rows labelled ok):")
    disagreements = []
    for field in ("category", "novelty", "severity", "mentions_ai"):
        # Plain lists, not Series.map: pandas would turn None into NaN, and NaN != NaN.
        llm = [canon(field, v) for v in merged[f"{field}_llm"]]
        hum = [canon(field, v) for v in merged[f"{field}_human"]]
        agree = [a == b for a, b in zip(llm, hum)]
        print(f"  {field:12} {sum(agree)}/{n}")
        for i, ok in enumerate(agree):
            if not ok:
                disagreements.append((merged.paragraph_id.iat[i], field, hum[i], llm[i],
                                      merged.reason.iat[i], merged.text.iat[i][:150]))
    if disagreements:
        print("\nDisagreements:")
        for pid, field, h, l, reason, text in disagreements:
            print(f"  {pid}  {field}: human={h!r}  llm={l!r}\n    reason: {reason}\n    text:   {text!r}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dev", action="store_true", help="label the 20 dev rows of the gold set")
    mode.add_argument("--test", action="store_true", help="label the 40 test rows (needs --confirm-test)")
    mode.add_argument("--all", action="store_true", help="label every TF-IDF candidate")
    parser.add_argument("--confirm-test", action="store_true", help="required with --test")
    parser.add_argument("--limit", type=int, help="label at most N rows")
    parser.add_argument("--ids", nargs="+", help="label only these paragraph_ids")
    parser.add_argument("--model", default=MODEL, help=f"Claude model id (default {MODEL})")
    parser.add_argument("--run-name", help="default: <mode>_<PROMPT_VERSION>_<model short name>")
    parser.add_argument("--force", action="store_true", help="relabel ids already in the output CSV")
    args = parser.parse_args()
    if args.test and not args.confirm_test:
        parser.error("--test evaluates the held-out set; pass --confirm-test to run it")

    mode_name = "dev" if args.dev else "test" if args.test else "all"
    run_name = args.run_name or f"{mode_name}_{PROMPT_VERSION}_{model_short_name(args.model)}"
    out_path = DATA_DIR / f"llm_labels_{run_name}.csv"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    rows = load_rows(args)
    done = pd.read_csv(out_path, dtype=object) if out_path.exists() else pd.DataFrame(columns=OUT_COLUMNS)
    if args.force:
        done = done[~done.paragraph_id.isin(rows.paragraph_id)]
    todo = rows[~rows.paragraph_id.isin(done.paragraph_id)]
    print(f"run {run_name} ({args.model}): {len(rows)} rows selected, {len(rows) - len(todo)} already labelled, {len(todo)} to label")

    load_dotenv(PIPELINE_DIR / ".env", override=True)
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=5)  # SDK backs off exponentially
    codebook, codebook_version = load_codebook()
    system = [{"type": "text", "text": f"{ROLE}\n\n{codebook}", "cache_control": {"type": "ephemeral"}}]
    p_hash = prompt_hash(system)
    print(f"prompt {PROMPT_VERSION}, hash {p_hash[:12]}, codebook {codebook_version}")

    totals = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
    records = done.to_dict("records")
    with open(RUNS_DIR / f"{run_name}.jsonl", "a") as log:
        for i, row in enumerate(todo.to_dict("records"), start=1):
            try:
                record = label_row(client, system, row, log, codebook_version, totals, args.model, p_hash)
            except (anthropic.BadRequestError, anthropic.AuthenticationError,
                    anthropic.PermissionDeniedError, anthropic.NotFoundError):
                raise  # configuration problems: every remaining call would fail the same way
            except anthropic.APIError as e:  # retries exhausted (429 / 5xx / connection)
                record = {"paragraph_id": row["paragraph_id"], "ticker": row["ticker"], "status": "error"}
                log.write(json.dumps({"paragraph_id": row["paragraph_id"], "status": "error", "prompt_hash": p_hash,
                                      "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                      "error": f"{type(e).__name__}: {e}"}) + "\n")
            records.append(record)
            pd.DataFrame(records).reindex(columns=OUT_COLUMNS).to_csv(out_path, index=False)  # save as we go
            print(f"  [{i}/{len(todo)}] {row['paragraph_id']}: {record.get('category')} / {record.get('novelty')} "
                  f"/ sev {record.get('severity')} / quote_valid={record.get('quote_valid')} ({record['status']})")

    print(f"\ntokens: input {totals['input']:,}, output {totals['output']:,}, "
          f"cache read {totals['cache_read']:,}, cache write {totals['cache_write']:,}")
    print(f"wrote {out_path}")

    if args.dev:
        results = pd.read_csv(out_path, dtype=object)
        results = results[results.paragraph_id.isin(rows.paragraph_id)]
        gold = pd.read_excel(GOLD_PATH, dtype=object, keep_default_na=False)
        compare_with_gold(results, gold[["paragraph_id", "category", "novelty", "severity", "mentions_ai", "text"]])


if __name__ == "__main__":
    main()
