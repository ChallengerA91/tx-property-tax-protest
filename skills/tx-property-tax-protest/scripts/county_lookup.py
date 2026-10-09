#!/usr/bin/env python3
"""Look up one county in references/counties.json without loading the whole file into a conversation.

  python county_lookup.py "Fort Bend"                 compact record
  python county_lookup.py "Fort Bend County" --full   adds sources, phone notes, v1 check, confidence
  python county_lookup.py fortbend --case-fragment    JSON for case.json: {"cad": {...}, "filing": {...}}
  python county_lookup.py --list                      the covered counties

Names are matched ignoring case, spaces, punctuation and the word "County"; a district abbreviation
such as HCAD also works. Exit codes: 0 found, 1 county not covered, 2 usage or data-file problem.
Data fields that are null mean "not confirmed" in counties.json and are shown that way.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from fmt import use_utf8_output

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "references" / "counties.json"
NOT_CONFIRMED = "not confirmed"
WIDTH = 100
METHOD_LABELS = {"online": "Online", "mail": "Mail", "fax": "Fax", "email": "E-mail", "in_person": "In person"}


class DataError(Exception):
    """counties.json is missing or unreadable."""


# --- loading and matching ---------------------------------------------------

def normalize(text: str) -> str:
    """'Fort Bend County' -> 'fortbend'."""
    without_county = re.sub(r"\bcounty\b", " ", text.lower())
    return re.sub(r"[^a-z0-9]", "", without_county)


def load_data(path: Path = DEFAULT_DATA) -> Dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise DataError(f"county data not found: {path}")
    except json.JSONDecodeError as exc:
        raise DataError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})")
    counties = data.get("counties") if isinstance(data, dict) else None
    if not isinstance(counties, list) or not all(isinstance(record, dict) for record in counties):
        raise DataError(f'{path}: expected an object with a "counties" list of county records')
    return data


def find_matches(data: Mapping[str, Any], query: str) -> List[Dict[str, Any]]:
    """Records matching the query. An exact county name wins; district abbreviations can be shared."""
    key = normalize(query)
    if not key:
        return []
    by_name = [r for r in data["counties"] if normalize(str(r.get("county") or "")) == key]
    if by_name:
        return by_name
    return [r for r in data["counties"] if normalize(str(r.get("cad_abbrev") or "")) == key]


def find_county(data: Mapping[str, Any], query: str) -> Optional[Dict[str, Any]]:
    """The one matching record, or None when nothing matches or the query is ambiguous."""
    matches = find_matches(data, query)
    return matches[0] if len(matches) == 1 else None


def covered_names(data: Mapping[str, Any]) -> List[str]:
    return [str(record.get("county", "?")) for record in data["counties"]]


def directory_url(data: Mapping[str, Any]) -> Optional[str]:
    """The Comptroller directory page, derived from the per-county links in the data."""
    for record in data["counties"]:
        link = record.get("comptroller_directory_url")
        if link:
            return link.rsplit("/", 1)[0] + "/"
    return None


# --- helpers ----------------------------------------------------------------

def is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def shown(value: Any) -> str:
    return NOT_CONFIRMED if is_empty(value) else str(value)


def wrap(text: str, indent: str = "") -> str:
    return textwrap.fill(text, width=WIDTH, initial_indent=indent, subsequent_indent=indent,
                         break_on_hyphens=False)


def first_sentence(text: str, limit: int = 160) -> str:
    sentence = re.split(r"(?<=[.;])\s", text.strip(), maxsplit=1)[0]
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"


def yes_no(value: Any) -> str:
    return NOT_CONFIRMED if value is None else ("yes" if value else "no")


def methods_text(record: Mapping[str, Any]) -> str:
    methods = record.get("filing_methods") or []
    return ", ".join(METHOD_LABELS.get(m, m.replace("_", " ")).lower() for m in methods) or NOT_CONFIRMED


def is_partial(record: Mapping[str, Any]) -> bool:
    return record.get("verification_status") != "verified"


# --- compact text view ------------------------------------------------------

def partial_banner(record: Mapping[str, Any]) -> List[str]:
    secondary = sorted((record.get("confidence") or {}))
    lines = [textwrap.fill(
        f"*** PARTIALLY VERIFIED (data checked {shown(record.get('verified_date'))}): something core is missing "
        "or rests on a non-district source. Confirm it with the district and your notice.",
        width=WIDTH, subsequent_indent="    ", break_on_hyphens=False)]
    if secondary:
        lines.append(f"    Secondary-source fields: {', '.join(secondary)}")
    if record.get("table_note"):
        lines.append(wrap(f"Note: {record['table_note']}", "    "))
    return lines


def portal_lines(record: Mapping[str, Any]) -> List[str]:
    portal = record.get("protest_portal")
    if is_empty(portal):
        return [f"Protest portal: {NOT_CONFIRMED}"]
    lines = [f"Protest portal: {shown(portal.get('name'))}", f"  URL: {shown(portal.get('url'))}"]
    if portal.get("requires"):
        lines.append(wrap(f"Requires: {portal['requires']}", "  "))
    return lines


def hearing_lines(record: Mapping[str, Any]) -> List[str]:
    info = record.get("informal_hearings") or {}
    lines = [f"Informal hearings: online {yes_no(info.get('online'))}, phone {yes_no(info.get('phone'))}, "
             f"in person {yes_no(info.get('in_person'))}"]
    if info.get("notes"):
        lines.append(wrap(info["notes"], "  "))
    return lines


def bulk_line(record: Mapping[str, Any], full: bool) -> str:
    bulk = record.get("bulk_data")
    if is_empty(bulk):
        return f"Bulk data: {NOT_CONFIRMED}"
    text = f"Bulk data: {shown(bulk.get('url'))}"
    detail = bulk.get("format")
    if detail:
        text += f" ({detail if full else first_sentence(detail)})"
    return text


def address_lines(record: Mapping[str, Any]) -> List[str]:
    address = record.get("correspondence_address") or {}
    return [wrap(f"Mailing address: {shown(address.get('mailing'))}"),
            wrap(f"Physical address: {shown(address.get('physical'))}")]


def render_record(record: Mapping[str, Any], full: bool = False) -> str:
    lines = [f"{record.get('county', '?')} County | population rank {shown(record.get('population_rank'))} | "
             f"verification: {shown(record.get('verification_status'))} | verified {shown(record.get('verified_date'))}"]
    if is_partial(record):
        lines += partial_banner(record)
    lines += [
        f"CAD: {shown(record.get('cad_name'))}",
        f"Website: {shown(record.get('website'))}",
        f"Phone: {shown(record.get('phone'))}",
        f"Property search: {shown(record.get('property_search_url'))}",
        *portal_lines(record),
        f"Filing methods: {methods_text(record)}",
        wrap(f"Filing notes: {shown(record.get('filing_notes'))}"),
        *hearing_lines(record),
        wrap(f"Notice timing: {shown(record.get('notice_timing'))}"),
        wrap(bulk_line(record, full)),
        *address_lines(record),
    ]
    quirks = record.get("quirks") or []
    lines.append("Quirks:" if quirks else f"Quirks: {NOT_CONFIRMED}")
    lines += [wrap(f"- {quirk}", "  ") for quirk in quirks]
    if full:
        lines += _full_extras(record)
    return "\n".join(lines)


def _full_extras(record: Mapping[str, Any]) -> List[str]:
    lines = ["", "--- full record extras ---",
             f"Population (2025 estimate): {shown(record.get('population_2025'))}",
             f"District abbreviation: {shown(record.get('cad_abbrev'))}",
             wrap(f"Phone notes: {shown(record.get('phone_notes'))}"),
             f"Comptroller directory page: {shown(record.get('comptroller_directory_url'))}"]
    if record.get("table_note") and not is_partial(record):
        lines.append(wrap(f"Table note: {record['table_note']}"))
    lines.append(f"Field confidence: {json.dumps(record.get('confidence') or {})}")
    lines.append(f"v1 check: {json.dumps(record.get('v1_check'), ensure_ascii=False)}")
    lines.append("Sources:" if record.get("sources") else f"Sources: {NOT_CONFIRMED}")
    lines += [wrap(f"- {source}", "  ") for source in record.get("sources") or []]
    return lines


# --- case.json fragment -----------------------------------------------------

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
FAX = re.compile(r"\bfax[^0-9(]{0,15}(\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})", re.IGNORECASE)
THROUGH_ZIP = re.compile(r"^.*?[^,]+,\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?")
TRAILING_PARENTHETICAL = re.compile(r"\s*\([^()]*\)\s*$")
CITY_STATE_ZIP = re.compile(r"^(?P<head>.*),\s*(?P<city>[^,]+),\s*(?P<state>[A-Z]{2})\s+(?P<zip>\d{5}(?:-\d{4})?)$")


def clean_address(text: str) -> str:
    """Keep the address and drop remarks about it: everything after the ZIP, or a closing '(...)'."""
    through_zip = THROUGH_ZIP.match(text)
    if through_zip:
        return through_zip.group(0).strip()
    while TRAILING_PARENTHETICAL.search(text):
        text = TRAILING_PARENTHETICAL.sub("", text)
    return text.strip().rstrip(".")


def letter_address(record: Mapping[str, Any]) -> Optional[str]:
    """Address block for the protest letter: the mailing address, else the physical one."""
    address = record.get("correspondence_address") or {}
    raw = address.get("mailing") or address.get("physical")
    if not raw:
        return None
    cleaned = clean_address(raw)
    match = CITY_STATE_ZIP.match(cleaned)
    if not match:
        return cleaned
    cad_name = normalize(record.get("cad_name") or "")
    head_lines = [line.strip() for line in match["head"].split(", ")]
    head_lines = [line for line in head_lines if normalize(line) != cad_name]
    return "\n".join(head_lines + [f"{match['city']}, {match['state']} {match['zip']}"])


def one_line(address: Optional[str]) -> str:
    return (address or "").replace("\n", ", ")


def method_detail(method: str, record: Mapping[str, Any]) -> str:
    notes = record.get("filing_notes") or ""
    address = record.get("correspondence_address") or {}
    if method == "online":
        portal = record.get("protest_portal") or {}
        label = portal.get("short_name") or portal.get("name")
        if not label:
            return f"Use the district's online filing option; see {shown(record.get('website'))}."
        requires = f" Needs: {first_sentence(portal['requires'], 240)}" if portal.get("requires") else ""
        return f"Use {label} at {shown(portal.get('url'))}.{requires}"
    if method == "mail":
        return f"Mail to {one_line(letter_address(record))}." if letter_address(record) else \
            "Mail to the address on your notice."
    if method == "in_person":
        physical = clean_address(address.get("physical") or "")
        return f"Deliver to {physical}." if physical else "Deliver to the district office."
    if method == "fax":
        found = FAX.search(notes)
        return f"Fax to {found.group(1)}." if found else "See the district's filing instructions for the fax number."
    if method == "email":
        protest = sorted({e for e in EMAIL.findall(notes) if "protest" in e.lower()}, key=str.lower)
        return f"E-mail to {' or '.join(protest)}." if protest else \
            "See the district's filing instructions for the e-mail address."
    return "See the district's filing instructions."


def case_fragment(record: Mapping[str, Any]) -> Dict[str, Any]:
    cad: Dict[str, Any] = {"name": record.get("cad_name")}
    address = letter_address(record)
    if address:
        cad["address"] = address
    for field, key in (("phone", "phone"), ("website", "website")):
        if record.get(key):
            cad[field] = record[key]
    methods = [{"method": METHOD_LABELS.get(m, m.replace("_", " ").capitalize()), "detail": method_detail(m, record)}
               for m in record.get("filing_methods") or []]
    notes = [record["filing_notes"]] if record.get("filing_notes") else []
    notes.append(f"District details checked on {shown(record.get('verified_date'))}; "
                 "the deadline and filing instructions printed on your notice always control.")
    if is_partial(record):
        notes.append("Only partly verified: confirm the filing options with the district before you file.")
    return {"cad": {k: v for k, v in cad.items() if v}, "filing": {"methods": methods, "notes": notes}}


def fragment_warnings(record: Mapping[str, Any], fragment: Mapping[str, Any]) -> List[str]:
    warnings = []
    if "address" not in fragment["cad"]:
        warnings.append("no mailing or physical address in the county data: fill cad.address by hand "
                        "(it is required for the letter)")
    elif not (record.get("correspondence_address") or {}).get("mailing"):
        warnings.append("no mailing address in the county data: cad.address is the physical address")
    if not fragment["filing"]["methods"]:
        warnings.append("no filing methods in the county data: add filing.methods by hand (at least one is required)")
    if "name" not in fragment["cad"]:
        warnings.append("no district name in the county data: fill cad.name by hand")
    return warnings


# --- command line -----------------------------------------------------------

def not_found_message(query: str, data: Mapping[str, Any]) -> str:
    link = directory_url(data)
    where = f"the Comptroller appraisal district directory ({link})" if link else "the Comptroller appraisal district directory"
    return "\n".join([
        f'"{query}" is not one of the {len(data["counties"])} counties covered.',
        "Covered: " + ", ".join(covered_names(data)),
        wrap(f"Look up the district in {where}, confirm the filing method on the district's own site and on your "
             "notice, and fill the cad block of case.json by hand."),
    ])


def ambiguous_message(query: str, matches: Sequence[Mapping[str, Any]]) -> str:
    options = ", ".join(f"{r.get('county', '?')} ({r.get('cad_name') or r.get('cad_abbrev') or '?'})"
                        for r in matches)
    return (f'"{query}" matches more than one district: {options}. Nothing was chosen. '
            f'Use the county name instead, for example "{matches[0].get("county", "?")}".')


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Look up a county's appraisal district and protest filing details.")
    parser.add_argument("county", nargs="?", help='county name, e.g. "Fort Bend" or "Fort Bend County"')
    parser.add_argument("--full", action="store_true", help="include sources, phone notes, v1 check and confidence")
    parser.add_argument("--case-fragment", action="store_true",
                        help="print JSON with the cad and filing blocks to merge into case.json")
    parser.add_argument("--list", action="store_true", dest="list_counties", help="list the covered counties")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="counties.json to read (default: references/)")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    use_utf8_output()
    args = _parse_args(argv)
    try:
        data = load_data(args.data)
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.list_counties:
        print("\n".join(f"{str(r.get('population_rank') or '?'):>2}  {r.get('county', '?')}  "
                        f"({r.get('verification_status') or '?'})" for r in data["counties"]))
        return 0
    if not args.county:
        print("error: give a county name (or use --list)", file=sys.stderr)
        return 2
    matches = find_matches(data, args.county)
    if not matches:
        print(not_found_message(args.county, data))
        return 1
    if len(matches) > 1:
        print(ambiguous_message(args.county, matches))
        return 1
    record = matches[0]
    if args.case_fragment:
        fragment = case_fragment(record)
        for warning in fragment_warnings(record, fragment):
            print(f"warning: {warning}", file=sys.stderr)
        print(json.dumps(fragment, indent=2, ensure_ascii=False))
    else:
        print(render_record(record, args.full))
    return 0


if __name__ == "__main__":
    sys.exit(main())
