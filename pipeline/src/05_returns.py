"""Abnormal stock returns after each company's latest 10-K, and whether they relate to how much its
Risk Factors changed.

Window: t+k is the k-th trading day after the filing date. Returns run from the close of t+1 to the
close of t+60 (adjusted closes). Abnormal return = stock return - SPY return over the same window.
Tickers whose t+60 hasn't happened yet are flagged incomplete and left out of the statistics.

Statistics, fixed in advance:
  primary   - Spearman correlation of change_score with abnormal return
  secondary - Spearman correlation of the genuinely-new risk count with abnormal return
"""
import sqlite3
from datetime import date
from pathlib import Path

import matplotlib
import pandas as pd
import yfinance as yf
from scipy.stats import spearmanr

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (backend must be set first)

WINDOW_START, WINDOW_END = 1, 60  # trading days after the filing date
BENCHMARK = "SPY"

PIPELINE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PIPELINE_DIR / "data"
CHART_PATH = PIPELINE_DIR.parent / "output" / "charts" / "returns_vs_changescore.png"
LABELS_PATH = DATA_DIR / "llm_labels_all_v1_sonnet_final.csv"


def load_inputs():
    with sqlite3.connect(DATA_DIR / "filings.db") as conn:
        filings = pd.read_sql("SELECT ticker, filing_date FROM filings WHERE pair_position = 'latest'", conn)
    scores = pd.read_csv(DATA_DIR / "change_scores.csv")[["ticker", "change_score"]]
    labels = pd.read_csv(LABELS_PATH, dtype=str, keep_default_na=False)
    new_counts = labels[labels.novelty == "genuinely_new"].groupby("ticker").size().rename("n_genuinely_new")
    df = filings.merge(scores, on="ticker", validate="1:1")
    df["n_genuinely_new"] = df.ticker.map(new_counts).fillna(0).astype(int)
    df["filing_date"] = pd.to_datetime(df.filing_date)
    return df


def download_prices(tickers, earliest_filing):
    # A few calendar days of slack before the earliest filing; yfinance's end date is exclusive.
    start = (earliest_filing - pd.Timedelta(days=10)).date()
    end = (pd.Timestamp(date.today()) + pd.Timedelta(days=1)).date()
    prices = yf.download(tickers + [BENCHMARK], start=start, end=end, auto_adjust=True, progress=False)["Close"]
    missing = [t for t in tickers + [BENCHMARK] if t not in prices.columns or prices[t].dropna().empty]
    if missing:
        raise SystemExit(f"ABORT: no price data for {missing}")
    return prices


def window_returns(row, prices):
    """Return over [t+1, t+60] for one ticker, plus the benchmark over the same dates."""
    days = prices[row.ticker].dropna().index
    after = days[days > row.filing_date]  # after[0] is t+1
    base = {"window_start": after[WINDOW_START - 1].date() if len(after) >= WINDOW_START else None}
    if len(after) < WINDOW_END:
        return {**base, "window_end": None, "stock_return": None, "spy_return": None,
                "abnormal_return_60d": None, "complete": False}
    start, end = after[WINDOW_START - 1], after[WINDOW_END - 1]
    stock = prices.at[end, row.ticker] / prices.at[start, row.ticker] - 1
    spy = prices.at[end, BENCHMARK] / prices.at[start, BENCHMARK] - 1
    return {**base, "window_end": end.date(), "stock_return": stock, "spy_return": spy,
            "abnormal_return_60d": stock - spy, "complete": True}


def correlate(df, x):
    rho, p = spearmanr(df[x], df.abnormal_return_60d)
    return {"x": x, "rho": float(rho), "p": float(p), "n": len(df)}


def plot(df, primary):
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.scatter(df.change_score, df.abnormal_return_60d * 100, color="#3b6ea5")
    for r in df.itertuples():
        ax.annotate(r.ticker, (r.change_score, r.abnormal_return_60d * 100), xytext=(4, 3),
                    textcoords="offset points", fontsize=8)
    ax.axhline(0, color="grey", linewidth=0.8)
    ax.set_xlabel("ChangeScore (1 − TF-IDF cosine similarity, latest vs prior Risk Factors)")
    ax.set_ylabel(f"Abnormal return vs {BENCHMARK}, t+{WINDOW_START} to t+{WINDOW_END} (%)")
    ax.set_title(f"Risk Factor change vs 60-day abnormal return\n"
                 f"Spearman ρ = {primary['rho']:.2f}, p = {primary['p']:.2f}, n = {primary['n']}")
    fig.tight_layout()
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CHART_PATH, dpi=150)


def main():
    df = load_inputs()
    prices = download_prices(sorted(df.ticker), df.filing_date.min())
    df = pd.concat([df, df.apply(lambda r: pd.Series(window_returns(r, prices)), axis=1)], axis=1)
    df["filing_date"] = df.filing_date.dt.date
    cols = ["ticker", "filing_date", "window_start", "window_end", "stock_return", "spy_return",
            "abnormal_return_60d", "change_score", "n_genuinely_new", "complete"]
    df[cols].sort_values("change_score", ascending=False).to_csv(DATA_DIR / "returns.csv", index=False)

    complete = df[df.complete].copy()
    excluded = sorted(df.loc[~df.complete, "ticker"])
    primary, secondary = correlate(complete, "change_score"), correlate(complete, "n_genuinely_new")
    plot(complete, primary)

    print(f"excluded (window not complete): {excluded or 'none'}")
    for name, c in (("primary", primary), ("secondary", secondary)):
        print(f"{name}: Spearman({c['x']}, abnormal return) rho = {c['rho']:.3f}, p = {c['p']:.3f}, n = {c['n']}")
    strength = "no clear" if primary["p"] >= 0.05 else ("a positive" if primary["rho"] > 0 else "a negative")
    print(f"\nAcross {primary['n']} companies and a single filing year, we found {strength} rank relationship "
          f"between how much a company's Risk Factors changed and its stock's return relative to SPY over the "
          f"60 trading days after filing (Spearman ρ = {primary['rho']:.2f}, p = {primary['p']:.2f}); with this "
          f"small sample the result is exploratory and says nothing about cause and effect.")
    print(f"\nwrote {DATA_DIR / 'returns.csv'} and {CHART_PATH}")


if __name__ == "__main__":
    main()
