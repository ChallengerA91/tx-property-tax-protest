#!/usr/bin/env python3
"""Compute protest-season deadlines from the notice date, and export them as .ics.

Deadlines come from a rules file (default: deadline_rules.json beside this script).
No law lives in this code: dates, day counts, holidays and citations are all rule data.

The rules file is an object: {"holidays": [...], "rules": [...]}.

Rule fields: id, event, type, params, statute, note, and optional
  core          true (default) shows the rule in the evidence package; false keeps it as a reference date
  weekend_roll  true moves a Saturday, Sunday or listed holiday forward to the next business day
  safe_day      true moves it back to the previous business day (act by the earlier day)

Rule types (specs nest inside later_of and earlier_of)
  fixed_date          params {month, day, year_offset=0}; the year is tax_year + year_offset
  days_after_input    params {input, days}; input is notice_date, hearing_date, arb_order_date,
                      acquisition_date (date the home was bought) or qualified_date (turned 65 or became disabled)
  years_after_input   params {input, years, days=0}; Feb 29 falls back to Feb 28
  days_after_notice   params {days}; same as days_after_input with notice_date
  days_after_event    params {event: <rule id>, days}; counted from that event's final date
  years_after_event   params {event: <rule id>, years}
  later_of            params {options: [<spec>, ...]}
  earlier_of          params {options: [<spec>, ...]}
A rule that needs an input that was not supplied is skipped, and so is any rule counted from a
skipped rule. Rules may not refer to each other in a loop (checked when the file is loaded).

Holidays are recomputed for every year. Each entry is an ISO date string or an object with a name and
  {"type": "fixed", "date": "YYYY-MM-DD"}                         one specific date
  {"type": "annual", "month": 7, "day": 4}                        the same date every year
  {"type": "nth_weekday", "month": 1, "weekday": "monday", "n": 3}   n = -1 for the last one
  {"type": "after", "holiday": "<name>", "days": 1}               a day offset from another holiday

Usage:
  python deadlines.py --notice-date 2027-04-01 --tax-year 2027 [--hearing-date D] [--arb-order-date D]
                      [--all] [--ics out.ics] [--json]
"""
from __future__ import annotations

import argparse
import calendar
import datetime as dt
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from fmt import strict_date, use_utf8_output, weekday_date

DEFAULT_RULES = Path(__file__).with_name("deadline_rules.json")
DEFAULT_REMINDER_DAYS: Tuple[int, ...] = (14, 3)
UID_NAMESPACE = uuid.UUID("5d0c9c1e-6a53-4f0e-9d3a-7e2f5a1b8c44")
UID_DOMAIN = "tx-property-tax-protest"
INPUT_NAMES = ("notice_date", "hearing_date", "arb_order_date", "acquisition_date", "qualified_date")
SPEC_TYPES = ("fixed_date", "days_after_input", "years_after_input", "days_after_notice", "days_after_event",
              "years_after_event", "later_of", "earlier_of")
WEEKDAYS = tuple(name.lower() for name in calendar.day_name)
PORTAL_WARNING = ("Some county portals close on the original date; file by the last business day before it "
                  "to be safe")


class RuleError(ValueError):
    """The rules file is malformed or a rule cannot be evaluated."""


class _Skip(Exception):
    """A rule needs inputs that have not been supplied."""

    def __init__(self, missing: Iterable[str]):
        super().__init__()
        self.missing = tuple(sorted(set(missing)))


# --- holidays ---------------------------------------------------------------

