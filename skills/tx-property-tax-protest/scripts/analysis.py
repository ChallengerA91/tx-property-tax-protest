"""Deterministic numbers behind every output: comps, unequal appraisal, income, savings.

``build_analysis`` turns a validated case dict into an ``Analysis`` that the
renderers read; no renderer does its own arithmetic.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence

import deadlines as deadline_engine
from deadlines import Deadline
from fmt import parse_date
from savings import SavingsEstimate, estimate_savings

# Used for file metadata and the .ics DTSTAMP when the case has no prepared_on. 1980-01-01 is the ZIP/DOS
# epoch: it is clearly a placeholder, not a real build date, and keeps rebuilds byte-identical.
FALLBACK_DATE = dt.date(1980, 1, 1)

DEFAULT_DISCLAIMER = (
    "This package is general information built from the data you supplied. It is not legal, tax, "
    "or appraisal advice and does not guarantee any reduction. Check every figure and deadline "
    "with your appraisal district before relying on it."
)


# --- statistics -------------------------------------------------------------

def present(values: Iterable[Optional[float]]) -> List[float]:
    """Drop missing (None) and non-numeric values."""
    return [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]


def median(values: Iterable[Optional[float]]) -> Optional[float]:
    ordered = sorted(present(values))
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    kept = present(values)
    return sum(kept) / len(kept) if kept else None


def per_sqft(value: Optional[float], sqft: Optional[float]) -> Optional[float]:
    if value is None or not sqft:
        return None
    return value / sqft


# --- result types -----------------------------------------------------------

@dataclass(frozen=True)
class Adjustment:
    label: str
    amount: float


@dataclass(frozen=True)
class CompRow:
    address: str
    price: float
    price_type: str
    sale_date: Optional[dt.date]
    sqft: Optional[float]
    year_built: Optional[int]
    beds: Optional[float]
    baths: Optional[float]
    lot_sqft: Optional[float]
    distance_mi: Optional[float]
    source: Optional[str]
    notes: Optional[str]
    adjustments: List[Adjustment]
    adjustment_total: float
    adjusted_value: float
    price_ppsf: Optional[float]
    adjusted_ppsf: Optional[float]


@dataclass(frozen=True)
class NeighborRow:
    address: str
    appraised_value: float
    sqft: float
    year_built: Optional[int]
    ppsf: float


@dataclass(frozen=True)
class UnequalAnalysis:
    neighbors: List[NeighborRow]          # sorted by $/sqft, highest first
    subject_ppsf: float
    median_ppsf: float
    mean_ppsf: float
    low_ppsf: float
    high_ppsf: float
    rank: int                             # 1 = highest $/sqft among subject + neighbors
    group_size: int                       # neighbors + subject
    percentile: float                     # share of neighbors at or below the subject, ties count half
    indicated_value: float                # median neighbor $/sqft x subject sqft


@dataclass(frozen=True)
class RankedRow:
    """One line of the neighbor ranking table; equal $/sq ft values share a rank."""
    rank: int
    address: str
    appraised_value: float
    sqft: float
    ppsf: float
    year_built: Optional[int]
    is_subject: bool


@dataclass(frozen=True)
class IncomeAnalysis:
    gross_rent: float
    vacancy_pct: float
    vacancy_loss: float
    effective_gross_income: float
    expenses: List[Adjustment]
    total_expenses: float
    noi: float
    cap_rate_pct: float
    cap_rate_source: str
    rent_source: Optional[str]
    indicated_value: float
    circuit_breaker_note: Optional[str]


@dataclass
class Analysis:
    case: Mapping[str, Any]
    path: str
    strategy: str
    market_value: float        # CAD market value on the notice (equals appraised_value when no cap applies)
    market_ppsf: float
    appraised_value: float     # taxable appraised value on the notice (capped for some homesteads)
    argued_value: float
    argued_ppsf: float
    reduction: float           # market_value - argued_value: what the protest asks for
    reduction_pct: float       # of market_value
    comps: List[CompRow]       # every comp in the case, sales first as given
    median_adjusted: Optional[float]       # medians and averages use sale comps only
    mean_adjusted: Optional[float]
    median_price_ppsf: Optional[float]
    median_adjusted_ppsf: Optional[float]
    unequal: Optional[UnequalAnalysis]
    income: Optional[IncomeAnalysis]
    savings: SavingsEstimate
    deadlines: List[Deadline] = field(default_factory=list)
    disclaimer: str = DEFAULT_DISCLAIMER
    prepared_on: Optional[dt.date] = None

    @property
    def capped(self) -> bool:
        """True when the taxable appraised value is held below the market value (homestead cap)."""
        return self.appraised_value < self.market_value

    def ranked_neighbors(self) -> List[RankedRow]:
        """Neighbors and the subject in one table, highest $/sq ft first, ranked the way `unequal.rank` is."""
        u = self.unequal
        if u is None:
            return []
        subject = self.case["subject"]
        entries = [(n.address, n.appraised_value, n.sqft, n.ppsf, n.year_built, False) for n in u.neighbors]
        entries.append((f"{subject['address']} (SUBJECT)", self.market_value, subject["sqft"], u.subject_ppsf,
                        subject.get("year_built"), True))
        entries.sort(key=lambda e: (-e[3], e[5], e[0]))
        return [RankedRow(1 + sum(1 for other in entries if other[3] > e[3]), *e) for e in entries]

    @property
    def sale_comps(self) -> List[CompRow]:
        """Closed sales: the only comps that enter the median and average."""
        return [c for c in self.comps if c.price_type == "sale"]

    @property
    def other_comps(self) -> List[CompRow]:
        """Listings and estimates: supporting data points, not used in the median."""
        return [c for c in self.comps if c.price_type != "sale"]

    @property
    def income_supports_reduction(self) -> bool:
        """The letter cites the income approach only when it indicates less than the CAD value."""
        return self.income is not None and self.income.indicated_value < self.market_value

    @property
    def value_term(self) -> str:
        """What the protest is about: the 'market value' when a cap applies, else the 'appraised value'."""
        return "market value" if self.capped else "appraised value"

    @property
    def timestamp(self) -> dt.datetime:
        """Fixed stamp for file metadata so repeated builds are byte-identical."""
        return dt.datetime.combine(self.prepared_on or FALLBACK_DATE, dt.time.min)


# --- builders ---------------------------------------------------------------

def build_comp_rows(comps: Sequence[Mapping[str, Any]]) -> List[CompRow]:
    return [_comp_row(comp) for comp in comps]


def _comp_row(comp: Mapping[str, Any]) -> CompRow:
    adjustments = [Adjustment(a["label"], a["amount"]) for a in comp.get("adjustments", [])]
    total = sum(a.amount for a in adjustments)
    adjusted = comp["price"] + total
    sqft = comp.get("sqft")
    return CompRow(
        address=comp["address"], price=comp["price"], price_type=comp.get("price_type") or "sale",
        sale_date=parse_date(comp.get("sale_date")), sqft=sqft, year_built=comp.get("year_built"),
        beds=comp.get("beds"), baths=comp.get("baths"), lot_sqft=comp.get("lot_sqft"),
        distance_mi=comp.get("distance_mi"), source=comp.get("source"), notes=comp.get("notes"),
        adjustments=adjustments, adjustment_total=total, adjusted_value=adjusted,
        price_ppsf=per_sqft(comp["price"], sqft), adjusted_ppsf=per_sqft(adjusted, sqft),
    )


def build_unequal(neighbors: Sequence[Mapping[str, Any]], subject_sqft: float,
                  subject_value: float) -> Optional[UnequalAnalysis]:
    """Compare the subject's appraised $/sqft with neighbors that have a usable sqft."""
    rows = [
        NeighborRow(n["address"], n["appraised_value"], n["sqft"], n.get("year_built"),
                    n["appraised_value"] / n["sqft"])
        for n in neighbors if n.get("sqft")
    ]
    if not rows:
        return None
    rows.sort(key=lambda r: (-r.ppsf, r.address))
    subject_ppsf = subject_value / subject_sqft
    values = [r.ppsf for r in rows]
    higher = sum(1 for v in values if v > subject_ppsf)
    below = sum(1 for v in values if v < subject_ppsf)
    equal = len(values) - higher - below
    median_ppsf = median(values)
    return UnequalAnalysis(
        neighbors=rows, subject_ppsf=subject_ppsf, median_ppsf=median_ppsf, mean_ppsf=mean(values),
        low_ppsf=min(values), high_ppsf=max(values), rank=higher + 1, group_size=len(rows) + 1,
        percentile=100 * (below + 0.5 * equal) / len(values),
        indicated_value=median_ppsf * subject_sqft,
    )


