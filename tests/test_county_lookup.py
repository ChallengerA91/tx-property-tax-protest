"""county_lookup: forgiving name matching, compact output, case.json fragments that validate."""
from __future__ import annotations

import copy
import json
import subprocess
import sys

import pytest

import county_lookup
from case_schema import validate_case
from conftest import SCRIPTS

DATA = county_lookup.load_data()
ALL_COUNTIES = county_lookup.covered_names(DATA)


def run(capsys, *args):
    code = county_lookup.main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def merged(homestead_case, fragment):
    case = copy.deepcopy(homestead_case)
    case["cad"] = fragment["cad"]
    case["filing"] = fragment["filing"]
    return case


# --- matching -----------------------------------------------------------------

@pytest.mark.parametrize("query", ["Fort Bend", "Fort Bend County", "fort bend", "FORTBEND", "  fort-bend  county ",
                                   "FORT BEND COUNTY", "fortbend county"])
def test_name_variants_find_fort_bend(query):
    assert county_lookup.find_county(DATA, query)["county"] == "Fort Bend"


@pytest.mark.parametrize("query, expected", [("El Paso", "El Paso"), ("elpaso county", "El Paso"),
                                             ("mclennan", "McLennan"), ("HCAD", "Harris"), ("webb", "Webb")])
def test_other_names_and_abbreviations(query, expected):
    assert county_lookup.find_county(DATA, query)["county"] == expected


@pytest.mark.parametrize("query", ["", "County", "Narnia", "Fort", "Bend County Nowhere"])
def test_unmatched_queries(query):
    assert county_lookup.find_county(DATA, query) is None


# --- compact record ------------------------------------------------------------

def test_compact_record_shows_the_core_fields(capsys):
    code, out, _ = run(capsys, "Fort Bend")
    assert code == 0
    for expected in ("Fort Bend County | population rank 8 | verification: verified | verified 2026-10-08",
                     "CAD: Fort Bend Central Appraisal District", "Website: https://www.fbcad.org/",
                     "Phone: 281-344-8623", "Property search:", "Protest portal: Online Appeal", "URL: https://webappeals",
                     "Requires:", "Filing methods: online, mail, in person", "Filing notes:", "Informal hearings:",
                     "Notice timing:", "Bulk data:", "Mailing address:", "Physical address:", "Quirks:"):
        assert expected in out
    assert "PARTIALLY VERIFIED" not in out


def test_compact_record_leaves_out_the_bulky_fields(capsys):
    _, out, _ = run(capsys, "Harris")
    assert "Telephone Information Center" not in out        # phone_notes
    assert "Sources:" not in out and "v1 check" not in out
    assert "census.gov" not in out


def test_full_adds_sources_phone_notes_and_v1_check(capsys):
    _, out, _ = run(capsys, "Harris", "--full")
    assert "Telephone Information Center" in out
    assert "Sources:" in out and "v1 check:" in out and "Field confidence:" in out
    assert "Comptroller directory page: https://comptroller.texas.gov/taxes/property-tax/county-directory/harris.php" in out


def test_compact_output_is_much_smaller_than_the_data_file(capsys):
    _, out, _ = run(capsys, "Harris")
    assert len(out) < 9000 and len(json.dumps(DATA)) > 100000


@pytest.mark.parametrize("county", ["Webb", "Nueces"])
def test_partial_counties_are_flagged_clearly(county, capsys):
    code, out, _ = run(capsys, county)
    assert code == 0
    assert "verification: partial | verified 2026-10-08" in out
    assert "*** PARTIALLY VERIFIED" in out and "Secondary-source fields:" in out
    assert "Confirm it with the district" in out


def test_webb_lists_the_fields_that_rest_on_secondary_sources(capsys):
    _, out, _ = run(capsys, "Webb")
    assert "filing_methods, informal_hearings, notice_timing" in out


def test_missing_values_are_shown_as_not_confirmed(tmp_path, capsys):
    data = {"counties": [{"county": "Blank", "cad_name": "Blank CAD", "verification_status": "partial",
                          "protest_portal": None, "filing_methods": [], "bulk_data": None, "phone_notes": None,
                          "informal_hearings": {"online": None, "phone": False, "in_person": True, "notes": None},
                          "correspondence_address": {"mailing": None, "physical": None}, "quirks": []}]}
    path = tmp_path / "counties.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    code, out, _ = run(capsys, "blank", "--data", str(path))
    assert code == 0
    assert "Phone: not confirmed" in out and "Protest portal: not confirmed" in out
    assert "Filing methods: not confirmed" in out and "Bulk data: not confirmed" in out
    assert "online not confirmed, phone no, in person yes" in out
    assert "Mailing address: not confirmed" in out and "Quirks: not confirmed" in out
    assert "PARTIALLY VERIFIED" in out


# --- not found ---------------------------------------------------------------------

def test_not_found_lists_counties_and_points_to_the_directory(capsys):
    code, out, _ = run(capsys, "Narnia")
    assert code == 1
    for name in ALL_COUNTIES:
        assert name in out
    assert "https://comptroller.texas.gov/taxes/property-tax/county-directory/" in out
    assert "by hand" in out and "Comptroller appraisal district directory" in out


