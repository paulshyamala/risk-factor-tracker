"""Financials for the UNP memo -> output/model.xlsx (sheets Summary, Raw, Sources, ProForma).

UNP (memo company), CSX and CP (peers) for FY2023-2025, plus NSC FY2025 (merger counterparty, not a
peer) for pro forma leverage. Values are annual 10-K facts from SEC XBRL companyfacts (via edgartools);
UNP closing prices for the implied deal value come from yfinance. The ProForma sheet keeps inputs as
cells and everything derived as Excel formulas, so assumptions can be changed in the workbook.

Usage: python memo_financials.py [--out PATH]
"""
import argparse
from datetime import date
from pathlib import Path

import pandas as pd
import yfinance as yf
from edgar import Company, set_identity
from edgar.httprequests import download_json
from edgar.urls import build_company_facts_url
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font

set_identity("Paul Shyamala p4reddy@uwaterloo.ca")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "model.xlsx"
YEARS = [2023, 2024, 2025]
CURRENCY = {"UNP": "USD", "CSX": "USD", "CP": "CAD", "NSC": "USD"}
YEARS_BY_TICKER = {"NSC": [2025]}  # NSC is pulled only for pro forma leverage
ROLE = {"UNP": "memo company", "CSX": "peer", "CP": "peer", "NSC": "merger counterparty, not a peer"}

# Deal terms from Note 20 of UNP's FY2025 10-K (pipeline/data/unp_note20.txt).
SHARES_ISSUED_M = 224.8        # UNP shares to be issued, millions
CASH_PER_SHARE = 88.82         # cash per Norfolk Southern share, USD
CASH_CONSIDERATION_BN = 20.0   # "approximately $ 20 billion"
ANNOUNCEMENT = date(2025, 7, 29)