@dataclass(frozen=True)
class Holiday:
    name: str
    kind: str                           # fixed | annual | nth_weekday | after
    date: Optional[dt.date] = None      # fixed
    month: int = 0                      # annual, nth_weekday
    day: int = 0                        # annual
    weekday: int = 0                    # nth_weekday
    n: int = 0                          # nth_weekday
    base: Optional["Holiday"] = None    # after
    offset: int = 0                     # after

    def date_in(self, year: int) -> Optional[dt.date]:
        """The date this holiday falls on in `year` (None when it has none, such as Feb 29)."""
        if self.kind == "fixed":
            return self.date if self.date and self.date.year == year else None
        if self.kind == "annual":
            try:
                return dt.date(year, self.month, self.day)
            except ValueError:
                return None
        if self.kind == "nth_weekday":
            return self._nth_weekday(year)
        base = self.base.date_in(year) if self.base else None
        return base + dt.timedelta(days=self.offset) if base else None

    def falls_on(self, day: dt.date) -> bool:
        return self.date_in(day.year) == day

    def _nth_weekday(self, year: int) -> dt.date:
        if self.n == -1:
            last = dt.date(year, self.month, calendar.monthrange(year, self.month)[1])
            return last - dt.timedelta(days=(last.weekday() - self.weekday) % 7)
        first = dt.date(year, self.month, 1)
        return first + dt.timedelta(days=(self.weekday - first.weekday()) % 7 + 7 * (self.n - 1))


def _parse_holidays(items: Any) -> Tuple[Holiday, ...]:
    if not isinstance(items, list):
        raise RuleError("holidays: must be a list")
    by_name: Dict[str, Holiday] = {}
    ordered: List[Holiday] = []
    for item in (i for i in items if not _is_after(i)):
        holiday = _parse_holiday(item)
        by_name[holiday.name] = holiday
        ordered.append(holiday)
    for item in (i for i in items if _is_after(i)):
        base = by_name.get(item.get("holiday"))
        if base is None or not isinstance(item.get("days"), int) or isinstance(item.get("days"), bool):
            raise RuleError(f"holidays: {item.get('name')}: needs an existing holiday name and a whole number of days")
        holiday = Holiday(_holiday_name(item), "after", base=base, offset=item["days"])
        by_name[holiday.name] = holiday
        ordered.append(holiday)
    return tuple(ordered)


def _is_after(item: Any) -> bool:
    return isinstance(item, dict) and item.get("type") == "after"


def _holiday_name(item: Dict[str, Any]) -> str:
    if not isinstance(item.get("name"), str) or not item["name"].strip():
        raise RuleError(f"holidays: each entry needs a date string or an object with a name (got {item!r})")
    return item["name"]


def _parse_holiday(item: Any) -> Holiday:
    if isinstance(item, str):
        try:
            return Holiday("Holiday", "fixed", date=strict_date(item))
        except ValueError:
            raise RuleError(f"holidays: {item!r} is not a YYYY-MM-DD date")
    if not isinstance(item, dict):
        raise RuleError(f"holidays: each entry needs a date string or an object with a name (got {item!r})")
    name, kind = _holiday_name(item), item.get("type")
    if kind == "fixed":
        try:
            return Holiday(name, "fixed", date=strict_date(item.get("date")))
        except ValueError:
            raise RuleError(f"holidays: {name}: date must be YYYY-MM-DD")
    if kind == "annual":
        month, day = item.get("month"), item.get("day")
        try:
            dt.date(2000, month, day)
        except (TypeError, ValueError):
            raise RuleError(f"holidays: {name}: needs a real month and day")
        return Holiday(name, "annual", month=month, day=day)
    if kind == "nth_weekday":
        weekday = str(item.get("weekday", "")).lower()
        month, n = item.get("month"), item.get("n")
        if weekday not in WEEKDAYS or not isinstance(month, int) or not 1 <= month <= 12 \
                or n not in (-1, 1, 2, 3, 4):
            raise RuleError(f"holidays: {name}: needs month 1-12, a weekday name and n of -1, 1, 2, 3 or 4")
        return Holiday(name, "nth_weekday", month=month, weekday=WEEKDAYS.index(weekday), n=n)
    raise RuleError(f"holidays: {name}: type must be fixed, annual, nth_weekday or after")


# --- results ----------------------------------------------------------------

