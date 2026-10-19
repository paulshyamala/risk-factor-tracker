"""Render output/memo.md as a one-page US Letter PDF (output/memo.pdf) with WeasyPrint.

Layout: navy header band with the title; a main column with the memo text (every word of memo.md,
restyled) and a sidebar with "At a glance", key numbers and the deal timeline. Key numbers are read from
output/model.xlsx (ProForma formulas evaluated from their input cells) and every cell used is printed.
Writes nothing if any memo word is missing from the layout or the result isn't exactly one page.

WeasyPrint needs Pango (macOS: `brew install pango`). Fonts (Inter, Source Serif 4) load from Google
Fonts when reachable, otherwise Helvetica / Georgia.

Usage: python render_memo.py [--font-pt 9.5] [--line-height 1.4] [--section-gap 6] [--item-gap 3] [--out PATH]
"""
import argparse
import html
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("DYLD_FALLBACK_LIBRARY_PATH", "/opt/homebrew/lib")  # must be set before importing weasyprint

from openpyxl import load_workbook  # noqa: E402
from weasyprint import HTML  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "output"
MODEL = OUTPUT_DIR / "model.xlsx"

NAVY, ACCENT, GREY, TINT = "#14284b", "#2b7a78", "#6b7280", "#eef6f5"
MEMO_DATE = "October 19, 2026"
FEE_BN = 2.5  # Regulatory Termination Fee, merger agreement §7.3(b)(i) (not in model.xlsx)
AT_A_GLANCE = ["Union Pacific (UNP)", "Latest 10-K filed Feb 6, 2026", "ChangeScore 0.196 (2nd of 25)",
               "20 new risk paragraphs"]
SOURCE_TAGS = [  # one per "What they added" item, in order
    "Item 1A · UNP_latest_027 · severity 3",
    "Item 1A · UNP_latest_040 · severity 2",
    "Item 1A · UNP_latest_012 · sentence added this year",  # kept paragraph: not LLM-labelled, so no severity
]
TIMELINE = [  # (date, event, from outside the 10-K)
    ("Jul 28, 2025", "Merger agreement signed", False),
    ("Dec 19, 2025", "STB application filed", False),
    ("Jan 16, 2026", "Rejected as incomplete", False),
    ("Apr 30, 2026", "Revised application filed", True),
    ("May 28, 2026", "Accepted", True),
    ("Nov 18, 2026", "Opposition filings due", True),
    ("2027", "Expected close (company estimate)", False),
]
FONTS = ("@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700"
         "&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap');")


# ---------------------------------------------------------------- figures from model.xlsx
class Model:
    """Read values from model.xlsx, evaluating simple arithmetic formulas from their inputs."""

    def __init__(self, path):
        self.wb = load_workbook(path)
        self.used = []  # (label, sheet!cell, formula or "value", value)

    def _eval(self, sheet, ref):
        v = self.wb[sheet][ref.replace("$", "")].value
        if isinstance(v, str) and v.startswith("="):
            expr = re.sub(r"\$?([A-Z]{1,2})\$?(\d+)", lambda m: repr(self._eval(sheet, m.group(1) + m.group(2))), v[1:])
            if not re.fullmatch(r"[\d.+\-*/() e]+", expr):
                raise ValueError(f"unsupported formula {sheet}!{ref}: {v}")
            return eval(expr)  # arithmetic only, checked above
        return v

    def get(self, label, sheet, ref):
        value = self._eval(sheet, ref)
        raw = self.wb[sheet][ref].value
        self.used.append((label, f"{sheet}!{ref}", raw if isinstance(raw, str) and raw.startswith("=") else "value", value))
        return value

    def summary(self, label, ticker, year, column):
        ws = self.wb["Summary"]
        hdr = {c.value: c.column_letter for c in ws[1]}
        row = next(r for r in range(2, ws.max_row + 1)
                   if ws[f"A{r}"].value == ticker and ws[f"{hdr['fiscal_year']}{r}"].value == year)
        return self.get(label, "Summary", f"{hdr[column]}{row}")


