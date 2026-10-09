"""End to end: build_package on both sample cases, plus the cross-output rules (disclaimer, determinism)."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from docx import Document
from openpyxl import load_workbook

import build_package
from analysis import DEFAULT_DISCLAIMER
from conftest import EXAMPLES, SCRIPTS, read_json

OUTPUTS = ["comp_analysis.xlsx", "protest_letter.docx", "filing_checklist.md", "dashboard.html", "deadlines.ics"]


@pytest.fixture(scope="module")
def homestead(tmp_path_factory):
    out = tmp_path_factory.mktemp("homestead")
    build_package.build_package(EXAMPLES / "sample-case.json", out)
    return out


@pytest.fixture(scope="module")
def capped(tmp_path_factory):
    out = tmp_path_factory.mktemp("capped")
    build_package.build_package(EXAMPLES / "sample-case-capped.json", out)
    return out


@pytest.fixture(scope="module")
def rental(tmp_path_factory):
    out = tmp_path_factory.mktemp("rental")
    build_package.build_package(EXAMPLES / "sample-case-rental.json", out)
    return out


def letter_text(folder: Path) -> str:
    document = Document(folder / "protest_letter.docx")
    parts = [p.text for p in document.paragraphs]
    parts += [cell.text for table in document.tables for row in table.rows for cell in row.cells]
    return "\n".join(parts)


def sheet_text(sheet) -> str:
    return "\n".join(str(cell.value) for row in sheet.iter_rows() for cell in row if cell.value is not None)


def find_row(sheet, label):
    for row in sheet.iter_rows():
        if row[0].value == label:
            return row
    raise AssertionError(f"no row labelled {label!r} on sheet {sheet.title!r}")


# --- outputs exist and open -------------------------------------------------

@pytest.mark.parametrize("folder", ["homestead", "rental", "capped"])
def test_all_outputs_are_written(folder, request):
    out = request.getfixturevalue(folder)
    for name in OUTPUTS:
        assert (out / name).stat().st_size > 0, name


def test_xlsx_opens_with_expected_sheets(homestead, rental):
    assert load_workbook(homestead / "comp_analysis.xlsx").sheetnames == [
        "Comp Analysis", "Adjustments", "Unequal Appraisal"]
    assert load_workbook(rental / "comp_analysis.xlsx").sheetnames == [
        "Comp Analysis", "Adjustments", "Unequal Appraisal", "Income Approach"]


def test_xlsx_summary_numbers(homestead):
    sheet = load_workbook(homestead / "comp_analysis.xlsx")["Comp Analysis"]
    assert find_row(sheet, "Median adjusted value")[1].value == 421000
    assert find_row(sheet, "Average adjusted value")[1].value == pytest.approx(421180)
    assert find_row(sheet, "CAD appraised value")[1].value == 465000
    assert find_row(sheet, "Argued market value")[1].value == 425000
    assert find_row(sheet, "Potential reduction")[1].value == 40000
    assert find_row(sheet, "Savings meter")[1].value == "Estimated savings so far: $1,060 to $1,490 per year"


def test_xlsx_comp_table_has_one_row_per_comp(homestead, homestead_case):
    sheet = load_workbook(homestead / "comp_analysis.xlsx")["Comp Analysis"]
    addresses = {comp["address"] for comp in homestead_case["comps"]}
    found = {row[0].value for row in sheet.iter_rows() if row[0].value in addresses}
    assert found == addresses


def test_xlsx_unequal_sheet_has_rank_and_percentile(homestead):
    sheet = load_workbook(homestead / "comp_analysis.xlsx")["Unequal Appraisal"]
    assert find_row(sheet, "Subject rank (1 = highest)")[1].value == "2 of 9"
    assert find_row(sheet, "Subject percentile")[1].value == "88%"
    assert find_row(sheet, "Neighbor median $ / sq ft")[1].value == pytest.approx(205.555, abs=0.01)


def test_xlsx_income_sheet(rental):
    sheet = load_workbook(rental / "comp_analysis.xlsx")["Income Approach"]
    assert find_row(sheet, "Net operating income (NOI)")[1].value == pytest.approx(18696)
    assert find_row(sheet, "Income-indicated value (NOI / cap rate)")[1].value == pytest.approx(267085.71, abs=0.01)
    assert "Sample broker survey" in sheet_text(sheet)
    assert "is not in effect for tax year 2027" in sheet_text(sheet)


def test_homestead_has_no_income_sheet(homestead):
    assert "Income Approach" not in load_workbook(homestead / "comp_analysis.xlsx").sheetnames


# --- letter ------------------------------------------------------------------

def test_letter_contents(homestead, homestead_case):
    text = letter_text(homestead)
    for expected in (
        homestead_case["owner"]["name"],
        homestead_case["cad"]["name"],
        homestead_case["subject"]["cad_account"],
        homestead_case["subject"]["address"],
        homestead_case["legal_basis"]["market_value_cite"],
        homestead_case["legal_basis"]["unequal_cite"],
        "$465,000", "$425,000", "$40,000",
        "118 Sample Court",
        "Respectfully submitted",
    ):
        assert expected in text


def test_letter_for_market_only_strategy_omits_unequal_material(tmp_path, write_case, homestead_case):
    homestead_case["strategy"] = "market_value"
    build_package.build_package(write_case(homestead_case), tmp_path / "out")
    text = letter_text(tmp_path / "out")
    assert homestead_case["legal_basis"]["market_value_cite"] in text
    assert homestead_case["legal_basis"]["unequal_cite"] not in text
    assert "Neighboring properties" not in text


def test_rental_letter_has_income_table(rental):
    text = letter_text(rental)
    assert "Income approach" in text and "Net operating income" in text and "$18,696" in text


def test_letter_has_no_disclaimer(homestead, rental, homestead_case):
    for folder in (homestead, rental):
        text = letter_text(folder).lower()
        assert "disclaimer" not in text
        assert "not legal, tax, or appraisal advice" not in text
        assert "does not guarantee" not in text
    assert homestead_case["disclaimer_text"] not in letter_text(homestead)


def test_letter_without_custom_disclaimer_still_has_none(tmp_path, write_case, homestead_case):
    del homestead_case["disclaimer_text"]
    build_package.build_package(write_case(homestead_case), tmp_path / "out")
    assert DEFAULT_DISCLAIMER not in letter_text(tmp_path / "out")
    assert "not legal, tax, or appraisal advice" not in letter_text(tmp_path / "out")


def test_letter_date_is_blank_line_without_prepared_on(tmp_path, write_case, homestead_case):
    del homestead_case["prepared_on"]
    build_package.build_package(write_case(homestead_case), tmp_path / "out")
    assert "Date: ____" in letter_text(tmp_path / "out")


# --- disclaimer on every other output ---------------------------------------

def test_disclaimer_appears_in_xlsx_checklist_and_dashboard(homestead, rental, homestead_case, rental_case):
    for folder, case in ((homestead, homestead_case), (rental, rental_case)):
        disclaimer = case["disclaimer_text"]
        workbook = load_workbook(folder / "comp_analysis.xlsx")
        for sheet in workbook.worksheets:
            assert disclaimer in sheet_text(sheet), sheet.title
        assert disclaimer in (folder / "filing_checklist.md").read_text(encoding="utf-8")
        assert disclaimer in (folder / "dashboard.html").read_text(encoding="utf-8")


def test_default_disclaimer_used_when_case_has_none(tmp_path, write_case, homestead_case):
    del homestead_case["disclaimer_text"]
    out = tmp_path / "out"
    build_package.build_package(write_case(homestead_case), out)
    assert DEFAULT_DISCLAIMER in (out / "filing_checklist.md").read_text(encoding="utf-8")
    assert DEFAULT_DISCLAIMER in (out / "dashboard.html").read_text(encoding="utf-8")
    assert DEFAULT_DISCLAIMER in sheet_text(load_workbook(out / "comp_analysis.xlsx")["Comp Analysis"])


# --- checklist ----------------------------------------------------------------

def test_checklist_contents(homestead, homestead_case):
    text = (homestead / "filing_checklist.md").read_text(encoding="utf-8")
    assert "Estimated savings so far: $1,060 to $1,490 per year" in text
    assert "Mon, May 17, 2027" in text
    for method in homestead_case["filing"]["methods"]:
        assert method["method"] in text and method["detail"] in text
    for item in homestead_case["exemptions"]["eligible"]:
        assert item["name"] in text and item["how_to_claim"] in text
    for extra in homestead_case["filing"]["hearing_documents"]:
        assert extra in text
    assert "| **Total per year** | **$1,060** | **$1,490** |" in text


def test_rental_checklist_has_circuit_breaker_note_and_income_documents(rental, rental_case):
    text = (rental / "filing_checklist.md").read_text(encoding="utf-8")
    assert rental_case["income"]["circuit_breaker_note"] in text
    assert "rent roll" in text
    assert "No exemptions were identified" in text


# --- dashboard ------------------------------------------------------------------

EXTERNAL = [
    r'(?:src|href|action|poster|data)\s*=\s*["\']?\s*(?:https?:)?//',
    r"url\(\s*[\"']?\s*(?:https?:)?//",
    r"@import",
    r"<link\b",
    r"<script[^>]+\bsrc\s*=",
    r"<iframe",
    r"<img\b",
]


@pytest.mark.parametrize("folder", ["homestead", "rental", "capped"])
def test_dashboard_is_self_contained(folder, request):
    html = (request.getfixturevalue(folder) / "dashboard.html").read_text(encoding="utf-8")
    for pattern in EXTERNAL:
        assert not re.search(pattern, html, re.I), pattern
    assert "<style>" in html and "<svg" in html


def test_dashboard_accessibility_and_responsive_basics(homestead):
    html = (homestead / "dashboard.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in html
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert "prefers-color-scheme: dark" in html
    assert "<main" in html and "<h1>" in html and "<caption>" in html
    assert html.count('role="img"') == 2 and "<title id=" in html and "<desc id=" in html
    assert 'scope="col"' in html and 'scope="row"' in html
    assert "<title>Protest dashboard - 123 Example Street" in html


def test_dashboard_shows_key_numbers(homestead):
    html = (homestead / "dashboard.html").read_text(encoding="utf-8")
    for expected in ("$465,000", "$425,000", "$40,000", "Estimated savings so far: $1,060 to $1,490 per year",
                     "Protest filing deadline", 'datetime="2027-05-17"', "ranks 2 of 9"):
        assert expected in html


def test_rental_dashboard_has_income_indicated_value(rental):
    html = (rental / "dashboard.html").read_text(encoding="utf-8")
    assert "Income-indicated value" in html and "$267,086" in html


def test_dashboard_escapes_markup_from_the_case(tmp_path, write_case, homestead_case):
    homestead_case["subject"]["address"] = "1 <b>Bold</b> & Co Street, Exampleville, TX"
    homestead_case["comps"][0]["address"] = '2 "Quote" <script>x</script>, Exampleville, TX'
    out = tmp_path / "out"
    build_package.build_package(write_case(homestead_case), out)
    html = (out / "dashboard.html").read_text(encoding="utf-8")
    assert "<b>Bold</b>" not in html and "<script>x</script>" not in html
    assert "&lt;b&gt;Bold&lt;/b&gt; &amp; Co Street" in html


# --- deadlines.ics ----------------------------------------------------------------

def test_package_ics(homestead, rental):
    text = (homestead / "deadlines.ics").read_bytes().decode("utf-8")
    assert text.count("BEGIN:VEVENT") == 4 and "DTSTART;VALUE=DATE:20270517" in text
    assert "DTSTART;VALUE=DATE:20270430" in text and "DTSTART;VALUE=DATE:20280201" in text
    assert "DTSTART;VALUE=DATE:20270524" in (rental / "deadlines.ics").read_bytes().decode("utf-8")


# --- determinism --------------------------------------------------------------------

@pytest.mark.parametrize("case_file", ["sample-case.json", "sample-case-rental.json", "sample-case-capped.json"])
def test_two_builds_are_byte_identical(case_file, tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    build_package.build_package(EXAMPLES / case_file, first)
    build_package.build_package(EXAMPLES / case_file, second)
    for name in OUTPUTS:
        assert (first / name).read_bytes() == (second / name).read_bytes(), name


def test_rebuilding_across_a_clock_tick_is_byte_identical(tmp_path):
    """openpyxl stamps 'modified' with the current time; the build must pin it."""
    build_package.build_package(EXAMPLES / "sample-case.json", tmp_path / "a")
    time.sleep(1.2)
    build_package.build_package(EXAMPLES / "sample-case.json", tmp_path / "b")
    for name in OUTPUTS:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def normalized(path: Path) -> str:
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")


@pytest.mark.parametrize("case_file, folder", [("sample-case.json", "homestead"), ("sample-case-rental.json", "rental"),
                                          ("sample-case-capped.json", "capped")])
def test_committed_sample_output_is_current(case_file, folder, tmp_path):
    """Regenerate with: python build_package.py examples/<case> --out examples/sample-output/<folder>"""
    build_package.build_package(EXAMPLES / case_file, tmp_path)
    for name in ("filing_checklist.md", "dashboard.html", "deadlines.ics"):
        assert normalized(tmp_path / name) == normalized(EXAMPLES / "sample-output" / folder / name), name


# --- robustness: missing values ---------------------------------------------------------

def test_comp_with_only_required_fields_builds_everything(tmp_path, write_case, homestead_case):
    homestead_case["comps"] = [{"address": "9 Bare Street, Exampleville, TX 75000", "price": 410000},
                               homestead_case["comps"][0]]
    out = tmp_path / "out"
    build_package.build_package(write_case(homestead_case), out)
    sheet = load_workbook(out / "comp_analysis.xlsx")["Comp Analysis"]
    bare = next(row for row in sheet.iter_rows() if row[0].value == "9 Bare Street, Exampleville, TX 75000")
    assert bare[3].value == 410000 and bare[4].value == "—"
    assert "9 Bare Street" in (out / "dashboard.html").read_text(encoding="utf-8")


def test_rental_without_comps_or_neighbors_builds(tmp_path, write_case, rental_case):
    rental_case["comps"], rental_case["neighbors"] = [], []
    out = tmp_path / "out"
    build_package.build_package(write_case(rental_case), out)
    workbook = load_workbook(out / "comp_analysis.xlsx")
    assert workbook.sheetnames == ["Comp Analysis", "Adjustments", "Income Approach"]
    assert "Income-indicated value" in (out / "dashboard.html").read_text(encoding="utf-8")


def test_unequal_only_homestead_without_comps_builds(tmp_path, write_case, homestead_case):
    homestead_case["strategy"] = "unequal_appraisal"
    homestead_case["comps"] = []
    out = tmp_path / "out"
    build_package.build_package(write_case(homestead_case), out)
    text = letter_text(out)
    assert homestead_case["legal_basis"]["unequal_cite"] in text and "Comparable sales" not in text


def test_notice_date_drives_the_deadline_when_no_list_given(tmp_path, write_case, homestead_case):
    homestead_case["notice_date"] = "2027-04-20"
    out = tmp_path / "out"
    build_package.build_package(write_case(homestead_case), out)
    assert "Thu, May 20, 2027" in (out / "filing_checklist.md").read_text(encoding="utf-8")


# --- command line -------------------------------------------------------------------------

def run_cli(*args):
    return subprocess.run([sys.executable, str(SCRIPTS / "build_package.py"), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8")


def test_cli_builds_and_prints_summary(tmp_path):
    result = run_cli(EXAMPLES / "sample-case.json", "--out", tmp_path / "out")
    assert result.returncode == 0, result.stderr
    assert "PROPERTY TAX PROTEST SUMMARY" in result.stdout
    assert "Estimated savings so far: $1,060 to $1,490 per year" in result.stdout
    assert (tmp_path / "out" / "comp_analysis.xlsx").exists()


def test_cli_lists_every_validation_problem(tmp_path, write_case, homestead_case):
    del homestead_case["owner"]
    homestead_case["subject"]["sqft"] = "big"
    result = run_cli(write_case(homestead_case), "--out", tmp_path / "out")
    assert result.returncode == 2
    assert "owner: required field is missing" in result.stderr
    assert "subject.sqft: must be a number" in result.stderr
    assert not (tmp_path / "out").exists()


def test_cli_without_out_is_a_usage_error(tmp_path):
    assert run_cli(EXAMPLES / "sample-case.json").returncode == 2


def test_scripts_contain_no_hardcoded_statute_cites():
    """Statute cites, exemption amounts and tax rates come from case.json, never from code."""
    offenders = [path.name for path in SCRIPTS.glob("*.py")
                 if re.search(r"§|Tax Code|Gov't Code", path.read_text(encoding="utf-8"))]
    assert offenders == []


def test_minimal_example_in_schema_doc_is_valid_and_builds(tmp_path):
    doc = (SCRIPTS.parent / "references" / "case-schema.md").read_text(encoding="utf-8")
    block = re.search(r"## Minimal example\s+```json\n(.*?)```", doc, re.S).group(1)
    case_path = tmp_path / "minimal.json"
    case_path.write_text(block, encoding="utf-8")
    out = tmp_path / "out"
    build_package.build_package(case_path, out)
    assert (out / "protest_letter.docx").exists()
    assert "Estimated savings so far: $376 to $753 per year" in (out / "filing_checklist.md").read_text(encoding="utf-8")


def test_sample_cases_are_fictional():
    for name in ("sample-case.json", "sample-case-rental.json"):
        text = (EXAMPLES / name).read_text(encoding="utf-8")
        assert "Example" in text and ".invalid" in text
        assert read_json(EXAMPLES / name)["cad"]["website"].endswith(".invalid")


# --- samples follow references/law-and-figures.md -------------------------------------

def test_homestead_sample_uses_the_researched_figures_and_cites(homestead_case):
    assert homestead_case["legal_basis"]["market_value_cite"] == "Tax Code §41.41(a)(1)"
    assert homestead_case["legal_basis"]["unequal_cite"] == "Tax Code §41.41(a)(2)"
    [on_file] = homestead_case["exemptions"]["on_file"]
    assert (on_file["amount"], on_file["applies_to"], on_file["cite"]) == (140000, "school", "Tax Code §11.13(b)")
    over_65, freeze = homestead_case["exemptions"]["eligible"]
    assert (over_65["amount"], over_65["applies_to"], over_65["cite"]) == (60000, "school", "Tax Code §11.13(c)")
    assert "Form 50-114" in over_65["how_to_claim"] and "Form 50-132" in homestead_case["legal_basis"]["protest_form"]
    assert "amount" not in freeze                      # a tax ceiling is listed but not priced


def test_rental_sample_does_not_claim_the_circuit_breaker(rental, rental_case):
    note = rental_case["income"]["circuit_breaker_note"]
    assert "Tax Code §23.231" in note and "expires December 31, 2026" in note
    assert "not in effect for tax year 2027" in note
    assert rental_case["tax_year"] == 2027
    for name in ("filing_checklist.md", "dashboard.html"):
        text = (rental / name).read_text(encoding="utf-8")
        assert note in text or note.replace("'", "&#x27;") in text
    # no output other than the note itself mentions the limit as available
    assert "circuit" not in " ".join(rental_case["arguments"] + rental_case["market_notes"]).lower()


# --- capped homestead: protest market value, tax is based on the capped appraised value ----------

NO_SAVINGS = "No protest savings this year: your argued value is above the capped appraised value"


def test_capped_letter_protests_the_market_value(capped, capped_case):
    text = letter_text(capped)
    assert "CAD market value: $520,000" in text and "Taxable (capped) appraised value: $462,000" in text
    assert "protest its 2027 market value of $520,000 and ask that it be reduced to $470,000" in text
    assert "a reduction of $50,000 (9.6%)" in text and "reduced from $520,000 to $470,000" in text
    assert text.count("$462,000") == 1 and text.count("appraised value") == 1       # only the labeled taxable figure
    assert "$48,000 below the market value" in text        # 520,000 - median adjusted 472,000
    assert capped_case["disclaimer_text"] not in text


def test_capped_xlsx_shows_both_values_and_zero_protest_savings(capped):
    workbook = load_workbook(capped / "comp_analysis.xlsx")
    sheet = workbook["Comp Analysis"]
    assert find_row(sheet, "CAD market value")[1].value == 520000
    assert find_row(sheet, "Taxable (capped) appraised value")[1].value == 462000
    assert find_row(sheet, "Reduction in market value")[1].value == 50000
    assert find_row(sheet, "Reduction below the taxable (capped) value")[1].value == 0
    assert find_row(sheet, "Annual tax savings from protest")[1].value == "$0"
    meter = find_row(sheet, "Savings meter")[1].value
    assert meter.startswith("Estimated savings so far: $660 per year.") and NO_SAVINGS in meter


def test_capped_checklist_says_so_plainly(capped):
    text = (capped / "filing_checklist.md").read_text(encoding="utf-8")
    assert "**Estimated savings so far: $660 per year**" in text and NO_SAVINGS in text
    assert "| CAD market value | $520,000 |" in text
    assert "| Taxable (capped) appraised value (the value your tax is based on) | $462,000 |" in text
    assert "| Reduction in market value | $50,000 (9.6%) |" in text
    assert "| Reduction below the taxable (capped) value | $0 |" in text
    assert "| Protest (argued value is not below the capped appraised value) | $0 | $0 |" in text
    assert "-$" not in text.replace("Tax Code", "")


def test_capped_dashboard_shows_market_and_capped_values(capped):
    html = (capped / "dashboard.html").read_text(encoding="utf-8")
    for expected in ("CAD market value", "$520,000", "Taxable (capped) appraised value", "$462,000",
                     "the value your tax is based on", "Reduction below the taxable (capped) value",
                     NO_SAVINGS, "Market $520,000", "Taxable (capped) $462,000", 'class="ref-capped"',
                     "Protest (argued value is not below the capped appraised value)"):
        assert expected in html
    assert re.search(r"Estimated savings per year</dt><dd><span class=\"big\">\$660<", html)    # no negative or range


def test_capped_case_with_argued_value_below_the_cap_has_real_savings(tmp_path, write_case, capped_case):
    capped_case["argued_value"] = 440000
    out = tmp_path / "out"
    build_package.build_package(write_case(capped_case), out)
    checklist = (out / "filing_checklist.md").read_text(encoding="utf-8")
    assert "**Estimated savings so far: $660 to $1,144 per year**" in checklist
    assert NO_SAVINGS not in checklist
    # the low scenario takes half of the 80,000 market reduction (to 480,000), still above the 462,000 cap
    assert "| Protest (reduction from the capped appraised value to the argued value) | $0 | $484 |" in checklist
    assert "| Reduction in market value | $80,000 (15.4%) |" in checklist     # the protest still asks for the market cut
    assert "| Reduction below the taxable (capped) value | $22,000 |" in checklist
    sheet = load_workbook(out / "comp_analysis.xlsx")["Comp Analysis"]
    assert find_row(sheet, "Reduction below the taxable (capped) value")[1].value == 22000
    assert find_row(sheet, "Annual tax savings from protest")[1].value == "$0 to $484"


def test_uncapped_outputs_never_mention_a_cap(homestead, rental):
    for folder in (homestead, rental):
        for name in ("filing_checklist.md", "dashboard.html"):
            text = (folder / name).read_text(encoding="utf-8")
            assert "Capped appraised" not in text and 'class="ref-capped"' not in text
        checklist = (folder / "filing_checklist.md").read_text(encoding="utf-8")
        assert "apped" not in checklist and NO_SAVINGS not in checklist
        sheet = load_workbook(folder / "comp_analysis.xlsx")["Comp Analysis"]
        assert "Capped appraised value (taxable)" not in sheet_text(sheet)


def test_market_value_equal_to_appraised_builds_identical_outputs(tmp_path, write_case, homestead_case):
    build_package.build_package(write_case(homestead_case), tmp_path / "a")
    homestead_case["subject"]["market_value"] = homestead_case["subject"]["appraised_value"]
    build_package.build_package(write_case(homestead_case, "explicit.json"), tmp_path / "b")
    for name in OUTPUTS:
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes(), name


def test_capped_cli_summary_lists_both_values(tmp_path):
    result = run_cli(EXAMPLES / "sample-case-capped.json", "--out", tmp_path / "out")
    assert result.returncode == 0, result.stderr
    assert "CAD market value:    $520,000" in result.stdout and "Taxable (capped):    $462,000" in result.stdout
    assert NO_SAVINGS in result.stdout