@dataclass(frozen=True)
class Deadline:
    id: str
    event: str
    date: dt.date                  # date to plan around, after any roll
    computed_date: dt.date         # statutory date before rolling
    statute: str
    note: str
    roll: str = ""                 # "forward" (next business day is timely), "back" (act earlier) or ""
    roll_reasons: Tuple[str, ...] = ()
    core: bool = True
    safe_date: Optional[dt.date] = None   # forward rolls: the last business day before the statutory date

    @property
    def rolled(self) -> bool:
        return self.date != self.computed_date

    @property
    def roll_text(self) -> str:
        """Why the planning date differs from the statutory date (empty when it does not)."""
        if not self.rolled:
            return ""
        why = f"Statutory date: {weekday_date(self.computed_date)} ({', '.join(self.roll_reasons)}). "
        if self.roll == "forward":
            return why + f"It moves to the next business day, {weekday_date(self.date)}."
        return why + f"Act by the previous business day, {weekday_date(self.date)}, to be safe."

    @property
    def portal_text(self) -> str:
        """Forward rolls only: the day to file by if the county portal closes on the statutory date."""
        if self.roll != "forward" or not self.safe_date:
            return ""
        return f"{PORTAL_WARNING}: {weekday_date(self.safe_date)}."

    @property
    def full_note(self) -> str:
        return " ".join(part for part in (self.note, self.roll_text, self.portal_text) if part)


@dataclass(frozen=True)
class Skipped:
    id: str
    event: str
    missing: Tuple[str, ...]       # the inputs that were not supplied
    core: bool


@dataclass(frozen=True)
class RuleSet:
    rules: Tuple[Dict[str, Any], ...]
    holidays: Tuple[Holiday, ...]

    def closed_reason(self, day: dt.date) -> Optional[str]:
        """Why a filing cannot be made on this day (weekend or listed holiday), else None."""
        if day.weekday() >= 5:
            return calendar.day_name[day.weekday()]
        for holiday in self.holidays:
            if holiday.falls_on(day):
                return holiday.name
        return None


# --- loading and validating rules -------------------------------------------

def load_rules(path: Path = DEFAULT_RULES) -> RuleSet:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuleError(f"rules file not found: {path}")
    except json.JSONDecodeError as exc:
        raise RuleError(f"{path}: not valid JSON ({exc.msg} at line {exc.lineno})")
    return parse_rules(data)


def parse_rules(data: Any) -> RuleSet:
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        raise RuleError('rules file must be an object with a "rules" list')
    holidays = _parse_holidays(data.get("holidays", []))
    rules = tuple(data["rules"])
    ids: Set[str] = set()
    for index, rule in enumerate(rules):
        _validate_rule(rule, f"rules[{index}]", ids)
    for rule in rules:
        _check_event_refs(rule, rule, ids)
    _check_no_cycles(rules)
    return RuleSet(rules, holidays)


def _validate_rule(rule: Any, where: str, ids: Set[str]) -> None:
    if not isinstance(rule, dict):
        raise RuleError(f"{where}: must be an object")
    for key in ("id", "event"):
        if not isinstance(rule.get(key), str) or not rule[key].strip():
            raise RuleError(f"{where}.{key}: required non-empty string")
    if rule["id"] in ids:
        raise RuleError(f"{where}.id: duplicate id '{rule['id']}'")
    ids.add(rule["id"])
    for key in ("statute", "note"):
        if not isinstance(rule.get(key, ""), str):
            raise RuleError(f"{where}.{key}: must be a string")
    for key in ("weekend_roll", "safe_day", "core"):
        if not isinstance(rule.get(key, False), bool):
            raise RuleError(f"{where}.{key}: must be true or false")
    if rule.get("weekend_roll") and rule.get("safe_day"):
        raise RuleError(f"{where}: weekend_roll and safe_day cannot both be true")
    _validate_spec(rule, where)


def _validate_spec(spec: Any, where: str) -> None:
    if not isinstance(spec, dict) or spec.get("type") not in SPEC_TYPES:
        raise RuleError(f"{where}.type: must be one of {', '.join(SPEC_TYPES)}")
    params = spec.get("params")
    if not isinstance(params, dict):
        raise RuleError(f"{where}.params: required object")
    kind = spec["type"]
    if kind == "fixed_date":
        _require_int(params, "month", where, 1, 12)
        _require_int(params, "day", where, 1, 31)
        _require_int(params, "year_offset", where, required=False)
    elif kind in ("days_after_notice", "days_after_input", "days_after_event"):
        _require_int(params, "days", where)
        _check_reference(kind, params, where)
    elif kind in ("years_after_event", "years_after_input"):
        _require_int(params, "years", where)
        _require_int(params, "days", where, required=False)
        _check_reference(kind, params, where)
    else:
        options = params.get("options")
        if not isinstance(options, list) or len(options) < 2:
            raise RuleError(f"{where}.params.options: needs at least two specs")
        for index, option in enumerate(options):
            _validate_spec(option, f"{where}.params.options[{index}]")


