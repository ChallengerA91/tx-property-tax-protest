#!/usr/bin/env python3
"""Build the full protest evidence package from a case.json.

  python build_package.py case.json --out OUTPUT_DIR

Writes comp_analysis.xlsx, protest_letter.docx, filing_checklist.md,
dashboard.html and deadlines.ics. Output depends only on the case file (no
clock, no network): the same case, run with the same Python and library
versions, gives byte-identical files. Files are built in a staging folder and
moved into OUTPUT_DIR only when all of them were written, so a failed or
locked write never leaves a mixed package.

Exit codes: 0 built, 2 the case is invalid, 1 the files could not be written.
Field reference: references/case-schema.md
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import deadlines as deadline_engine
from analysis import Analysis, build_analysis
from case_schema import CaseError, case_warnings, load_case
from fmt import long_date, money, percent, use_utf8_output
from render_checklist import write_checklist
from render_dashboard import write_dashboard
from render_docx import write_letter
from render_xlsx import write_xlsx
from savings import meter_for

ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
UNIX = 3     # ZipInfo.create_system: the same value on every platform

OUTPUT_NAMES = {
    "xlsx": "comp_analysis.xlsx",
    "docx": "protest_letter.docx",
    "checklist": "filing_checklist.md",
    "dashboard": "dashboard.html",
    "ics": "deadlines.ics",
}

CORE_MODIFIED = re.compile(rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)")


def normalize_zip(path: Path, stamp: dt.datetime) -> None:
    """Rewrite an OOXML zip so rebuilds are byte-identical.

    Entry timestamps, the creating system and the entry order are fixed, entries are stored
    uncompressed (so the zlib version cannot change the bytes), and openpyxl's habit of stamping
    the current time into docProps/core.xml is replaced by the case's own date.
    """
    modified = stamp.strftime("%Y-%m-%dT%H:%M:%SZ").encode("ascii")
    temp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(temp, "w", zipfile.ZIP_STORED) as target:
        for info in sorted(source.infolist(), key=lambda i: i.filename):
            data = source.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = CORE_MODIFIED.sub(lambda m: m.group(1) + modified + m.group(2), data)
            entry = zipfile.ZipInfo(info.filename, date_time=ZIP_EPOCH)
            entry.compress_type = zipfile.ZIP_STORED
            entry.create_system = UNIX
            entry.external_attr = 0o600 << 16
            target.writestr(entry, data)
    os.replace(temp, path)


def write_ics_file(a: Analysis, path: Path) -> None:
    stamp = a.timestamp.replace(tzinfo=dt.timezone.utc)
    deadline_engine.write_ics(path, deadline_engine.build_ics(a.deadlines, a.case["tax_year"], stamp))


def _write_all(a: Analysis, folder: Path) -> None:
    write_xlsx(a, folder / OUTPUT_NAMES["xlsx"])
    normalize_zip(folder / OUTPUT_NAMES["xlsx"], a.timestamp)
    write_letter(a, folder / OUTPUT_NAMES["docx"])
    normalize_zip(folder / OUTPUT_NAMES["docx"], a.timestamp)
    write_checklist(a, folder / OUTPUT_NAMES["checklist"])
    write_dashboard(a, folder / OUTPUT_NAMES["dashboard"])
    write_ics_file(a, folder / OUTPUT_NAMES["ics"])


def _publish(staging: Path, out_dir: Path) -> None:
    """Move the staged files into out_dir. If any file cannot be replaced, the earlier ones are put back."""
    backup = Path(tempfile.mkdtemp(prefix=".backup-", dir=out_dir))
    placed: List[Tuple[Path, Optional[Path]]] = []
    keep_backup = False
    try:
        for name in OUTPUT_NAMES.values():
            target = out_dir / name
            saved = backup / name if target.exists() else None
            if saved:
                os.replace(target, saved)
            placed.append((target, saved))
            os.replace(staging / name, target)
    except OSError:
        keep_backup = not _restore(placed)
        raise
    finally:
        if not keep_backup:
            shutil.rmtree(backup, ignore_errors=True)


def _restore(placed: Sequence[Tuple[Path, Optional[Path]]]) -> bool:
    """Put the original files back; False when something could not be restored (the backup folder is kept)."""
    restored = True
    for target, saved in reversed(placed):
        try:
            if target.exists():
                target.unlink()
            if saved and saved.exists():
                os.replace(saved, target)
        except OSError:
            restored = False
    return restored


def build_package(case_path: Path, out_dir: Path) -> Analysis:
    """Validate the case and write every output; raises CaseError on invalid input, OSError on a write failure."""
    analysis = build_analysis(load_case(case_path))
    out_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=out_dir))
    try:
        _write_all(analysis, staging)
        _publish(staging, out_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return analysis


def package_warnings(a: Analysis) -> List[str]:
    """Things to look at that do not stop the build."""
    warnings = case_warnings(a.case)
    if a.income and not a.income_supports_reduction:
        warnings.append(f"Income approach indicates {money(a.income.indicated_value)}, above the CAD value; "
                        "it is not used in the letter")
    return warnings


def summary_text(a: Analysis, out_dir: Path) -> str:
    """Plain-text results block for the hand-off step."""
    case = a.case
    lines = [
        "PROPERTY TAX PROTEST SUMMARY",
        "============================",
        f"Subject:             {case['subject']['address']}",
        f"CAD account:         {case['subject']['cad_account']}",
        *([f"CAD market value:    {money(a.market_value)}",
           f"Taxable (capped):    {money(a.appraised_value)}"] if a.capped
          else [f"Current appraised:   {money(a.appraised_value)}"]),
        f"Argued value:        {money(a.argued_value)}",
        f"Requested reduction: {money(a.reduction)} ({percent(a.reduction_pct)})",
    ]
    if a.capped:
        lines.append(f"Below taxable value: {money(a.savings.reduction)}")
    if a.median_adjusted is not None:
        lines.append(f"Median adjusted comp: {money(a.median_adjusted)}")
    if a.unequal:
        lines.append(f"Unequal appraisal:   rank {a.unequal.rank} of {a.unequal.group_size} by $/sq ft "
                     f"(median-equalized value {money(a.unequal.indicated_value)})")
    if a.income:
        lines.append(f"Income-indicated:    {money(a.income.indicated_value)}")
    lines += ["", meter_for(a.savings), "", "Deadlines:"]
    lines += [f"  {long_date(d.date)}: {d.event}" for d in a.deadlines]
    lines += ["", "Files:"] + [f"  {out_dir / name}" for name in OUTPUT_NAMES.values()]
    return "\n".join(lines)


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the protest evidence package from case.json.")
    parser.add_argument("case", type=Path, help="path to case.json")
    parser.add_argument("--out", type=Path, required=True, help="directory for the generated files")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    use_utf8_output()
    args = _parse_args(argv)
    try:
        analysis = build_package(args.case, args.out)
    except CaseError as exc:
        print(f"{args.case} is not a valid case ({len(exc.errors)} problem(s)):", file=sys.stderr)
        for error in exc.errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    except deadline_engine.RuleError as exc:
        print(f"deadline rules problem: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Could not write the package to {args.out}: {exc.strerror or exc}. "
              "Close any open copies of the files and try again; nothing was changed.", file=sys.stderr)
        return 1
    for warning in package_warnings(analysis):
        print(f"warning: {warning}", file=sys.stderr)
    print(summary_text(analysis, args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
