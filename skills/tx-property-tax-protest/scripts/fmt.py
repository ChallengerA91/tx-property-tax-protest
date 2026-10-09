"""Small, deterministic formatting helpers shared by every renderer."""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional

MISSING = "—"  # em dash shown where a value is not available


def use_utf8_output() -> None:
    """Make CLI output survive legacy Windows console code pages (section signs, dashes)."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    """UTF-8 with LF newlines on every platform, so output bytes do not depend on the OS."""
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def round_half_up(value: float, places: int = 0) -> Decimal:
    """Round the way people do on paper (1072.5 -> 1073), not to the nearest even digit."""
    exponent = Decimal(1).scaleb(-places)
    return Decimal(repr(float(value))).quantize(exponent, rounding=ROUND_HALF_UP)


def money(value: Optional[float], cents: bool = False) -> str:
    """Format dollars as $1,234 (or $1,234.56); None becomes a dash."""
    if value is None:
        return MISSING
    places = 2 if cents else 0
    rounded = round_half_up(abs(value), places)
    sign = "-" if value < 0 and rounded != 0 else ""
    return f"{sign}${rounded:,.{places}f}"


def number(value: Optional[float], decimals: int = 0) -> str:
    if value is None:
        return MISSING
    return f"{value:,.{decimals}f}"


def percent(value: Optional[float], decimals: int = 1) -> str:
    """Format a number that is already a percentage (12.5 -> '12.5%')."""
    if value is None:
        return MISSING
    return f"{value:.{decimals}f}%"


def text_or_dash(value: object) -> str:
    return MISSING if value in (None, "") else str(value)


def long_date(value: Optional[dt.date]) -> str:
    """May 17, 2027 (no zero-padded day, independent of platform strftime)."""
    if value is None:
        return MISSING
    return f"{value:%B} {value.day}, {value.year}"


def short_date(value: Optional[dt.date]) -> str:
    """Sep 18, 2026."""
    if value is None:
        return MISSING
    return f"{value:%b} {value.day}, {value.year}"


def comp_when(price_type: str, day: Optional[dt.date]) -> str:
    """Date text for a comp that cannot be mistaken for a sale date on a listing or an estimate."""
    if price_type == "sale":
        return short_date(day) if day else "Sale (date not given)"
    label = price_type.capitalize()
    if day is None:
        return label
    return f"{label}, {'listed' if price_type == 'listing' else 'as of'} {short_date(day)}"


def weekday_date(value: dt.date) -> str:
    """Mon, May 17, 2027."""
    return f"{value:%a}, {long_date(value)}"


ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def strict_date(value: Any) -> dt.date:
    """YYYY-MM-DD only. date.fromisoformat also takes '20270415' and week dates on newer Pythons."""
    if not isinstance(value, str) or not ISO_DATE.match(value):
        raise ValueError(f"not a date written YYYY-MM-DD: {value!r}")
    return dt.date.fromisoformat(value)


def parse_date(value: Optional[str]) -> Optional[dt.date]:
    return strict_date(value) if value else None


def read_json(path: Path) -> Any:
    """Read a UTF-8 (BOM allowed) JSON file; NaN and Infinity are rejected. Raises ValueError with a plain message."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        raise ValueError(f"{path}: file not found")
    except OSError as exc:
        raise ValueError(f"{path}: cannot be read ({exc.strerror or exc})")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: not UTF-8 text (byte {exc.start}); save the file as UTF-8")
    try:
        return json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno}, column {exc.colno})")


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not a valid number in a case file")


def local_address(address: str, reference: str) -> str:
    """Drop the city/state/zip tail when it matches the reference address (keeps tables narrow)."""
    _, _, tail = reference.partition(",")
    tail = tail.strip()
    if tail and address.endswith(tail):
        return address[: -len(tail)].rstrip().rstrip(",")
    return address


def beds_baths(beds: Optional[float], baths: Optional[float]) -> str:
    if beds is None and baths is None:
        return MISSING
    return f"{_trim(beds)} / {_trim(baths)}"


def _trim(value: Optional[float]) -> str:
    if value is None:
        return MISSING
    return f"{value:g}"