def build_income(income: Mapping[str, Any]) -> IncomeAnalysis:
    gross = income["gross_rent"]
    vacancy_loss = gross * income["vacancy_pct"] / 100
    effective = gross - vacancy_loss
    expenses = [Adjustment(e["label"], e["amount"]) for e in income["expenses"]]
    total_expenses = sum(e.amount for e in expenses)
    noi = effective - total_expenses
    return IncomeAnalysis(
        gross_rent=gross, vacancy_pct=income["vacancy_pct"], vacancy_loss=vacancy_loss,
        effective_gross_income=effective, expenses=expenses, total_expenses=total_expenses, noi=noi,
        cap_rate_pct=income["cap_rate_pct"], cap_rate_source=income["cap_rate_source"],
        rent_source=income.get("rent_source"), indicated_value=noi / (income["cap_rate_pct"] / 100),
        circuit_breaker_note=income.get("circuit_breaker_note"),
    )


def resolve_deadlines(case: Mapping[str, Any], rules_path: Optional[Path] = None) -> List[Deadline]:
    """Use deadlines supplied in case.json; otherwise compute the core ones from notice_date.

    hearing_date and arb_order_date, when present, add the dates counted from them.
    """
    if case.get("deadlines"):
        items = _supplied_deadlines(case["deadlines"])
    else:
        ruleset = deadline_engine.load_rules(rules_path or deadline_engine.DEFAULT_RULES)
        inputs = {name: parse_date(case.get(name)) for name in ("hearing_date", "arb_order_date")}
        items = deadline_engine.compute_deadlines(
            ruleset, parse_date(case["notice_date"]), case["tax_year"], inputs, include_reference=False)
    return sorted(items, key=lambda item: item.date)