# metric -> (flow | instant, ordered tag alternatives; the first with an annual 10-K value wins)
METRICS = {
    "revenue": ("flow", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]),
    "operating_income": ("flow", ["OperatingIncomeLoss"]),
    "d_and_a": ("flow", ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization", "Depreciation"]),
    "net_income": ("flow", ["NetIncomeLoss"]),
    "diluted_eps": ("flow", ["EarningsPerShareDiluted"]),
    "operating_cash_flow": ("flow", ["NetCashProvidedByUsedInOperatingActivities"]),
    "capex": ("flow", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    "dividends_paid": ("flow", ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"]),
    "share_repurchases": ("flow", ["PaymentsForRepurchaseOfCommonStock"]),
    "debt_repaid": ("flow", ["RepaymentsOfDebtAndCapitalLeaseObligations", "RepaymentsOfLongTermDebt"]),
    "debt_noncurrent": ("instant", ["LongTermDebtAndCapitalLeaseObligations"]),
    "debt_current": ("instant", ["LongTermDebtAndCapitalLeaseObligationsCurrent"]),
    "cash": ("instant", ["CashAndCashEquivalentsAtCarryingValue",
                         "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"]),
}
NUM, RATIO = "#,##0.00", "0.00x"


def annual_fact(gaap, tag, kind, year, currency):
    """Latest-filed 10-K FY value for fiscal `year` (period ending in that year), or None."""
    unit_key = f"{currency}/shares" if tag == "EarningsPerShareDiluted" else currency
    keep = []
    for v in gaap.get(tag, {}).get("units", {}).get(unit_key, []):
        if v.get("form") != "10-K" or v.get("fp") != "FY" or not v["end"].startswith(str(year)):
            continue
        if kind == "flow":
            if "start" not in v:
                continue
            if not 350 <= (date.fromisoformat(v["end"]) - date.fromisoformat(v["start"])).days <= 380:
                continue
        elif "start" in v:
            continue
        keep.append(v)
    return max(keep, key=lambda v: v["filed"]) if keep else None, unit_key


def pull():
    raw, flags = [], []
    for t, cur in CURRENCY.items():
        gaap = download_json(build_company_facts_url(Company(t).cik))["facts"]["us-gaap"]
        for metric, (kind, tags) in METRICS.items():
            base = YEARS_BY_TICKER.get(t, YEARS)
            years = ([base[0] - 1] + base) if metric == "revenue" else base  # prior year for growth
            for y in years:
                hit = None
                for tag in tags:
                    fact, unit = annual_fact(gaap, tag, kind, y, cur)
                    if fact:
                        hit = (tag, fact, unit)
                        break
                if not hit:
                    flags.append(f"{t} {metric} FY{y}: no annual 10-K value under {tags}")
                    raw.append({"ticker": t, "fiscal_year": y, "metric": metric, "value": None, "tag": None,
                                "unit": None, "period_start": None, "period_end": None, "accession": None, "filed": None})
                    continue
                tag, f, unit = hit
                if tag != tags[0]:
                    flags.append(f"{t} {metric} FY{y}: used alternative tag {tag} (first choice {tags[0]} missing)")
                raw.append({"ticker": t, "fiscal_year": y, "metric": metric, "value": f["val"], "tag": f"us-gaap:{tag}",
                            "unit": unit, "period_start": f.get("start"), "period_end": f["end"],
                            "accession": f["accn"], "filed": f["filed"]})
    raw = pd.DataFrame(raw)
    raw.insert(1, "role", raw.ticker.map(ROLE))
    return raw, flags


def derive(raw):
    w = raw.pivot_table(index=["ticker", "fiscal_year"], columns="metric", values="value", aggfunc="first")
    rows = []
    for (t, y), r in w.iterrows():
        if y not in YEARS_BY_TICKER.get(t, YEARS):
            continue
        prev = w.loc[(t, y - 1), "revenue"] if (t, y - 1) in w.index else None
        debt = r.debt_noncurrent + r.debt_current
        ebitda = r.operating_income + r.d_and_a
        net_debt = debt - r.cash
        rows.append({
            "ticker": t, "role": ROLE[t], "fiscal_year": y, "currency": CURRENCY[t],
            "revenue": r.revenue, "revenue_growth": r.revenue / prev - 1 if prev else None,
            "operating_income": r.operating_income,
            "operating_ratio": (r.revenue - r.operating_income) / r.revenue,
            "ebitda": ebitda, "net_income": r.net_income, "diluted_eps": r.diluted_eps,
            "operating_cash_flow": r.operating_cash_flow, "capex": r.capex,
            "free_cash_flow": r.operating_cash_flow - r.capex,
            "dividends_paid": r.dividends_paid, "share_repurchases": r.share_repurchases,
            "total_debt": debt, "cash": r.cash, "net_debt": net_debt, "net_debt_to_ebitda": net_debt / ebitda,
        })
    return pd.DataFrame(rows)


def unp_closes():
    """(date, close) for the last close before the announcement and the latest close; unadjusted."""
    pre = yf.download("UNP", start="2025-07-14", end=ANNOUNCEMENT.isoformat(), auto_adjust=False,
                      progress=False)["Close"]["UNP"].dropna()
    latest = yf.download("UNP", period="10d", auto_adjust=False, progress=False)["Close"]["UNP"].dropna()
    return ((pre.index[-1].date().isoformat(), round(float(pre.iloc[-1]), 2)),
            (latest.index[-1].date().isoformat(), round(float(latest.iloc[-1]), 2)))


def write_xlsx(out, summary, raw, flags):
    money = ["revenue", "operating_income", "ebitda", "net_income", "operating_cash_flow", "capex", "free_cash_flow",
             "dividends_paid", "share_repurchases", "total_debt", "cash", "net_debt"]
    pct = ["revenue_growth", "operating_ratio"]
    s = summary.copy()
    for c in money:
        s[c] = s[c] / 1e9
    s = s.rename(columns={c: f"{c} (bn)" for c in money})
    sources = pd.DataFrame({"note": [
        "Source: SEC XBRL companyfacts (data.sec.gov/api/xbrl/companyfacts), fetched with edgartools.",
        "Values: annual figures from Form 10-K (form = 10-K, fp = FY). Flows require a ~1-year duration; balance-sheet "
        "values are fiscal-year-end instants. Where a value was restated in a later 10-K, the latest-filed value is used.",
        "Companies: UNP (memo company); CSX and CP (peers); NSC FY2025 only, as the merger counterparty (not a peer), for pro forma leverage. Currency: UNP, CSX and NSC in USD; CP (Canadian Pacific Kansas City) reports in CAD. Ratios are comparable across "
        "companies; levels are not (no FX conversion).",
        "Revenue growth = revenue / prior-year revenue - 1.",
        "Operating ratio = (revenue - operating income) / revenue.",
        "EBITDA = operating income + depreciation & amortization (UNP reports depreciation only).",
        "Total debt = LongTermDebtAndCapitalLeaseObligations (non-current) + LongTermDebtAndCapitalLeaseObligationsCurrent "
        "(debt due within one year); includes finance leases. For each company this sum equals its own reported total-debt tag.",
        "Net debt = total debt - cash and equivalents. Net debt / EBITDA uses same-year EBITDA.",
        "Free cash flow = operating cash flow - capital expenditures (PaymentsToAcquirePropertyPlantAndEquipment).",
        "Tag choices and fallbacks: " + ("; ".join(flags) if flags else "none"),
    ]})
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        s.to_excel(w, sheet_name="Summary", index=False)
        raw.to_excel(w, sheet_name="Raw", index=False)
        sources.to_excel(w, sheet_name="Sources", index=False)
        ws = w.sheets["Summary"]
        for j, h in enumerate([c.value for c in ws[1]], start=1):
            ws.column_dimensions[ws.cell(row=1, column=j).column_letter].width = max(12, len(h) + 2)
            fmt = ("0.0%" if h in pct else NUM if h.endswith("(bn)") else RATIO if h == "net_debt_to_ebitda"
                   else "0.00" if h == "diluted_eps" else None)
            if fmt:
                for row in ws.iter_rows(min_row=2, min_col=j, max_col=j):
                    row[0].number_format = fmt
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "D2"
        rws = w.sheets["Raw"]
        for c in rws[1]:
            c.font = Font(bold=True)
        for col, width in zip("ABCDEFGHIJ", (8, 11, 20, 18, 52, 12, 12, 12, 24, 12)):
            rws.column_dimensions[col].width = width
        rws.freeze_panes = "A2"
        sws = w.sheets["Sources"]
        sws.column_dimensions["A"].width = 140
        for row in sws.iter_rows(min_row=2):
            row[0].alignment = Alignment(wrap_text=True, vertical="top")


def write_proforma(out, summary, pre_close, latest_close):
    """ProForma sheet: inputs as values, everything derived as Excel formulas."""
    def g(ticker, col):
        return float(summary[(summary.ticker == ticker) & (summary.fiscal_year == 2025)][col].iloc[0]) / 1e9

    wb = load_workbook(out)
    ws = wb.create_sheet("ProForma")
    bold = Font(bold=True)

    def put(cell, value, fmt=None, font=None, wrap=False):
        c = ws[cell]
        c.value = value
        if fmt:
            c.number_format = fmt
        if font:
            c.font = font
        if wrap:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    put("A1", "Pro forma leverage, UNP + Norfolk Southern (FY2025, USD bn)", font=bold)
    put("A2", "ILLUSTRATIVE ONLY: excludes synergies, transaction costs, any divestitures, and cash generated or debt "
              "repaid between FY2025 and closing (expected 2027). NSC is the merger counterparty, not a peer.", wrap=True)
    ws.merge_cells("A2:F2")
    ws.row_dimensions[2].height = 45

    put("A4", "Inputs (edit these)", font=bold)
    inputs = [("UNP EBITDA FY2025", g("UNP", "ebitda")), ("NSC EBITDA FY2025", g("NSC", "ebitda")),
              ("UNP total debt FY2025", g("UNP", "total_debt")), ("UNP cash FY2025", g("UNP", "cash")),
              ("NSC total debt FY2025", g("NSC", "total_debt")), ("NSC cash FY2025", g("NSC", "cash")),
              ("Cash consideration (approx. USD 20bn, Note 20)", CASH_CONSIDERATION_BN)]
    for r, (label, val) in enumerate(inputs, start=5):  # rows 5-11
        put(f"A{r}", label)
        put(f"B{r}", round(val, 3), NUM)

    put("A13", "Derived", font=bold)
    put("A14", "Combined EBITDA (no synergies)"); put("B14", "=B5+B6", NUM)
    put("A15", "Combined net debt before the deal"); put("B15", "=B7-B8+B9-B10", NUM)
    put("A16", "UNP standalone net debt / EBITDA"); put("B16", "=(B7-B8)/B5", RATIO)

    put("A17", "Funding scenarios: the cash portion is assumed to come from operating cash generated before closing "
               "(Note 20), so FY2025 cash balances are unchanged.", font=bold, wrap=True)
    ws.merge_cells("A17:F17")
    ws.row_dimensions[17].height = 30
    for col, h in zip("ABCDEF", ["Scenario", "Share funded with new debt", "New debt", "Cash portion",
                                 "Pro forma net debt", "Net debt / EBITDA"]):
        put(f"{col}18", h, font=bold)
    for r, share in zip((19, 20, 21), (1.0, 0.75, 0.5)):
        put(f"A{r}", f"{share:.0%} funded with new debt")
        put(f"B{r}", share, "0%")
        put(f"C{r}", f"=B{r}*$B$11", NUM)
        put(f"D{r}", f"=$B$11-C{r}", NUM)
        put(f"E{r}", f"=$B$15+C{r}", NUM)
        put(f"F{r}", f"=E{r}/$B$14", RATIO)
    put("A22", "Check: cash portion paid from existing balances (any debt share)")
    put("E22", "=$B$15+$B$11", NUM); put("F22", "=E22/$B$14", RATIO)
    put("A23", "UNP standalone (FY2025)")
    put("E23", "=B7-B8", NUM); put("F23", "=B16", RATIO)
    put("A24", "If the cash portion came out of existing balances, net debt would rise by the full cash consideration "
               "whatever the debt share (row 22). Combined FY2025 cash is far below USD 10bn, so the 75% and 50% cases "
               "depend on cash generated before closing.", wrap=True)
    ws.merge_cells("A24:F24")
    ws.row_dimensions[24].height = 45

    put("A26", "Implied deal value (USD bn)", font=bold)
    deal = [("UNP shares to be issued (millions, Note 20)", SHARES_ISSUED_M, "#,##0.0"),
            ("Cash per NS share (USD, Note 20)", CASH_PER_SHARE, "0.00"),
            ("Cash consideration = shares x cash per share (one UNP share per NS share)", "=B27*B28/1000", NUM),
            (f"UNP close on {pre_close[0]} (last close before the 29 Jul 2025 announcement)", pre_close[1], "0.00"),
            (f"UNP close on {latest_close[0]} (latest)", latest_close[1], "0.00"),
            ("Deal value at pre-announcement close (stock + cash)", "=B27*B30/1000+B29", NUM),
            ("Deal value at latest close (stock + cash)", "=B27*B31/1000+B29", NUM)]
    for r, (label, val, fmt) in enumerate(deal, start=27):  # rows 27-33
        put(f"A{r}", label)
        put(f"B{r}", val, fmt)
    put("A34", "Prices are yfinance unadjusted closes. Deal value is equity consideration only; it excludes NSC debt assumed.")

    ws.column_dimensions["A"].width = 74
    for col in "BCDEF":
        ws.column_dimensions[col].width = 18
    wb.save(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=OUT, help=f"output workbook (default {OUT})")
    args = parser.parse_args()

    raw, flags = pull()
    summary = derive(raw)
    pre_close, latest_close = unp_closes()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_xlsx(args.out, summary, raw, flags)
    write_proforma(args.out, summary, pre_close, latest_close)
    print(f"UNP close before announcement {pre_close}, latest {latest_close}")
    print(f"{len(flags)} tag fallbacks/gaps (listed in the Sources sheet)")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