def key_figures(m):
    fcf = m.summary("UNP free cash flow 2025 (bn)", "UNP", 2025, "free_cash_flow (bn)")
    return {
        "fee_share": FEE_BN / fcf,
        "standalone": m.get("UNP standalone net debt / EBITDA", "ProForma", "F23"),
        "pf_100": m.get("Pro forma, 100% debt-funded", "ProForma", "F19"),
        "pf_50": m.get("Pro forma, 50% debt-funded", "ProForma", "F21"),
        "or_unp": m.summary("Operating ratio UNP 2025", "UNP", 2025, "operating_ratio"),
        "or_cp": m.summary("Operating ratio CP 2025", "CP", 2025, "operating_ratio"),
        "or_csx": m.summary("Operating ratio CSX 2025", "CSX", 2025, "operating_ratio"),
        "deal": m.get("Deal value at latest close (bn)", "ProForma", "B33"),
        "rev_growth": m.summary("UNP revenue growth 2025", "UNP", 2025, "revenue_growth"),
    }


# ---------------------------------------------------------------- memo text
def parse_memo(md):
    """Title plus {section label: [paragraph or list items]}."""
    lines = md.splitlines()
    title = lines[0].lstrip("# ").strip()
    sections, current = {}, None
    for line in lines[1:]:
        m = re.match(r"\*\*(.+?)\.?\*\*\s*(.*)", line)
        if m:
            current = m.group(1).rstrip(".")
            sections[current] = [m.group(2)] if m.group(2) else []
        elif line.strip() and current:
            sections[current].append(re.sub(r"^(\d+\.|-)\s+", "", line.strip()))
    return title, sections


def esc(s):
    """HTML-escape and use typographic quotes (styling only; the words are unchanged)."""
    s = html.escape(s, quote=False)
    s = re.sub(r'"(?=\w)', "“", s)
    return s.replace('"', "”").replace("'", "’")


def lead_bold(item):
    """Bold the first sentence of a bullet (its label)."""
    m = re.match(r"(.+?[.?])\s+(.*)", item)
    return f"<strong>{esc(m.group(1))}</strong> {esc(m.group(2))}" if m else esc(item)


def added_item(item, tag):
    label, quote, rest = re.match(r'(.*?)\s*(".*?")\s*(.*)', item).groups()
    out = (f'<li><span class="label">{esc(label)}</span><blockquote>{esc(quote)}'
           f'<span class="tag">{esc(tag)}</span></blockquote>')
    return out + (f'<span class="after">{esc(rest)}</span>' if rest else "") + "</li>"