def _check_reference(kind: str, params: Dict[str, Any], where: str) -> None:
    if kind in ("days_after_input", "years_after_input") and params.get("input") not in INPUT_NAMES:
        raise RuleError(f"{where}.params.input: must be one of {', '.join(INPUT_NAMES)}")
    if kind in ("days_after_event", "years_after_event") and not isinstance(params.get("event"), str):
        raise RuleError(f"{where}.params.event: required rule id")


def _require_int(params: Dict[str, Any], key: str, where: str,
                 low: Optional[int] = None, high: Optional[int] = None, required: bool = True) -> None:
    if key not in params:
        if required:
            raise RuleError(f"{where}.params.{key}: required whole number")
        return
    value = params[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuleError(f"{where}.params.{key}: must be a whole number")
    if (low is not None and value < low) or (high is not None and value > high):
        raise RuleError(f"{where}.params.{key}: must be between {low} and {high}")


def _event_refs(spec: Dict[str, Any]) -> List[str]:
    """Rule ids a spec is counted from, including nested specs."""
    params = spec["params"]
    refs = [params["event"]] if spec["type"] in ("days_after_event", "years_after_event") else []
    for option in params.get("options", []):
        refs += _event_refs(option)
    return refs


def _check_event_refs(rule: Dict[str, Any], spec: Dict[str, Any], ids: Set[str]) -> None:
    for ref in _event_refs(spec):
        if ref not in ids:
            raise RuleError(f"rule '{rule['id']}': refers to unknown rule id '{ref}'")


def _check_no_cycles(rules: Sequence[Dict[str, Any]]) -> None:
    """Fail at load time when rules are counted from each other in a loop (or from themselves)."""
    graph = {rule["id"]: _event_refs(rule) for rule in rules}
    state: Dict[str, int] = {}          # 1 = on the current path, 2 = finished

    def visit(rule_id: str, path: List[str]) -> None:
        if state.get(rule_id) == 2:
            return
        if state.get(rule_id) == 1:
            raise RuleError(f"circular rule reference: {' -> '.join(path[path.index(rule_id):] + [rule_id])}")
        state[rule_id] = 1
        for ref in graph[rule_id]:
            visit(ref, path + [rule_id])
        state[rule_id] = 2

    for rule_id in graph:
        visit(rule_id, [])


# --- evaluation -------------------------------------------------------------

def _add_years(day: dt.date, years: int) -> dt.date:
    """Same month and day, `years` later; Feb 29 falls back to Feb 28 (the earlier, safer date)."""
    try:
        return day.replace(year=day.year + years)
    except ValueError:
        return day.replace(year=day.year + years, day=28)


class _Resolver:
    def __init__(self, ruleset: RuleSet, tax_year: int, inputs: Mapping[str, dt.date]):
        self.ruleset = ruleset
        self.tax_year = tax_year
        self.inputs = inputs
        self.by_id = {rule["id"]: rule for rule in ruleset.rules}
        self.done: Dict[str, Optional[Deadline]] = {}
        self.missing: Dict[str, Tuple[str, ...]] = {}
        self.active: List[str] = []

    def deadline(self, rule_id: str) -> Optional[Deadline]:
        """The rule's result, or None when it is skipped for a missing input."""
        if rule_id in self.done:
            return self.done[rule_id]
        if rule_id in self.active:
            raise RuleError(f"circular rule reference: {' -> '.join(self.active + [rule_id])}")
        self.active.append(rule_id)
        try:
            self.done[rule_id] = self._resolve(self.by_id[rule_id])
        finally:
            self.active.pop()
        return self.done[rule_id]

    def _resolve(self, rule: Dict[str, Any]) -> Optional[Deadline]:
        try:
            computed = self.evaluate(rule)
        except _Skip as skip:
            self.missing[rule["id"]] = skip.missing
            return None
        final, kind, reasons, safe = self._roll(rule, computed)
        return Deadline(rule["id"], rule["event"], final, computed, rule.get("statute", ""),
                        rule.get("note", ""), kind, reasons, rule.get("core", True), safe)

    def evaluate(self, spec: Dict[str, Any]) -> dt.date:
        kind, params = spec["type"], spec["params"]
        if kind == "fixed_date":
            return self._fixed_date(params)
        if kind in ("days_after_notice", "days_after_input", "years_after_input"):
            name = "notice_date" if kind == "days_after_notice" else params["input"]
            if name not in self.inputs:
                raise _Skip([name])
            if kind == "years_after_input":
                return _add_years(self.inputs[name], params["years"]) + dt.timedelta(days=params.get("days", 0))
            return self.inputs[name] + dt.timedelta(days=params["days"])
        if kind in ("days_after_event", "years_after_event"):
            reference = self.deadline(params["event"])
            if reference is None:
                raise _Skip(self.missing[params["event"]])
            if kind == "years_after_event":
                return _add_years(reference.date, params["years"])
            return reference.date + dt.timedelta(days=params["days"])
        dates = [self.evaluate(option) for option in params["options"]]
        return max(dates) if kind == "later_of" else min(dates)

    def _fixed_date(self, params: Dict[str, Any]) -> dt.date:
        year = self.tax_year + params.get("year_offset", 0)
        try:
            return dt.date(year, params["month"], params["day"])
        except ValueError:
            raise RuleError(f"fixed_date {params['month']}/{params['day']} does not exist in {year}")

    def _roll(self, rule: Dict[str, Any], computed: dt.date
              ) -> Tuple[dt.date, str, Tuple[str, ...], Optional[dt.date]]:
        if rule.get("weekend_roll"):
            step, kind = 1, "forward"
        elif rule.get("safe_day"):
            step, kind = -1, "back"
        else:
            return computed, "", (), None
        day, reasons = computed, []
        while True:
            reason = self.ruleset.closed_reason(day)
            if reason is None:
                break
            if not reasons or day.weekday() < 5:  # name the first closed day, then only holidays
                reasons.append(reason)
            day += dt.timedelta(days=step)
        if not reasons:
            return day, "", (), None
        return day, kind, tuple(reasons), (self._last_open_day_before(computed) if kind == "forward" else None)

    def _last_open_day_before(self, day: dt.date) -> dt.date:
        day -= dt.timedelta(days=1)
        while self.ruleset.closed_reason(day):
            day -= dt.timedelta(days=1)
        return day


def compute_report(ruleset: RuleSet, notice_date: Optional[dt.date], tax_year: int,
                   inputs: Optional[Mapping[str, Optional[dt.date]]] = None,
                   include_reference: bool = True) -> Tuple[List[Deadline], List[Skipped]]:
    """Evaluate every rule; returns (deadlines sorted by planning date, rules skipped for missing inputs).

    `inputs` may hold hearing_date and arb_order_date; notice_date may be None when the rules asked
    for only need the others. With include_reference=False only rules marked core are returned.
    """
    given = {"notice_date": notice_date, **(inputs or {})}
    known = {name: value for name, value in given.items() if value is not None}
    unknown = sorted(set(known) - set(INPUT_NAMES))
    if unknown:
        raise RuleError(f"unknown input(s): {', '.join(unknown)}")
    resolver = _Resolver(ruleset, tax_year, known)
    results = [resolver.deadline(rule["id"]) for rule in ruleset.rules]
    kept = sorted((d for d in results if d is not None and (include_reference or d.core)), key=lambda d: d.date)
    skipped = [Skipped(rule["id"], rule["event"], resolver.missing[rule["id"]], rule.get("core", True))
               for rule, result in zip(ruleset.rules, results)
               if result is None and (include_reference or rule.get("core", True))]
    return kept, skipped


def compute_deadlines(ruleset: RuleSet, notice_date: Optional[dt.date], tax_year: int,
                      inputs: Optional[Mapping[str, Optional[dt.date]]] = None,
                      include_reference: bool = True) -> List[Deadline]:
    """The deadlines only (see compute_report for the rules that were skipped)."""
    return compute_report(ruleset, notice_date, tax_year, inputs, include_reference)[0]


# --- iCalendar --------------------------------------------------------------

def event_id(text: str) -> str:
    """Stable identifier for an event name (used for iCalendar UIDs)."""
    return "-".join("".join(ch.lower() if ch.isalnum() else " " for ch in text).split())


def _escape(value: str) -> str:
    """RFC 5545 TEXT: escape the separators, turn every line break into \\n, drop other control characters."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = "".join(ch for ch in value if ch == "\n" or ord(ch) >= 32 and ord(ch) != 127)
    return cleaned.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """Fold to at most 75 octets per physical line (RFC 5545 3.1), never splitting a character."""
    if len(line.encode("utf-8")) <= 75:
        return line
    parts: List[str] = []
    current = ""
    limit = 75
    for char in line:
        if len((current + char).encode("utf-8")) > limit:
            parts.append(current)
            current, limit = char, 74  # continuation lines start with one space
        else:
            current += char
    parts.append(current)
    return "\r\n ".join(parts)


def _description(deadline: Deadline) -> str:
    pieces = [deadline.full_note] if deadline.full_note else []
    if deadline.statute:
        pieces.append(f"Basis: {deadline.statute}")
    return " ".join(pieces)


def _uid(tax_year: int, deadline_id: str, seen: Dict[str, int]) -> str:
    """Stable per event; a repeated id gets an occurrence number so two events never share a UID."""
    seed = f"{tax_year}:{deadline_id}"
    seen[seed] = seen.get(seed, 0) + 1
    if seen[seed] > 1:
        seed += f":{seen[seed]}"
    return f"{uuid.uuid5(UID_NAMESPACE, seed)}@{UID_DOMAIN}"


def _event_lines(deadline: Deadline, uid: str, stamp: str, reminder_days: Sequence[int]) -> List[str]:
    end = deadline.date + dt.timedelta(days=1)  # DTEND is exclusive for all-day events
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{deadline.date:%Y%m%d}",
        f"DTEND;VALUE=DATE:{end:%Y%m%d}",
        f"SUMMARY:{_escape(deadline.event)}",
        "TRANSP:TRANSPARENT",
    ]
    description = _description(deadline)
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    for days in reminder_days:
        lines += [
            "BEGIN:VALARM",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_escape(f'{deadline.event} is in {days} days')}",
            f"TRIGGER:-P{days}D",
            "END:VALARM",
        ]
    lines.append("END:VEVENT")
    return lines


def build_ics(deadlines: Iterable[Deadline], tax_year: int, dtstamp: dt.datetime,
              reminder_days: Sequence[int] = DEFAULT_REMINDER_DAYS) -> str:
    """Return an RFC 5545 calendar (CRLF line endings) with one all-day event per deadline.

    A naive `dtstamp` is taken to be UTC.
    """
    if dtstamp.tzinfo is None:
        dtstamp = dtstamp.replace(tzinfo=dt.timezone.utc)
    stamp = dtstamp.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//tx-property-tax-protest//deadlines//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(f'Texas property tax protest {tax_year}')}",
    ]
    seen: Dict[str, int] = {}
    for deadline in deadlines:
        lines += _event_lines(deadline, _uid(tax_year, deadline.id, seen), stamp, reminder_days)
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def write_ics(path: Path, content: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)


# --- command line -----------------------------------------------------------

def _skipped_lines(skipped: Sequence[Skipped]) -> List[str]:
    by_input: Dict[Tuple[str, ...], List[str]] = {}
    for item in skipped:
        by_input.setdefault(item.missing, []).append(item.event)
    return [f"Skipped, needs {' and '.join('--' + name.replace('_', '-') for name in missing)}: "
            f"{'; '.join(events)}" for missing, events in by_input.items()]


def _format_text(deadlines: Sequence[Deadline], notice_date: Optional[dt.date], tax_year: int,
                 hidden: int, skipped: Sequence[Skipped]) -> str:
    given = notice_date.isoformat() if notice_date else "not given"
    out = [f"Deadlines for tax year {tax_year} (notice date {given})", ""]
    for deadline in deadlines:
        out.append(f"{deadline.date:%a %Y-%m-%d}  {deadline.event}")
        if deadline.statute:
            out.append(f"    Basis: {deadline.statute}")
        if deadline.note:
            out.append(f"    Note:  {deadline.note}")
        if deadline.roll_text:
            out.append(f"    Roll:  {deadline.roll_text}")
        if deadline.portal_text:
            out.append(f"    Safe:  {deadline.portal_text}")
    if skipped:
        out += [""] + _skipped_lines(skipped)
    if hidden:
        out += ["", f"{hidden} more reference date(s) not shown; add --all to list them."]
    return "\n".join(out)


def deadlines_as_json(deadlines: Sequence[Deadline]) -> List[Dict[str, str]]:
    """Shape used by the `deadlines` list in case.json (the note includes any roll explanation)."""
    items = []
    for deadline in deadlines:
        item = {"event": deadline.event, "date": deadline.date.isoformat()}
        if deadline.statute:
            item["statute"] = deadline.statute
        if deadline.full_note:
            item["note"] = deadline.full_note
        items.append(item)
    return items


def _date_arg(text: str) -> dt.date:
    try:
        return strict_date(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute protest deadlines from the notice date.")
    parser.add_argument("--notice-date", type=_date_arg,
                        help="date printed on the appraisal notice, which is its mailing date (YYYY-MM-DD); "
                             "optional when you only need dates counted from --hearing-date or --arb-order-date")
    parser.add_argument("--tax-year", type=int,
                        help="the tax year; defaults to the year of --notice-date, --hearing-date or --arb-order-date")
    parser.add_argument("--hearing-date", type=_date_arg,
                        help="ARB hearing date; adds the dates counted back from the hearing")
    parser.add_argument("--arb-order-date", type=_date_arg,
                        help="date the ARB order was received; adds the appeal windows")
    parser.add_argument("--acquisition-date", type=_date_arg,
                        help="date you bought the home; adds the new-buyer homestead exemption date")
    parser.add_argument("--qualified-date", type=_date_arg,
                        help="date you turned 65 or became disabled; adds the 65+/disabled exemption date")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--all", action="store_true", dest="include_reference",
                        help="also list reference dates (late-filing limits, prepayment, rarely used windows)")
    parser.add_argument("--ics", type=Path, help="also write an .ics calendar file here")
    parser.add_argument("--json", action="store_true",
                        help="print the deadlines as JSON (the `deadlines` list used in case.json)")
    parser.add_argument("--dtstamp", type=dt.datetime.fromisoformat,
                        help="DTSTAMP for the .ics, ISO 8601; no time zone means UTC (default: now, UTC)")
    args = parser.parse_args(argv)
    dated = args.notice_date or args.hearing_date or args.arb_order_date
    if not dated and args.tax_year is None:
        parser.error("give --tax-year, or at least one of --notice-date, --hearing-date or --arb-order-date")
    if args.tax_year is None:
        args.tax_year = dated.year
    if args.notice_date and args.notice_date.year != args.tax_year:
        parser.error(f"--tax-year {args.tax_year} does not match the year of --notice-date "
                     f"{args.notice_date.isoformat()}; the notice for tax year {args.tax_year} is dated in {args.tax_year}")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    use_utf8_output()
    args = _parse_args(argv)
    inputs = {"hearing_date": args.hearing_date, "arb_order_date": args.arb_order_date,
              "acquisition_date": args.acquisition_date, "qualified_date": args.qualified_date}
    try:
        ruleset = load_rules(args.rules)
        everything, skipped = compute_report(ruleset, args.notice_date, args.tax_year, inputs,
                                             include_reference=args.include_reference)
        hidden = 0 if args.include_reference else len(
            compute_deadlines(ruleset, args.notice_date, args.tax_year, inputs)) - len(everything)
    except RuleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(deadlines_as_json(everything), indent=2, ensure_ascii=False))
        for line in _skipped_lines(skipped):
            print(line, file=sys.stderr)
    else:
        print(_format_text(everything, args.notice_date, args.tax_year, hidden, skipped))
    if args.ics:
        stamp = args.dtstamp or dt.datetime.now(dt.timezone.utc)
        write_ics(args.ics, build_ics(everything, args.tax_year, stamp))
        print(f"\nWrote {args.ics}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