def test_list_option(capsys):
    code, out, _ = run(capsys, "--list")
    assert code == 0 and len(out.strip().splitlines()) == 25 and "Fort Bend" in out


def test_usage_and_data_errors(capsys, tmp_path):
    assert run(capsys)[0] == 2
    code, _, err = run(capsys, "Harris", "--data", str(tmp_path / "missing.json"))
    assert code == 2 and "not found" in err
    bad = tmp_path / "bad.json"
    bad.write_text("{", encoding="utf-8")
    assert run(capsys, "Harris", "--data", str(bad))[0] == 2


# --- case.json fragment ---------------------------------------------------------------

def test_fragment_shape(capsys):
    code, out, err = run(capsys, "Cameron", "--case-fragment")
    assert code == 0 and err == ""
    fragment = json.loads(out)
    assert set(fragment) == {"cad", "filing"}
    assert fragment["cad"] == {"name": "Cameron Appraisal District", "address": "P.O. Box 1010\nSan Benito, TX 78586",
                               "phone": "956-399-9322", "website": "https://www.cameroncad.org"}
    methods = {m["method"]: m["detail"] for m in fragment["filing"]["methods"]}
    assert list(methods) == ["Mail", "Fax", "E-mail", "In person"]
    assert methods["Fax"] == "Fax to (956) 399-6969."
    assert methods["E-mail"] == "E-mail to protest@cameroncad.org."
    assert methods["In person"] == "Deliver to 2021 Amistad Drive, San Benito, TX 78586."
    assert fragment["filing"]["notes"][0].startswith("Per the CAD FAQ")


def test_fragment_address_drops_remarks_and_the_duplicate_district_name(capsys):
    harris = json.loads(run(capsys, "Harris", "--case-fragment")[1])
    assert harris["cad"]["address"] == "Assistance Center\nP.O. Box 922004\nHouston, TX 77292-2004"
    tarrant = json.loads(run(capsys, "Tarrant", "--case-fragment")[1])
    assert "protest filings" not in tarrant["cad"]["address"] and "P.O. Box 185519" in tarrant["cad"]["address"]
    denton = json.loads(run(capsys, "Denton", "--case-fragment")[1])
    assert denton["cad"]["address"] == "3911 Morse Street\nDenton, TX 76208"


def test_fragment_for_a_partial_county_says_so(capsys):
    fragment = json.loads(run(capsys, "Webb", "--case-fragment")[1])
    assert any("Only partly verified" in note for note in fragment["filing"]["notes"])
    assert any("checked on 2026-10-08" in note for note in fragment["filing"]["notes"])


def test_fragment_without_any_address_leaves_the_field_out_and_warns(tmp_path, capsys):
    data = {"counties": [{"county": "Blank", "cad_name": "Blank CAD", "phone": "555-0100", "filing_methods": ["online"],
                          "correspondence_address": {"mailing": None, "physical": None}}]}
    path = tmp_path / "counties.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    code, out, err = run(capsys, "blank", "--case-fragment", "--data", str(path))
    assert code == 0
    assert "address" not in json.loads(out)["cad"]
    assert "fill cad.address by hand" in err


def test_fragment_falls_back_to_the_physical_address_with_a_warning(tmp_path, capsys):
    data = {"counties": [{"county": "Half", "cad_name": "Half CAD", "filing_methods": ["in_person"],
                          "correspondence_address": {"mailing": None, "physical": "1 Main St, Austin, TX 78701"}}]}
    path = tmp_path / "counties.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    code, out, err = run(capsys, "half", "--case-fragment", "--data", str(path))
    assert json.loads(out)["cad"]["address"] == "1 Main St\nAustin, TX 78701"
    assert "physical address" in err


@pytest.mark.parametrize("county", ALL_COUNTIES)
def test_every_county_fragment_validates_in_a_case(county, capsys, homestead_case):
    code, out, err = run(capsys, county, "--case-fragment")
    assert code == 0 and err == "", err
    assert validate_case(merged(homestead_case, json.loads(out))) == []


def test_fragment_builds_a_package(capsys, tmp_path, write_case, homestead_case):
    import build_package
    fragment = json.loads(run(capsys, "Fort Bend", "--case-fragment")[1])
    out_dir = tmp_path / "out"
    build_package.build_package(write_case(merged(homestead_case, fragment)), out_dir)
    checklist = (out_dir / "filing_checklist.md").read_text(encoding="utf-8")
    assert "Fort Bend Central Appraisal District" in checklist and "Rosenberg" in checklist


# --- as a script -----------------------------------------------------------------------

def test_command_line_exit_codes():
    script = str(SCRIPTS / "county_lookup.py")
    found = subprocess.run([sys.executable, script, "fortbend"], capture_output=True, text=True, encoding="utf-8")
    assert found.returncode == 0 and "Fort Bend Central Appraisal District" in found.stdout
    missing = subprocess.run([sys.executable, script, "Atlantis"], capture_output=True, text=True, encoding="utf-8")
    assert missing.returncode == 1 and "Comptroller" in missing.stdout
