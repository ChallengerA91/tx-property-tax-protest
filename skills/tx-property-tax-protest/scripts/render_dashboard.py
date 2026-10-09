"""dashboard.html: one self-contained page (inline CSS, SVG and a tiny script; no external requests)."""
from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Optional, Sequence

from analysis import Analysis
from fmt import beds_baths, comp_when, long_date, money, number, percent, text_or_dash, weekday_date, write_text
from savings import meter_line, range_text, savings_notes, scenario_text

PATH_LABELS = {"homestead": "Homestead protest", "rental": "Rental property protest"}
STRATEGY_LABELS = {
    "market_value": "Market value",
    "unequal_appraisal": "Unequal appraisal",
    "both": "Market value and unequal appraisal",
}

STYLE = """
:root {
  color-scheme: light dark;
  --bg: #f4f6f9; --surface: #ffffff; --ink: #16202c; --muted: #46525f; --line: #cfd7e2;
  --accent: #0b5cad; --bar: #2f6fb0; --bar-ink: #ffffff; --alt: #0f766e; --alt-ink: #ffffff;
  --subject: #b45309; --subject-ink: #ffffff; --argued: #6d28d9; --good: #166534; --track: #e8edf3;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0e141b; --surface: #17202a; --ink: #e8edf3; --muted: #aab5c2; --line: #33404f;
    --accent: #7db8ff; --bar: #6aa9e8; --bar-ink: #0a1118; --alt: #4fd1c1; --alt-ink: #04110f;
    --subject: #f5a524; --subject-ink: #1a1100; --argued: #c4a8ff; --good: #7ee0a0; --track: #223040;
  }
}
* { box-sizing: border-box; }
html { -webkit-text-size-adjust: 100%; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 1rem/1.5 system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
.skip { position: absolute; left: -999px; top: 0; background: var(--surface); color: var(--ink); padding: .5rem 1rem; }
.skip:focus { left: 8px; top: 8px; z-index: 10; outline: 3px solid var(--accent); }
.wrap { max-width: 64rem; margin: 0 auto; padding: 0 16px; }
header.page { padding-top: 1.5rem; padding-bottom: .5rem; }
.eyebrow { margin: 0; color: var(--muted); font-size: .875rem; letter-spacing: .02em; }
h1 { margin: .25rem 0; font-size: clamp(1.4rem, 5vw, 2rem); line-height: 1.2; overflow-wrap: anywhere; }
h2 { margin: 2rem 0 .75rem; font-size: 1.25rem; }
h3 { margin: 0; font-size: .9rem; font-weight: 600; color: var(--muted); }
.meta { margin: 0; color: var(--muted); }
button.print {
  margin-top: .75rem; min-height: 44px; padding: 0 1rem; border: 2px solid var(--accent);
  background: transparent; color: var(--accent); border-radius: 8px; font: inherit; font-weight: 600; cursor: pointer;
}
button.print:focus-visible, .scroll:focus-visible, summary:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr)); gap: .75rem; margin: 0; }
.tile { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: .9rem 1rem; }
.tile dt { color: var(--muted); font-size: .875rem; font-weight: 600; }
.tile dd { margin: .15rem 0 0; }
.tile .big { font-size: clamp(1.35rem, 5vw, 1.85rem); font-weight: 700; font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.tile .sub { color: var(--muted); font-size: .875rem; }
.tile.key { border-left: 6px solid var(--accent); }
.meter { margin: 1rem 0 0; padding: .75rem 1rem; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; font-weight: 600; }
.charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(19rem, 1fr)); gap: 1rem; }
.charts figure:only-child { max-width: 34rem; }
figure { margin: 0; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: .75rem; }
figcaption { font-weight: 600; margin-bottom: .25rem; }
figure .hint { margin: .25rem 0 0; color: var(--muted); font-size: .875rem; }
svg { display: block; width: 100%; height: auto; }
svg text { fill: var(--ink); font: 12px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
svg .muted { fill: var(--muted); }
svg .bar { fill: var(--bar); } svg .bar-alt { fill: var(--alt); }
svg .bar-subject { fill: var(--subject); stroke: var(--ink); stroke-width: 2; }
svg text.on-bar { fill: var(--bar-ink); font-weight: 600; } svg text.on-alt { fill: var(--alt-ink); font-weight: 600; }
svg text.on-subject { fill: var(--subject-ink); font-weight: 700; }
svg .ref-appraised { stroke: var(--ink); stroke-width: 2; }
svg .ref-argued { stroke: var(--argued); stroke-width: 2; stroke-dasharray: 6 4; }
svg .ref-capped { stroke: var(--muted); stroke-width: 2; stroke-dasharray: 2 3; }
svg text.t-argued { fill: var(--argued); font-weight: 700; } svg text.t-ref { font-weight: 700; }
svg text.row-label { font-weight: 500; } svg text.subject-label { font-weight: 700; }
.scroll { overflow-x: auto; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; }
caption { text-align: left; font-weight: 600; padding: .6rem .75rem; }
th, td { padding: .5rem .75rem; border-top: 1px solid var(--line); text-align: left; vertical-align: top; }
thead th { background: var(--track); border-top: 0; white-space: nowrap; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
tbody th { font-weight: 500; }
td { white-space: nowrap; }
.comps th:first-child, .comps td:first-child { position: sticky; left: 0; background: var(--surface); min-width: 11rem; }
.comps thead th:first-child, .comps tfoot th:first-child { background: var(--track); }
tfoot th, tfoot td { font-weight: 700; background: var(--track); }
tr.subject th, tr.subject td { font-weight: 700; background: var(--track); }
.comps table { min-width: 52rem; }
.wide table { min-width: 26rem; }
details { margin-top: .75rem; background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: .6rem .9rem; }
summary { cursor: pointer; font-weight: 600; min-height: 24px; }
details ul { margin: .5rem 0 0; padding-left: 1.25rem; }
.timeline { list-style: none; margin: 0; padding: 0 0 0 1.25rem; border-left: 3px solid var(--line); }
.timeline li { position: relative; margin: 0 0 1.1rem; padding-left: .5rem; }
.timeline li::before {
  content: ""; position: absolute; left: calc(-1.25rem - 9px); top: .35rem; width: 15px; height: 15px;
  border-radius: 50%; background: var(--accent); border: 3px solid var(--bg);
}
.timeline time { display: block; font-weight: 700; }
.timeline strong, .timeline .detail { display: block; }
.timeline .detail { color: var(--muted); font-size: .9rem; }
.note { color: var(--muted); font-size: .9rem; }
.sub-head { margin: 1.25rem 0 .5rem; font-size: 1rem; color: var(--ink); }
footer.page { margin-top: 2.5rem; margin-bottom: 2rem; padding-top: 1rem; border-top: 1px solid var(--line); color: var(--muted); font-size: .875rem; }
@media print {
  body { background: #fff; color: #000; }
  .skip, button.print { display: none; }
  .tile, figure, .scroll, details { break-inside: avoid; }
}
"""

