"""Download 10-K filings via edgartools and store Item 1A (Risk Factors) text in data/filings.db."""
import argparse
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from edgar import Company, set_identity

set_identity("Paul Shyamala p4reddy@uwaterloo.ca")

TICKERS = [
    # Canadian 10-K filers
    "SHOP", "CP", "QSR", "LULU", "WCN",
    # Rail
    "UNP", "CSX", "NSC",
    # Restaurants
    "MCD", "YUM", "DPZ", "WEN", "CMG", "SBUX",
    # Waste
    "WM", "RSG",
    # Apparel
    "NKE", "GAP", "UAA", "VFC",
    # E-commerce / payments
    "AMZN", "EBAY", "ETSY", "PYPL", "XYZ",
]
TEST_TICKERS = ["SHOP", "CP"]

MIN_CHARS = 15_000
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "filings.db"

# Headings must start a line, so in-text cross-references ("see Item 1A") don't match.
START_RE = re.compile(r"^\W*item\s*1a\b", re.I | re.M)
END_RE = re.compile(r"^\W*item\s*(1b|1c|2)\b", re.I | re.M)


def slice_item_1a(full_text):
    """Slice Item 1A out of the full filing text. The table of contents also lists
    Item 1A -> Item 1B, but that slice is tiny, so keep the longest candidate."""
    best = ""
    for start in START_RE.finditer(full_text):
        end = END_RE.search(full_text, start.end())
        candidate = full_text[start.start():end.start() if end else len(full_text)]
        if end and len(candidate) > len(best):
            best = candidate
    return best.strip()


PAGE_NUM_RE = re.compile(r"^(page\s*)?[-–—]?\s*\d{1,4}\s*[-–—]?$", re.I)
# "16 / CPKC 2025 Annual Report" and "CPKC 2025 Annual Report / 17" -> same footer key.
FOOTER_PAGE_RE = re.compile(r"^\d{1,4}\s*/\s*|\s*/\s*\d{1,4}$")
# Letter-prefixed page labels such as "K11" or "K-12" (NSC), alone or fused to the next line.
PAGE_LABEL_RE = re.compile(r"^[A-Z]-?\d{1,3}$")
FUSED_LABEL_RE = re.compile(r"^[A-Z]-?\d{1,3}\s+(?=[a-z])")
TERMINAL = tuple('.!?:;"”)')


def footer_key(line):
    return re.sub(r"\s+", " ", FOOTER_PAGE_RE.sub("", line.strip())).lower()


def clean_text(raw):
    """Strip page footers and re-join paragraphs split by page breaks.
    Returns (clean_text, footer_lines_removed, paragraph_merges)."""
    lines = [line.rstrip() for line in raw.split("\n")]
    counts = {}
    for line in lines:
        if line.strip() and len(line.strip()) < 80:
            counts[footer_key(line)] = counts.get(footer_key(line), 0) + 1

    kept, removed = [], 0
    for line in lines:
        s = line.strip()
        if s and (re.sub(r"\s", "", s).lower() == "tableofcontents"
                  or PAGE_NUM_RE.match(s)
                  or PAGE_LABEL_RE.match(s)
                  or (len(s) < 80 and counts[footer_key(line)] >= 5)):
            removed += 1
        elif FUSED_LABEL_RE.match(s):
            kept.append(FUSED_LABEL_RE.sub("", s))
            removed += 1
        else:
            kept.append(line)

    # A removed footer leaves a blank-line gap mid-sentence; merge across it when the
    # first block has no terminal punctuation and the next continues in lowercase.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", "\n".join(kept)) if b.strip()]
    merged, merges = [], 0
    for block in blocks:
        if merged and not merged[-1].endswith(TERMINAL) and block[0].islower():
            merged[-1] += " " + block
            merges += 1
        else:
            merged.append(block)
    text = re.sub(r"\n{3,}", "\n\n", "\n\n".join(merged))
    return text, removed, merges