def build_html(md, f, font_pt, line_height, section_gap, item_gap):
    title, s = parse_memo(md)
    main = [f'<div class="bottom"><span class="kicker">Bottom line.</span> {esc(s["Bottom line"][0])}</div>',
            "<h2>What they added</h2><ol class='added'>"
            + "".join(added_item(it, tag) for it, tag in zip(s["What they added"], SOURCE_TAGS)) + "</ol>",
            "<h2>Why it matters</h2><ul>" + "".join(f"<li>{lead_bold(i)}</li>" for i in s["Why it matters"]) + "</ul>",
            "<h2>Questions for management</h2><ol>" + "".join(f"<li>{esc(i)}</li>" for i in s["Questions for management"]) + "</ol>",
            "<h2>What would change my view</h2><ul>" + "".join(f"<li>{lead_bold(i)}</li>" for i in s["What would change my view"]) + "</ul>",
            f'<p class="datanote"><strong>Data note.</strong> {esc(s["Data note"][0])}</p>']

    keys = [("$2.5bn", "Regulatory termination fee", f"≈{f['fee_share']:.0%} of 2025 FCF"),
            (f"{f['standalone']:.2f}x → {f['pf_50']:.1f}–{f['pf_100']:.1f}x", "Net debt / EBITDA", "standalone → pro forma"),
            (f"{f['or_unp']:.1%}", "Operating ratio UNP", f"CP {f['or_cp']:.1%} · CSX {f['or_csx']:.1%}"),
            (f"≈${f['deal']:.0f}bn", "Deal value", "equity, recent price"),
            (f"+{f['rev_growth']:.1%}", "Revenue growth 2025", "")]
    key_html = "".join(f'<div class="kn"><div class="big">{esc(a)}</div><div class="lbl">{esc(b)}</div>'
                       + (f'<div class="sub">{esc(c)}</div>' if c else "") + "</div>" for a, b, c in keys)
    glance = "".join(f"<li>{esc(x)}</li>" for x in AT_A_GLANCE)
    tl = "".join(f'<li><span class="d">{esc(d)}{"<sup>†</sup>" if ext else ""}</span> {esc(e)}</li>' for d, e, ext in TIMELINE)
    sidebar = (f'<h3>At a glance</h3><ul class="glance">{glance}</ul>'
               f'<div class="box"><h3>Key numbers</h3>{key_html}</div>'
               f'<h3>Deal timeline</h3><ul class="tl">{tl}</ul><div class="cap">† from 2026 10-Qs / STB decisions</div>')

    css = f"""{FONTS}
@page {{ size: Letter; margin: 0.6in;
  @bottom-left {{ content: "{MEMO_DATE} · Risk-Factor Change Tracker · method and data in the project repository";
                  font: 7pt Inter, Helvetica, sans-serif; color: {GREY}; }} }}
body {{ font-family: "Source Serif 4", Georgia, serif; font-size: {font_pt}pt; line-height: {line_height}; color: #1f2937; margin: 0; }}
.header {{ background: {NAVY}; color: white; margin: -0.6in -0.6in 14pt -0.6in; padding: 0.42in 0.6in 0.2in 0.6in;
           font-family: Inter, Helvetica, sans-serif; }}
.header h1 {{ font-size: 18pt; line-height: 1.22; margin: 0; font-weight: 700; }}
.cols {{ display: grid; grid-template-columns: 66% 30%; column-gap: 4%; }}
.side {{ border-left: 0.6pt solid #d1d5db; padding-left: 11pt; font-family: Inter, Helvetica, sans-serif;
         font-size: 7.8pt; line-height: 1.35; }}
.bottom {{ background: {TINT}; border-left: 2.5pt solid {ACCENT}; padding: 6pt 8pt; }}
.kicker {{ font-family: Inter, Helvetica, sans-serif; font-weight: 700; color: {ACCENT}; font-size: {font_pt - 0.5}pt; }}
h2 {{ font-family: Inter, Helvetica, sans-serif; text-transform: uppercase; letter-spacing: 0.9pt; font-size: {font_pt - 1.6}pt;
      color: {NAVY}; font-weight: 700; border-bottom: 0.6pt solid #d1d5db; padding-bottom: 1.5pt;
      margin: {section_gap}pt 0 {section_gap * 0.45}pt 0; }}
ul, ol {{ margin: 0; padding-left: 14pt; }}
li {{ margin-bottom: {item_gap}pt; }}
li strong {{ font-weight: 600; color: {NAVY}; }}
.added .label {{ font-family: Inter, Helvetica, sans-serif; font-weight: 600; font-size: {font_pt - 1}pt; color: {NAVY}; }}
blockquote {{ font-style: italic; border-left: 2pt solid {ACCENT}; margin: 3pt 0 3pt 2pt; padding-left: 7pt; }}
.tag {{ display: block; font-style: normal; font-family: Inter, Helvetica, sans-serif; font-size: 6.8pt; color: {GREY}; margin-top: 1.5pt; }}
.datanote {{ font-size: 7.6pt; color: {GREY}; line-height: 1.35; margin: {section_gap}pt 0 0 0; }}
.datanote strong {{ color: {GREY}; }}
h3 {{ font-size: 7.4pt; text-transform: uppercase; letter-spacing: 0.9pt; color: {ACCENT}; margin: 12pt 0 4pt 0; font-weight: 700; }}
.side > h3:first-child {{ margin-top: 0; }}
ul.glance {{ list-style: none; padding: 0; }}
ul.glance li {{ margin-bottom: 2pt; }}
ul.glance li:first-child {{ font-weight: 700; color: {NAVY}; font-size: 8.6pt; }}
.box {{ background: #f6f8fa; padding: 2pt 8pt 4pt 8pt; margin-top: 10pt; }}
.box h3 {{ margin-top: 6pt; }}
.kn {{ margin-bottom: 6pt; }}
.kn .big {{ font-size: 13pt; font-weight: 700; color: {NAVY}; line-height: 1.15; }}
.kn .lbl {{ font-size: 7.4pt; font-weight: 600; color: #374151; }}
.kn .sub {{ font-size: 7pt; color: {GREY}; }}
.cap {{ font-size: 6.8pt; color: {GREY}; margin-top: 3pt; }}
ul.tl {{ list-style: none; padding-left: 10pt; margin: 0; border-left: 1pt solid #c7d2db; }}
ul.tl li {{ position: relative; margin-bottom: 4pt; }}
ul.tl li:before {{ content: ""; position: absolute; left: -13.3pt; top: 2.8pt; width: 5pt; height: 5pt; border-radius: 3pt; background: {ACCENT}; }}
ul.tl .d {{ font-weight: 600; color: {NAVY}; display: block; }}
sup {{ font-size: 5.5pt; color: {ACCENT}; }}
"""
    body = (f'<div class="header"><h1>{esc(title)}</h1></div>'
            f'<div class="cols"><div class="main">{"".join(main)}</div><div class="side">{sidebar}</div></div>')
    return f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>", title