SUBJECT_ROW = ' class="subject"'

# Enforces the "no external requests" promise in the browser: nothing but inline style and script, and data: images.
CSP = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:"

SCRIPT = """
var button = document.getElementById('print');
if (button) { button.hidden = false; button.addEventListener('click', function () { window.print(); }); }
"""


# --- SVG bar chart ----------------------------------------------------------

@dataclass(frozen=True)
class BarRow:
    label: str
    value: float
    text: str            # printed on or beside the bar
    kind: str = "bar"    # bar | alt | subject


@dataclass(frozen=True)
class RefLine:
    label: str
    value: float
    css: str             # ref-appraised | ref-argued | ref-capped


WIDTH, PAD, ROW_PITCH, BAR_HEIGHT, TOP = 360, 12, 46, 20, 62
INSIDE_MIN = 150  # bar must be at least this long (px) to hold its text inside


def _clip(text: str, limit: int = 50) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _street(address: str) -> str:
    """Street part of an address; the full address stays in the tables."""
    return address.split(",")[0].strip()


def _ref_line_svg(ref: RefLine, x: float, lane: int, height: float) -> str:
    y_label = 12 + lane * 16
    anchor, dx = ("end", -5) if x >= 170 else ("start", 5)
    cls = "t-argued" if ref.css == "ref-argued" else "t-ref"
    return (
        f'<line class="{ref.css}" x1="{x:.1f}" x2="{x:.1f}" y1="{y_label + 4}" y2="{height - 6:.1f}"/>'
        f'<text class="{cls}" x="{x + dx:.1f}" y="{y_label}" text-anchor="{anchor}">{escape(ref.label)}</text>'
    )