def _supplied_deadlines(entries: Sequence[Mapping[str, Any]]) -> List[Deadline]:
    """Deadlines written in case.json; ids are unique even when two event names read the same."""
    seen: dict = {}
    items = []
    for entry in entries:
        base = deadline_engine.event_id(entry["event"]) or "event"
        seen[base] = seen.get(base, 0) + 1
        deadline_id = base if seen[base] == 1 else f"{base}-{seen[base]}"
        day = parse_date(entry["date"])
        items.append(Deadline(deadline_id, entry["event"], day, day, entry.get("statute", ""),
                              entry.get("note", "")))
    return items


def build_analysis(case: Mapping[str, Any], rules_path: Optional[Path] = None) -> Analysis:
    subject = case["subject"]
    appraised, argued = subject["appraised_value"], case["argued_value"]
    market = subject.get("market_value", appraised)
    comps = build_comp_rows(case.get("comps", []))
    sales = [c for c in comps if c.price_type == "sale"]
    return Analysis(
        case=case,
        path=case["path"],
        strategy=case.get("strategy") or "market_value",
        market_value=market,
        market_ppsf=market / subject["sqft"],
        appraised_value=appraised,
        argued_value=argued,
        argued_ppsf=argued / subject["sqft"],
        reduction=market - argued,
        reduction_pct=100 * (market - argued) / market,
        comps=comps,
        median_adjusted=median(c.adjusted_value for c in sales),
        mean_adjusted=mean(c.adjusted_value for c in sales),
        median_price_ppsf=median(c.price_ppsf for c in sales),
        median_adjusted_ppsf=median(c.adjusted_ppsf for c in sales),
        unequal=build_unequal(case.get("neighbors", []), subject["sqft"], market),
        income=build_income(case["income"]) if "income" in case else None,
        savings=estimate_savings(case),
        deadlines=resolve_deadlines(case, rules_path),
        disclaimer=case.get("disclaimer_text") or DEFAULT_DISCLAIMER,
        prepared_on=parse_date(case.get("prepared_on")),
    )