def extract_risk_factors(filing):
    tenk = filing.obj()
    text = tenk.risk_factors
    if not text:
        # Returns None today but raises SectionNotFoundError from edgartools 6.0.
        try:
            text = tenk["Item 1A"]
        except Exception:
            text = None
    if text and len(text) >= MIN_CHARS:
        return text, "edgartools"
    fallback = slice_item_1a(filing.text())
    # Keep whichever is longer, so a failed fallback never discards a usable short section.
    if len(fallback) > len(text or ""):
        return fallback, "fallback"
    return text or "", "edgartools"


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS filings (
            ticker TEXT, accession_no TEXT, form TEXT, filing_date TEXT,
            period_of_report TEXT, fiscal_year INTEGER, text TEXT, char_len INTEGER,
            extraction_method TEXT, fetched_at TEXT, text_clean TEXT, char_len_clean INTEGER,
            pair_position TEXT,
            PRIMARY KEY (ticker, accession_no)
        )""")
    # Add the cleaning columns to databases created before they existed.
    existing = {row[1] for row in conn.execute("PRAGMA table_info(filings)")}
    for col, kind in [("text_clean", "TEXT"), ("char_len_clean", "INTEGER"), ("pair_position", "TEXT")]:
        if col not in existing:
            conn.execute(f"ALTER TABLE filings ADD COLUMN {col} {kind}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ticker_pair ON filings (ticker, pair_position)")


def save(conn, row):
    cols = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    updates = ", ".join(f"{c} = excluded.{c}" for c in row if c not in ("ticker", "accession_no"))
    conn.execute(
        f"INSERT INTO filings ({cols}) VALUES ({placeholders}) "
        f"ON CONFLICT (ticker, accession_no) DO UPDATE SET {updates}",
        list(row.values()),
    )
    conn.commit()


def fetch_ticker(conn, ticker):
    filings = [f for f in Company(ticker).get_filings(form="10-K") if f.form == "10-K"]
    filings = sorted(filings, key=lambda f: str(f.filing_date), reverse=True)[:2]
    if not filings:
        raise ValueError("no 10-K filings found")
    for filing, position in zip(filings, ["latest", "prior"]):
        text, method = extract_risk_factors(filing)
        clean, removed, merges = clean_text(text)
        period = str(filing.period_of_report)
        save(conn, {
            "ticker": ticker,
            "accession_no": filing.accession_no,
            "form": filing.form,
            "filing_date": str(filing.filing_date),
            "period_of_report": period,
            "fiscal_year": int(period[:4]),
            "text": text,
            "char_len": len(text),
            "extraction_method": method,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "text_clean": clean,
            "char_len_clean": len(clean),
            "pair_position": position,
        })
        print(f"  {ticker} {filing.filing_date}: {len(text):,} chars ({method}); "
              f"cleaned: {removed} footer lines removed, {merges} paragraph merges")
    # Older rows left over from earlier runs (e.g. once a newer 10-K appears) drop out of the pair.
    keep = [f.accession_no for f in filings]
    conn.execute(
        f"UPDATE filings SET pair_position = NULL WHERE ticker = ? "
        f"AND accession_no NOT IN ({','.join('?' for _ in keep)})",
        [ticker, *keep],
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--test", action="store_true", help="fetch TEST_TICKERS only")
    group.add_argument("--tickers", nargs="+", help="fetch only these tickers")
    args = parser.parse_args()
    tickers = TEST_TICKERS if args.test else [t.upper() for t in args.tickers] if args.tickers else TICKERS

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    failed = {}
    for ticker in tickers:
        print(f"Fetching {ticker}...")
        try:
            fetch_ticker(conn, ticker)
        except Exception as e:
            failed[ticker] = f"{type(e).__name__}: {e}"
            print(f"  FAILED {ticker}: {failed[ticker]}")

    rows = conn.execute(
        f"SELECT ticker, fiscal_year, filing_date, char_len, char_len_clean, extraction_method FROM filings "
        f"WHERE ticker IN ({','.join('?' for _ in tickers)}) ORDER BY ticker, filing_date DESC",
        tickers,
    ).fetchall()
    conn.close()

    print(f"\n{'ticker':<7}{'fy':<6}{'filed':<12}{'chars':>9}{'clean':>9}  method")
    for ticker, fy, filed, chars, clean, method in rows:
        flag = "  SHORT" if chars < MIN_CHARS else ""
        print(f"{ticker:<7}{fy:<6}{filed:<12}{chars:>9,}{clean or 0:>9,}  {method}{flag}")
    if failed:
        print("\nFailed tickers:")
        for ticker, err in failed.items():
            print(f"  {ticker}: {err}")


if __name__ == "__main__":
    main()