def _bar_svg(row: BarRow, y: float, length: float) -> str:
    style = {"bar": ("bar", "on-bar"), "alt": ("bar-alt", "on-alt"),
             "subject": ("bar-subject", "on-subject")}[row.kind]
    label_class = "subject-label" if row.kind == "subject" else "row-label"
    inside = length >= INSIDE_MIN
    text_x = PAD + 8 if inside else PAD + length + 6  # inside text sits left, clear of the reference lines
    text_class = style[1] if inside else ""
    return (
        f'<text class="{label_class}" x="{PAD}" y="{y + 12:.1f}">{escape(_clip(row.label))}</text>'
        f'<rect class="{style[0]}" x="{PAD}" y="{y + 18:.1f}" width="{length:.1f}" height="{BAR_HEIGHT}" rx="3"/>'
        f'<text class="{text_class}" x="{text_x:.1f}" y="{y + 18 + 14:.1f}">{escape(row.text)}</text>'
    )


def bar_chart(chart_id: str, title: str, description: str,
              rows: Sequence[BarRow], refs: Sequence[RefLine]) -> str:
    """Zero-based horizontal bars with labelled reference lines; scales to any container width."""
    plot_width = WIDTH - 2 * PAD
    scale = max([r.value for r in rows] + [r.value for r in refs] + [1])
    height = TOP + len(rows) * ROW_PITCH + 4
    parts = [f'<svg viewBox="0 0 {WIDTH} {height}" role="img" aria-labelledby="{chart_id}-t {chart_id}-d">',
             f'<title id="{chart_id}-t">{escape(title)}</title><desc id="{chart_id}-d">{escape(description)}</desc>']
    for index, row in enumerate(rows):
        parts.append(_bar_svg(row, TOP + index * ROW_PITCH, max(row.value, 0) / scale * plot_width))
    for lane, ref in enumerate(refs):
        parts.append(_ref_line_svg(ref, PAD + max(ref.value, 0) / scale * plot_width, lane, height))
    parts.append("</svg>")
    return "".join(parts)


def _delta(value: float, base: float) -> str:
    change = (value - base) / base * 100
    sign = "+" if change > 0 else "−" if change < 0 else ""
    return f"{sign}{abs(change):.1f}%"


def _comp_chart(a: Analysis) -> Optional[str]:
    rows = [BarRow(_street(c.address) + (f" ({number(c.sqft)} sq ft)" if c.sqft else ""), c.adjusted_value,
                   f"{money(c.adjusted_value)} ({_delta(c.adjusted_value, a.market_value)})")
            for c in sorted(a.sale_comps, key=lambda c: -c.adjusted_value)]
    if a.income:
        rows.append(BarRow("Income approach (NOI / cap rate)", a.income.indicated_value,
                           f"{money(a.income.indicated_value)} ({_delta(a.income.indicated_value, a.market_value)})",
                           "alt"))
    if not rows:
        return None
    description = (f"Horizontal bars of {len(rows)} value indications from {money(min(r.value for r in rows))} to "
                   f"{money(max(r.value for r in rows))}, against the {a.value_term} {money(a.market_value)}"
                   f"{f', the taxable (capped) appraised value {money(a.appraised_value)}' if a.capped else ''} "
                   f"and the argued value {money(a.argued_value)}.")
    refs = [RefLine(f"{'Market' if a.capped else 'Appraised'} {money(a.market_value)}", a.market_value,
                    "ref-appraised")]
    if a.capped:
        refs.append(RefLine(f"Taxable (capped) {money(a.appraised_value)}", a.appraised_value, "ref-capped"))
    refs.append(RefLine(f"Argued {money(a.argued_value)}", a.argued_value, "ref-argued"))
    svg = bar_chart("c1", "Value indications compared with the appraisal", description, rows, refs)
    return _figure("Adjusted comparable sales vs. appraisal", svg,
                   f"Percentages show each value compared with the {a.value_term}.")


