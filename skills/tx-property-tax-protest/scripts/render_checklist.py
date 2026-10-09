"""filing_checklist.md: what to file, by when, what to bring, and which exemptions to claim.

Text from the case (and from scraped county data) is made safe for markdown: line breaks are
collapsed, and <, > and & become entities, so it cannot add raw HTML or break a table row.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, List, Mapping, Optional

from analysis import Analysis
from deadlines import PORTAL_WARNING
from fmt import MISSING, long_date, money, percent, weekday_date, write_text
from savings import ExemptionSavings, meter_line, savings_notes, scenario_text


def md(value: Any) -> str:
    """One line of markdown-safe text."""
    text = " ".join(str(value).split())
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("[", "\\[").replace("]", "\\]")


def _table(headers: List[str], rows: List[List[str]]) -> List[str]:
    """Rows hold markdown-safe text; a pipe inside a cell is escaped here."""
    def line(row: List[str]) -> str:
        return "| " + " | ".join(value.replace("|", "\\|") for value in row) + " |"

    return [line(headers), line(["---"] * len(headers)), *[line(row) for row in rows], ""]


def _numbers(a: Analysis) -> List[str]:
    rows = [[f"CAD {a.value_term}", money(a.market_value)]]
    if a.capped:
        rows.append(["Taxable (capped) appraised value (the value your tax is based on)", money(a.appraised_value)])
    if a.median_adjusted is not None:
        rows.append(["Median adjusted comparable value", money(a.median_adjusted)])
    rows.append(["Argued value (your opinion of value)", money(a.argued_value)])
    if a.capped:
        rows.append(["Reduction in market value", f"{money(a.reduction)} ({percent(a.reduction_pct)})"])
        rows.append(["Reduction below the taxable (capped) value", money(a.savings.reduction)])
    else:
        rows.append(["Requested reduction", f"{money(a.reduction)} ({percent(a.reduction_pct)})"])
    if a.unequal:
        basis = "market-value $/sq ft" if a.capped else "$/sq ft"
        rows.append([f"Subject {basis} rank among neighbors (1 = highest)",
                     f"{a.unequal.rank} of {a.unequal.group_size}"])
    if a.income:
        rows.append(["Income-indicated value", money(a.income.indicated_value)])
    return ["## Your numbers", "", *_table(["Item", "Value"], rows)]


def _deadlines(a: Analysis) -> List[str]:
    rows = [[weekday_date(d.date), md(d.event), md(d.statute) or MISSING,
             md(" ".join(part for part in (d.note, d.roll_text) if part)) or MISSING]
            for d in a.deadlines]
    lines = ["## 1. Deadlines", "", *_table(["Date", "Event", "Basis", "Note"], rows)]
    moved = [d for d in a.deadlines if d.portal_text]
    if moved:
        lines += [f"{PORTAL_WARNING}:", ""]
        lines += [f"- {md(d.event)}: {weekday_date(d.safe_date)} (statutory date {weekday_date(d.computed_date)}, "
                  f"moves to {weekday_date(d.date)})" for d in moved]
        lines.append("")
    return lines


def _how_to_file(a: Analysis) -> List[str]:
    cad, filing = a.case["cad"], a.case["filing"]
    lines = [f"## 2. How to file with {md(cad['name'])}", ""]
    for method in filing["methods"]:
        detail = f": {md(method['detail'])}" if method.get("detail") else ""
        lines.append(f"- **{md(method['method'])}**{detail}")
    form = a.case["legal_basis"].get("protest_form")
    if form:
        lines.append(f"- Protest form: {md(form)}")
    contact = [md(part) for part in (cad.get("phone"), cad.get("website"), cad["address"]) if part]
    lines += ["", f"Contact: {' | '.join(contact)}", ""]
    lines += [f"- {md(note)}" for note in filing.get("notes", [])]
    if filing.get("notes"):
        lines.append("")
    return lines


def _hearing_documents(a: Analysis) -> List[str]:
    case = a.case
    items = [
        "Printed copy of `comp_analysis.xlsx` (comparables, adjustments, and unequal appraisal sheets)",
        "Copy of `protest_letter.docx`",
        "Your appraisal notice and the CAD property record for the subject",
    ]
    if case["subject"].get("purchase_price"):
        items.append("Purchase contract or closing statement showing the price and date")
    items.append("Dated photos, repair estimates, or inspection reports for any condition issues")
    if a.income:
        items.append("Leases, rent roll, income and expense records, and the cap rate sources you relied on")
    if case.get("exemptions", {}).get("eligible"):
        items.append("Exemption applications and the supporting documents listed in section 4")
    items += [md(extra) for extra in case["filing"].get("hearing_documents", [])]
    return ["## 3. Documents for your hearing", "", *[f"- [ ] {item}" for item in items], ""]


def _describe_amount(item: Mapping[str, Any]) -> str:
    if item.get("kind") == "total":
        return "full exemption"
    if not item.get("amount"):
        return ""
    scope = "school taxes" if item.get("applies_to") == "school" else "all taxes"
    return f"{money(item['amount'])} exemption from {scope}"


def _exemption_lines(item: Mapping[str, Any], priced: Optional[ExemptionSavings] = None) -> List[str]:
    heading = f"**{md(item['name'])}**"
    if item.get("cite"):
        heading += f" ({md(item['cite'])})"
    if _describe_amount(item):
        heading += f", {_describe_amount(item)}"
    if priced is not None:
        heading += f": about {money(priced.annual)} per year" if priced.quantified else ": savings not quantified"
    lines = [f"- {heading}"]
    if item.get("how_to_claim"):
        lines.append(f"  - How to claim: {md(item['how_to_claim'])}")
    if item.get("documents"):
        lines.append(f"  - Documents: {', '.join(md(d) for d in item['documents'])}")
    if item.get("note"):
        lines.append(f"  - Note: {md(item['note'])}")
    return lines


def _exemptions(a: Analysis) -> List[str]:
    exemptions = a.case.get("exemptions") or {}
    lines = ["## 4. Exemptions", ""]
    on_file, eligible = exemptions.get("on_file", []), exemptions.get("eligible", [])
    if not on_file and not eligible:
        return lines + ["No exemptions were identified for this case.", ""]
    if on_file:
        lines += ["Already on file with the CAD:", ""]
        for item in on_file:
            lines += _exemption_lines(item)
        lines.append("")
    if eligible:
        lines += ["Eligible but not yet on file (claim these):", ""]
        for item, priced in zip(eligible, a.savings.exemptions):
            lines += _exemption_lines(item, priced)
        lines.append("")
    return lines


def _savings_table(a: Analysis) -> List[str]:
    s = a.savings
    if s.protest_blocked:
        rows = [["Protest (argued value is not below the capped appraised value)", "$0", "$0"]]
    else:
        label = ("Protest (reduction from the capped appraised value to the argued value)" if a.capped
                 else "Protest (reduction to the argued value)")
        rows = [[label, money(s.protest.low), money(s.protest.high)]]
    for item in s.exemptions:
        amount = money(item.annual) if item.quantified else "not quantified"
        rows.append([f"Exemption: {md(item.name)}", amount, amount])
    rows.append(["**Total per year**", f"**{money(s.total.low)}**", f"**{money(s.total.high)}**"])
    rate = a.case["tax_rates"]["total"]
    return [
        "## 5. Estimated savings", "",
        *_table(["Source", "Low scenario", "High scenario"], rows),
        *[line for note in savings_notes(s) for line in (note, "")],
        f"Based on a total tax rate of {rate:g} per $100 of value. Low and high are settlement scenarios "
        f"({scenario_text(s)}), not predictions. "
        "Exemptions count in full in both columns.",
        "",
    ]


def _rental_note(a: Analysis) -> List[str]:
    if not (a.income and a.income.circuit_breaker_note):
        return []
    return ["## 6. Appraisal-increase limit (circuit breaker)", "", md(a.income.circuit_breaker_note), ""]


def render_checklist(a: Analysis) -> str:
    case = a.case
    prepared = f" | Prepared {long_date(a.prepared_on)}" if a.prepared_on else ""
    header = [
        f"# Filing checklist: {md(case['subject']['address'])}",
        "",
        f"Tax year {case['tax_year']} | {md(case['county'])} | {md(case['cad']['name'])}{prepared}",
        "",
        f"**{meter_line(a.savings)}**",
        "",
        *[line for note in savings_notes(a.savings) for line in (note, "")],
    ]
    sections = [header, _numbers(a), _deadlines(a), _how_to_file(a), _hearing_documents(a),
                _exemptions(a), _savings_table(a), _rental_note(a), ["---", "", f"*{md(a.disclaimer)}*", ""]]
    return "\n".join(line for section in sections for line in section)


def write_checklist(a: Analysis, path: Path) -> None:
    write_text(path, render_checklist(a))