def check_text(md, page_html, title):
    """Every word of memo.md must appear in the page, in order."""
    def words(s):
        s = s.replace("“", '"').replace("”", '"').replace("’", "'")
        return re.findall(r"[A-Za-z0-9$%~§()\-–.,;:'\"]+", s)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page_html))
    body_md = re.sub(r"\*\*|^\s*(\d+\.|-)\s+", "", "\n".join(md.splitlines()[1:]), flags=re.M)
    want, i = words(body_md), 0
    for w in words(text):
        if i < len(want) and w == want[i]:
            i += 1
    return i == len(want) and title in text, len(want) - i


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--font-pt", type=float, default=9.5)
    parser.add_argument("--line-height", type=float, default=1.4)
    parser.add_argument("--section-gap", type=float, default=6.0, help="space above each section heading (pt)")
    parser.add_argument("--item-gap", type=float, default=3.0, help="space between list items (pt)")
    parser.add_argument("--out", type=Path, default=OUTPUT_DIR / "memo.pdf")
    args = parser.parse_args()

    model = Model(MODEL)
    figures = key_figures(model)
    md = (OUTPUT_DIR / "memo.md").read_text()
    page_html, title = build_html(md, figures, args.font_pt, args.line_height, args.section_gap, args.item_gap)
    ok, unmatched = check_text(md, page_html, title)
    if not ok:
        sys.exit(f"memo text not fully present in the layout ({unmatched} words unmatched); not written")
    doc = HTML(string=page_html, base_url=str(OUTPUT_DIR)).render()
    settings = f"{args.font_pt}pt / line-height {args.line_height} / section gap {args.section_gap}pt / item gap {args.item_gap}pt"
    if len(doc.pages) != 1:
        sys.exit(f"memo is {len(doc.pages)} pages at {settings}; not written")
    doc.write_pdf(args.out)
    print("key numbers (model.xlsx):")
    for label, cell, how, value in model.used:
        print(f"  {label:36} {cell:14} {how:24} {value:.4f}")
    print(f"  {'Regulatory termination fee (bn)':36} merger agreement §7.3(b)(i)  {FEE_BN}")
    print(f"wrote {args.out}: 1 page, {settings}")


if __name__ == "__main__":
    main()