def _unequal_chart(a: Analysis) -> Optional[str]:
    u = a.unequal
    if not u:
        return None
    entries = [BarRow(_street(n.address), n.ppsf, f"{money(n.ppsf, True)} per sq ft") for n in u.neighbors]
    entries.append(BarRow(f"{_street(a.case['subject']['address'])} (your property)", u.subject_ppsf,
                          f"{money(u.subject_ppsf, True)} per sq ft", "subject"))
    entries.sort(key=lambda r: -r.value)
    refs = [RefLine(f"Neighbor median {money(u.median_ppsf, True)}", u.median_ppsf, "ref-appraised"),
            RefLine(f"Argued {money(a.argued_ppsf, True)}", a.argued_ppsf, "ref-argued")]
    basis = "Market-value" if a.capped else "Appraised"
    description = (f"{basis} dollars per square foot for {len(u.neighbors)} neighbors and your property, which ranks "
                   f"{u.rank} of {u.group_size} from highest. Neighbor median {money(u.median_ppsf, True)}; "
                   f"argued {money(a.argued_ppsf, True)}.")
    svg = bar_chart("c2", f"{basis} dollars per square foot", description, entries, refs)
    return _figure(f"{basis} $ per sq ft: neighbors vs. your property", svg,
                   f"Your property ranks {u.rank} of {u.group_size} (1 = highest), "
                   f"at the {u.percentile:.0f}th percentile.")


def _figure(caption: str, svg: str, hint: str) -> str:
    return f'<figure><figcaption>{escape(caption)}</figcaption>{svg}<p class="hint">{escape(hint)}</p></figure>'


# --- page sections ----------------------------------------------------------

def _tile(label: str, value: str, sub: str = "", key: bool = False) -> str:
    sub_html = f'<span class="sub">{escape(sub)}</span>' if sub else ""
    return (f'<div class="tile{" key" if key else ""}"><dt>{escape(label)}</dt>'
            f'<dd><span class="big">{escape(value)}</span><br>{sub_html}</dd></div>')


def _summary(a: Analysis) -> str:
    s = a.savings
    tiles = [
        _tile("CAD market value" if a.capped else "Appraised value", money(a.market_value),
              f"{money(a.market_ppsf, True)} per sq ft"),
        _tile("Argued value", money(a.argued_value), f"{money(a.argued_ppsf, True)} per sq ft", key=True),
        _tile("Reduction in market value" if a.capped else "Requested reduction", money(a.reduction),
              f"{percent(a.reduction_pct)} of the {'market value' if a.capped else 'appraisal'}"),
        _tile("Estimated savings per year", range_text(s.total.low, s.total.high),
              "protest and exemptions", key=True),
    ]
    if a.capped:
        tiles.insert(1, _tile("Taxable (capped) appraised value", money(a.appraised_value),
                              "the value your tax is based on"))
        tiles.insert(4, _tile("Reduction below the taxable (capped) value", money(s.reduction),
                              "what can lower your tax"))
    if a.income:
        tiles.insert(2 + 2 * a.capped, _tile("Income-indicated value", money(a.income.indicated_value),
                                             f"NOI {money(a.income.noi)}"))
    return (f'<section aria-labelledby="h-summary"><h2 id="h-summary">Summary</h2>'
            f'<dl class="tiles">{"".join(tiles)}</dl><p class="meter">{escape(meter_line(s))}</p>'
            f'{_notes_html(s)}</section>')


def _notes_html(s) -> str:
    return "".join(f'<p class="note">{escape(note)}</p>' for note in savings_notes(s))


def _charts(a: Analysis) -> str:
    figures = [f for f in (_comp_chart(a), _unequal_chart(a)) if f]
    if not figures:
        return ""
    return f'<section aria-labelledby="h-charts"><h2 id="h-charts">Evidence at a glance</h2><div class="charts">{"".join(figures)}</div></section>'


def _row(cells: Sequence[str], header_first: bool = True, numeric_from: int = 1) -> str:
    out = []
    for index, cell in enumerate(cells):
        cls = ' class="num"' if index >= numeric_from else ""
        tag, scope = ("th", ' scope="row"') if index == 0 and header_first else ("td", "")
        out.append(f"<{tag}{scope}{cls}>{cell}</{tag}>")
    return "<tr>" + "".join(out) + "</tr>"


def _column_header(label: str, numeric: bool) -> str:
    cls = ' class="num"' if numeric else ""
    return f'<th scope="col"{cls}>{escape(label)}</th>'


COMP_HEADS = ["Address", "Date", "Price", "Sq ft", "$ / sq ft", "Beds / baths", "Year", "Miles",
              "Net adj.", "Adjusted value"]


def _comp_row(c) -> str:
    return _row([
        escape(c.address), escape(comp_when(c.price_type, c.sale_date)),
        money(c.price), number(c.sqft), money(c.price_ppsf, True), escape(beds_baths(c.beds, c.baths)),
        escape(text_or_dash(c.year_built)), number(c.distance_mi, 1), money(c.adjustment_total),
        money(c.adjusted_value),
    ], numeric_from=2)


def _comps_table(a: Analysis) -> str:
    if not a.sale_comps:
        return ""
    head = "".join(_column_header(h, numeric=i > 0) for i, h in enumerate(COMP_HEADS))
    body = "".join(_comp_row(c) for c in a.sale_comps)
    foot = _row(["Median", "", "", "", money(a.median_price_ppsf, True),
                 "", "", "", "", money(a.median_adjusted)], numeric_from=2)
    return (f'<section aria-labelledby="h-comps"><h2 id="h-comps">Comparable sales</h2>'
            f'<div class="scroll comps" role="region" aria-label="Comparable sales table, scrolls sideways" tabindex="0">'
            f'<table><caption>Adjusted value is price plus net adjustments.</caption>'
            f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody><tfoot>{foot}</tfoot></table></div>'
            f'{_adjustment_details(a)}{_other_points_table(a)}</section>')


def _other_points_table(a: Analysis) -> str:
    if not a.other_comps:
        return ""
    head = "".join(_column_header(h, numeric=i > 0) for i, h in enumerate(COMP_HEADS))
    body = "".join(_comp_row(c) for c in a.other_comps)
    return (f'<h3 class="sub-head">Other data points (not used in the median)</h3>'
            f'<div class="scroll comps" role="region" aria-label="Other data points table, scrolls sideways" tabindex="0">'
            f'<table><caption>Listings and estimates are context, not sales.</caption>'
            f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>')


def _adjustment_details(a: Analysis) -> str:
    items = []
    for c in a.comps:
        if not c.adjustments:
            continue
        lines = "".join(f"<li>{escape(adj.label)}: {money(adj.amount)}</li>" for adj in c.adjustments)
        items.append(f"<li><strong>{escape(c.address)}</strong><ul>{lines}</ul></li>")
    if not items:
        return ""
    return f'<details><summary>Adjustment detail</summary><ul>{"".join(items)}</ul></details>'


def _unequal_table(a: Analysis) -> str:
    u = a.unequal
    if not u:
        return ""
    basis = "market value" if a.capped else "appraised value"
    body = "".join(
        f'<tr{SUBJECT_ROW if row.is_subject else ""}>'
        f'<th scope="row">{row.rank}. {escape(row.address)}</th>'
        f'<td class="num">{money(row.appraised_value)}</td><td class="num">{number(row.sqft)}</td>'
        f'<td class="num">{money(row.ppsf, True)}</td></tr>'
        for row in a.ranked_neighbors())
    return (f'<section aria-labelledby="h-unequal"><h2 id="h-unequal">Unequal appraisal</h2>'
            f'<div class="scroll wide" role="region" aria-label="Neighbor appraisals, scrolls sideways" tabindex="0">'
            f'<table><caption>Ranked by {basis} dollars per square foot, highest first; equal figures share a rank. '
            f'Neighbor median {money(u.median_ppsf, True)}; at that median your property would be appraised at '
            f'{money(u.indicated_value)}.</caption>'
            f'<thead><tr><th scope="col">Property</th><th scope="col" class="num">Appraised value</th>'
            f'<th scope="col" class="num">Sq ft</th><th scope="col" class="num">$ / sq ft</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div></section>')


def _income_table(a: Analysis) -> str:
    inc = a.income
    if not inc:
        return ""
    rows = [
        ("Potential gross rent (annual)", money(inc.gross_rent)),
        (f"Vacancy and collection loss ({percent(inc.vacancy_pct)})", money(-inc.vacancy_loss)),
        ("Effective gross income", money(inc.effective_gross_income)),
        *[(f"Expense: {e.label}", money(-e.amount)) for e in inc.expenses],
        ("Net operating income", money(inc.noi)),
        (f"Capitalization rate ({inc.cap_rate_source})", percent(inc.cap_rate_pct, 2)),
        ("Income-indicated value", money(inc.indicated_value)),
    ]
    body = "".join(f'<tr><th scope="row">{escape(label)}</th><td class="num">{escape(value)}</td></tr>'
                   for label, value in rows)
    note = (f'<p class="note"><strong>Appraisal-increase limit (circuit breaker):</strong> '
            f'{escape(inc.circuit_breaker_note)}</p>') if inc.circuit_breaker_note else ""
    return (f'<section aria-labelledby="h-income"><h2 id="h-income">Income approach</h2>'
            f'<div class="scroll" role="region" aria-label="Income approach table, scrolls sideways" tabindex="0">'
            f'<table><thead><tr><th scope="col">Line</th><th scope="col" class="num">Amount</th></tr></thead>'
            f'<tbody>{body}</tbody></table></div>{note}</section>')


def _savings_table(a: Analysis) -> str:
    s = a.savings
    if s.protest_blocked:
        rows = [("Protest (argued value is not below the capped appraised value)", "$0", "$0")]
    else:
        label = ("Protest (reduction from the capped appraised value to the argued value)" if a.capped
                 else "Protest (reduction to the argued value)")
        rows = [(label, money(s.protest.low), money(s.protest.high))]
    for item in s.exemptions:
        amount = money(item.annual) if item.quantified else "Not quantified"
        rows.append((f"Exemption: {item.name}", amount, amount))
    body = "".join(f'<tr><th scope="row">{escape(l)}</th><td class="num">{escape(lo)}</td>'
                   f'<td class="num">{escape(hi)}</td></tr>' for l, lo, hi in rows)
    foot = (f'<tr><th scope="row">Total per year</th><td class="num">{money(s.total.low)}</td>'
            f'<td class="num">{money(s.total.high)}</td></tr>')
    rate = a.case["tax_rates"]["total"]
    notes = _notes_html(s)
    return (f'<section aria-labelledby="h-savings"><h2 id="h-savings">Estimated savings</h2>'
            f'<div class="scroll" role="region" aria-label="Savings table, scrolls sideways" tabindex="0">'
            f'<table><thead><tr><th scope="col">Source</th><th scope="col" class="num">Low scenario</th>'
            f'<th scope="col" class="num">High scenario</th></tr></thead><tbody>{body}</tbody>'
            f'<tfoot>{foot}</tfoot></table></div>'
            f'<p class="note">Total tax rate {rate:g} per $100 of value. Low and high are settlement scenarios '
            f'({scenario_text(s)}), not predictions.</p>{notes}</section>')


def _timeline(a: Analysis) -> str:
    items = []
    for item in a.deadlines:
        detail = " ".join(part for part in (item.full_note, f"Basis: {item.statute}." if item.statute else "") if part)
        detail_html = f'<span class="detail">{escape(detail)}</span>' if detail else ""
        items.append(f'<li><time datetime="{item.date.isoformat()}">{escape(weekday_date(item.date))}</time>'
                     f'<strong>{escape(item.event)}</strong>{detail_html}</li>')
    return (f'<section aria-labelledby="h-deadlines"><h2 id="h-deadlines">Deadlines</h2>'
            f'<ol class="timeline">{"".join(items)}</ol></section>')


def render_dashboard(a: Analysis) -> str:
    case = a.case
    prepared = f" | Prepared {long_date(a.prepared_on)}" if a.prepared_on else ""
    kind = PATH_LABELS[a.path]
    strategy = STRATEGY_LABELS[a.strategy]
    head = (f'<header class="page wrap"><p class="eyebrow">Tax year {case["tax_year"]} | {escape(case["county"])} | '
            f'{escape(case["cad"]["name"])}{escape(prepared)}</p>'
            f'<h1>{escape(case["subject"]["address"])}</h1>'
            f'<p class="meta">CAD account {escape(case["subject"]["cad_account"])} | {kind} | Strategy: {strategy}</p>'
            f'<button id="print" class="print" type="button" hidden>Print or save as PDF</button></header>')
    sections = [_summary(a), _charts(a), _comps_table(a), _unequal_table(a), _income_table(a),
                _savings_table(a), _timeline(a)]
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        f'<title>Protest dashboard - {escape(case["subject"]["address"])}</title>\n'
        f'<style>{STYLE}</style>\n</head>\n<body>\n<a class="skip" href="#main">Skip to content</a>\n'
        f'{head}\n<main id="main" class="wrap">\n{chr(10).join(s for s in sections if s)}\n</main>\n'
        f'<footer class="page wrap"><p>{escape(a.disclaimer)}</p></footer>\n'
        f'<script>{SCRIPT}</script>\n</body>\n</html>\n'
    )


def write_dashboard(a: Analysis, path: Path) -> None:
    write_text(path, render_dashboard(a))
