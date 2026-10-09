# case.json contract

`scripts/build_package.py` turns one `case.json` into the whole evidence package. The scripts hold no
law: every statute cite, exemption amount, tax rate, deadline text and disclaimer comes from this file.
`scripts/case_schema.py` validates the file and lists every problem at once, for example
`comps[2].price: required field is missing`.

```
python scripts/build_package.py case.json --out OUTPUT_DIR
```

Outputs: `comp_analysis.xlsx`, `protest_letter.docx`, `filing_checklist.md`, `dashboard.html`, `deadlines.ics`.
There is no clock and no network access: the same case, with the same Python and library versions, gives byte-identical files. The files are written to a staging folder first and moved into `OUTPUT_DIR` only when all five were built, so a locked or failed write never leaves a mixed package. Problems that do not block the build (for example a sale date after `prepared_on`) are printed as `warning:` lines.

## Conventions

- Money is a plain number of dollars (`465000`), never a string with `$` or commas.
- `tax_rates` are dollars of tax per $100 of value (a rate of 2.15 means $2.15 per $100).
- Fields ending in `_pct` are percent numbers: `5` means 5%, not 0.05.
- Dates are written exactly `YYYY-MM-DD` (not `20270415`). Square footage is a number.
- Numbers must be finite and no larger than 1,000,000,000,000 (`NaN` and `Infinity` are rejected); years are 1 to 9999.
- The file must be UTF-8 (a byte-order mark is fine). Text fields may not contain control characters; only tabs and line breaks are allowed.
- `null` is treated as "not provided". A key starting with `_` is ignored, so it can hold a free-form note.
- Any other unknown key is an error, and the message suggests the closest valid name.
- "Path" below says where a field applies: `both`, `homestead` or `rental`.

## Top level

| Field | Type | Required | Path | Meaning |
|---|---|---|---|---|
| `path` | `"homestead"` or `"rental"` | yes | both | Which flow this case follows. |
| `tax_year` | integer | yes | both | Year of the appraisal being protested. |
| `county` | text | yes | both | County name as you want it printed. |
| `prepared_on` | date | no | both | Printed as the letter date and "Prepared" line, and used for file metadata and the calendar stamp. Must not be earlier than `notice_date`. Leave it out for a blank date line on the letter; metadata then carries 1980-01-01, the ZIP epoch, as a neutral placeholder. |
| `cad` | object | yes | both | Appraisal district, see below. |
| `filing` | object | yes | both | County-specific filing methods and extra hearing documents. |
| `notice_date` | date | one of `notice_date` / a non-empty `deadlines` | both | Date printed on the appraisal notice, which is its mailing date. Its year must equal `tax_year`. Deadlines are computed from it with `scripts/deadline_rules.json`. |
| `hearing_date` | date | no | both | ARB hearing date, once known. Adds the dates counted back from it (evidence cutoffs, notice, requests). Ignored when `deadlines` is given. |
| `arb_order_date` | date | no | both | Date the ARB order was received. Adds the arbitration and court windows. Ignored when `deadlines` is given. |
| `deadlines` | list | one of `notice_date` / a non-empty `deadlines` | both | Explicit deadlines. When non-empty, they are used as written and nothing is computed. |
| `owner` | object | yes | both | Person signing the letter. |
| `subject` | object | yes | both | The property being protested. |
| `legal_basis` | object | yes | both | Cites printed in the letter. |
| `tax_rates` | object | yes | both | Rates used for every savings figure. |
| `exemptions` | object | no | both | Exemptions already on file and ones to claim. |
| `comps` | list | see note | both | Comparables. When the strategy includes market value at least one must have `price_type` `sale` (the median uses sales only), unless the rental case leads with an `income` block. |
| `neighbors` | list | see note | both | CAD appraisals of nearby properties. At least one with `sqft` is required when the strategy includes unequal appraisal. |
| `market_notes` | list of text | no | both | Notes for the spreadsheet and dashboard (zip median, online estimates, trends). The letter uses them as bullets only when `arguments` is absent. |
| `arguments` | list of text | no | both | Bullets for the letter (condition issues, trends, unsold listings). |
| `strategy` | `"market_value"`, `"unequal_appraisal"` or `"both"` | no (default `market_value`) | both | Which protest grounds the letter asserts. |
| `argued_value` | number | yes | both | Your opinion of value (of the market value). It is a judgment, not computed; it must be below `subject.market_value`, or below `subject.appraised_value` when no market value is given. |
| `settlement_scenarios` | object | no | both | `low_fraction` and `high_fraction` (0 to 1, low not above high). Defaults 0.5 and 1.0. |
| `income` | object | no; not allowed for `homestead` | rental | Income approach inputs. A rental needs at least one of: sale comps (strategy includes market value), neighbors with `sqft` (unequal appraisal), or `income`. |
| `disclaimer_text` | text | no | both | Footer for the spreadsheet, checklist and dashboard. A short default is used when absent. It is never put in the letter. |

### `cad`

`python scripts/county_lookup.py "Fort Bend" --case-fragment` prints ready-to-merge `cad` and `filing` blocks for the covered counties.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `name` | text | yes | Name of the appraisal district. |
| `address` | text | yes | Where the letter is addressed. Use `\n` for line breaks. |
| `phone` | text | no | Shown in the checklist. |
| `website` | text | no | Shown in the checklist. |
| `protest_addressee` | text | no | "Attn:" line and salutation. Default `Appraisal Review Board`. |

### `filing`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `methods` | list of `{method, detail?}` | yes, at least one | Ways this county accepts a protest (online, mail, in person...). |
| `hearing_documents` | list of text | no | Extra items for the "Documents for your hearing" list. |
| `notes` | list of text | no | Extra lines for the "How to file" section. |

### `deadlines[]`

`{event, date, statute?, note?}`. Run `python scripts/deadlines.py --notice-date YYYY-MM-DD --tax-year YYYY --json`
to produce a list in exactly this shape. Sorted by date in every output.

### `owner`

`name` (required), `mailing_address` (required, `\n` allowed), `phone`, `email` (optional).

### `subject`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `address` | text | yes | Full address, with city, state and zip. |
| `cad_account` | text | yes | Property ID / account number. |
| `sqft` | number > 0 | yes | Living area. |
| `appraised_value` | number > 0 | yes | The taxable appraised value on the notice: what the tax bill is based on. For a capped homestead this is the capped figure; otherwise it equals the market value. |
| `market_value` | number > 0 | no (defaults to `appraised_value`) | The CAD market value on the notice. Give it when a homestead cap holds `appraised_value` below it. Must be at least `appraised_value`. The letter and spreadsheet protest this value; the dashboard shows both. |
| `legal_description`, `subdivision` | text | no | Shown in the spreadsheet. |
| `year_built`, `beds`, `baths`, `lot_sqft` | number | no | Descriptive. `baths` may be 2.5. |
| `land_value`, `improvement_value` | number | no | CAD breakdown. |
| `value_history` | list of `{year, value}` | no | Prior-year values. |
| `purchase_price`, `purchase_date` | number, date | no | Printed in the letter and spreadsheet when given. |

### `legal_basis`

| Field | Type | Required | Meaning |
|---|---|---|---|
| `market_value_cite` | text | when strategy is `market_value` or `both` | Printed after "Market value" in the letter. |
| `unequal_cite` | text | when strategy is `unequal_appraisal` or `both` | Printed after "Unequal appraisal". |
| `additional` | list of `{label, cite}` | no | More grounds to list in the letter. |
| `protest_form` | text | no | Name of the protest form, shown in the checklist. |
| `valuation_date` | date | no | Makes the opinion of value read "as of January 1, 2027". |

### `tax_rates`

`total` (required, number > 0, at most 100): combined rate of all taxing units. `school` (number > 0, at most `total`): school-district rate,
required when an eligible exemption with an amount applies to `school`, or when `school_ceiling` is true. `source` (text): where the rates came from.

`school_ceiling` (boolean, optional, default false): set it to true when a school tax ceiling holds the owner's school tax fixed. School-tax savings are then left
out of the estimate: the protest and every `"all"` exemption use `total - school`, and exemptions that apply to `school` save $0. The savings meter, spreadsheet,
checklist and dashboard then say: "A school tax ceiling applies, so school-tax savings are not counted; the real figure depends on the ceiling amount."

### `exemptions`

`on_file` and `eligible` are lists of items. Only `eligible` items count toward savings; `on_file` items are listed for reference.

| Field | Type | Meaning |
|---|---|---|
| `name` | text, required | Shown everywhere. |
| `amount` | number >= 0 | Dollars removed from taxable value. |
| `applies_to` | `"school"` or `"all"` | Which rate prices the amount (`tax_rates.school` or `tax_rates.total`). Required when `amount` is given. |
| `kind` | `"fixed"` (default) or `"total"` | `total` means the whole bill is exempt: savings are the full tax on the argued value and `amount` is ignored. |
| `cite` | text | Printed beside the name. |
| `how_to_claim` | text | Required for `eligible` items. Printed verbatim in the checklist. |
| `documents` | list of text | Documents to bring. |
| `note` | text | Extra line in the checklist. |

An exemption with no `amount` and no `kind: total` (for example a tax ceiling) is listed as "not quantified".

### `comps[]`

Only `address` and `price` are required; blank values show as a dash and are skipped in the medians. Price plus adjustments must stay above 0.

| Field | Type | Meaning |
|---|---|---|
| `address` | text, required | |
| `price` | number > 0, required | Sale price, listing price or estimate. |
| `price_type` | `"sale"` (default), `"listing"`, `"estimate"` | Only sales enter the median and average and the "comparable sales" wording. Listings and estimates appear in a separate "Other data points (not used in the median)" table, and the letter mentions them only as supporting context. |
| `sale_date` | date | For a listing or estimate this is the listing or valuation date; outputs label it that way, never as a sale date. |
| `sqft`, `year_built`, `beds`, `baths`, `lot_sqft`, `distance_mi` | number | |
| `source` | text | CAD, MLS export, county records... |
| `adjustments` | list of `{label, amount}` | Signed dollars added to `price`: positive when the comp is inferior to the subject, negative when it is superior. |
| `notes` | text | Condition or other remarks. |

Adjusted value = `price` + sum of adjustments.

### `neighbors[]`

`address` and `appraised_value` required; `sqft`, `year_built`, `cad_account` optional. Neighbors without `sqft` are ignored in the
$/sq ft statistics.

### `income` (rental only, optional)

If the block is present every field below marked required must be given, and the net operating income must be above 0. Without it the income sheet and sections are left out.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `gross_rent` | number > 0 | yes | Potential gross rent per year. |
| `vacancy_pct` | 0 to 100 | yes | Vacancy and collection loss as a percent of gross rent. |
| `expenses` | list of `{label, amount}` | yes (may be empty) | Annual operating expenses. |
| `cap_rate_pct` | number > 0 | yes | Capitalization rate in percent. If the district uses a loaded rate, put the loaded rate here and say so in `cap_rate_source`. |
| `cap_rate_source` | text | yes | Where the rate came from. |
| `rent_source` | text | no | For example "Current lease: $2,150 per month". |
| `circuit_breaker_note` | text | no | Free text about the limit on appraisal increases for non-homestead property. Printed in the spreadsheet, checklist and dashboard; not in the letter. |

Income-indicated value = (gross rent - vacancy - expenses) / (cap rate / 100). The letter cites the income approach only when this value is below the CAD market value; otherwise it stays in the spreadsheet and dashboard, and the build prints a warning.

## What is computed

- **Comparable values**: median and average of the adjusted values of the sale comps only; medians use the middle value (average of the middle two when the count is even) and ignore missing values.
- **Unequal appraisal**: neighbor $/sq ft (median, average, range). The subject is compared at its market value, not the capped value. Rank is 1 plus the number of properties with a higher $/sq ft (so ties share a rank, and the rank in the table matches "rank N of M"), 1 being the highest. Percentile is the share of neighbors at or below the subject, ties counting half. Equalized value = neighbor median $/sq ft x subject sq ft.
- **Requested reduction**: `market_value - argued_value` (market value is `appraised_value` when `market_value` is omitted). The letter, spreadsheet and dashboard use it. For a capped homestead the outputs also show "Reduction below the taxable (capped) value", `max(0, appraised_value - argued_value)`, which is what can lower the tax.
- **Savings**: the scenario fraction `f` (from `settlement_scenarios`, low and high) is applied to the market-value reduction first, then the result is capped at the taxable value: `taxable = min(appraised_value, market_value - f x (market_value - argued_value))` and protest savings = `(appraised_value - taxable)` x `tax_rates.total` / 100. Without a cap (`market_value` equal to or omitted) this is `f x (appraised_value - argued_value)` x rate / 100. So a capped homestead can have $0 in the low scenario and savings only in the high one. If `argued_value` is at or above `appraised_value` the protest savings are $0 and every output says so ("No protest savings this year: ...") instead of showing a negative figure. These are settlement scenarios, not predictions. Each eligible exemption saves `min(amount, min(argued_value, appraised_value))` x its rate / 100 in both scenarios. Inputs are validated so the estimate can never exceed the tax bill (no negative or non-finite values, `school` at most `total`, `argued_value` below the market value).
- **Savings meter**: `Estimated savings so far: $X to $Y per year` (a single figure when both match).
- **Deadlines**: `deadlines` as written, else the core rules in `scripts/deadline_rules.json` computed from `notice_date`, `tax_year` and, when given, `hearing_date` and `arb_order_date`. A date that moved off a weekend or holiday carries a note with the statutory date, and a date that moved forward also shows the last business day before it (some county portals close on the original date).

## Deadline rules file

`scripts/deadline_rules.json` is an object: `{"holidays": [...], "rules": [...]}`; it ships with the rules from `references/deadlines.md`
(the statutes and notes in it are the law agent's wording). Each rule has `id`, `event`, `type`, `params`, `statute` (text), `note` (text)
and optional flags:

- `core` (default true): `false` keeps the rule as a reference date. The evidence package shows only core rules; `deadlines.py --all` lists the rest.
- `weekend_roll`: the statute moves a Saturday, Sunday or listed holiday to the next business day. `date` is the rolled day and `computed_date` stays the statutory day.
- `safe_day`: for dates counted back from a hearing or forward from an order, plan on the previous business day instead. Both days are shown.

Rule types:

| `type` | `params` |
|---|---|
| `fixed_date` | `month`, `day`, optional `year_offset` (the year is `tax_year + year_offset`) |
| `days_after_input` | `input` (`notice_date`, `hearing_date`, `arb_order_date`, `acquisition_date` or `qualified_date`), `days` (negative counts back) |
| `years_after_input` | `input`, `years`, optional `days`; Feb 29 falls back to Feb 28 |
| `days_after_notice` | `days`; same as `days_after_input` with `notice_date` |
| `days_after_event` | `event` (another rule's `id`), `days`; counted from that event's final (rolled) date |
| `years_after_event` | `event`, `years`; Feb 29 falls back to Feb 28 |
| `later_of`, `earlier_of` | `options`: a list of two or more `{type, params}` specs; they can nest |

A rule that needs an input that was not supplied is skipped (case fields `hearing_date` and `arb_order_date`; CLI flags `--notice-date`, `--hearing-date`,
`--arb-order-date`, `--acquisition-date` for the date the home was bought and `--qualified-date` for turning 65 or becoming disabled), and so is any rule
counted from a skipped rule; the CLI lists what was skipped and why. `--tax-year` may be left out when one of the dates is given (it defaults to that
date's year). Rules can appear in any order, and a rule that refers to itself or to a loop of rules is rejected when the file is loaded.

Holidays are entries in `holidays`, recomputed for every year: an ISO date string, `{"name", "type": "fixed", "date"}`, `{"name", "type": "annual", "month", "day"}`,
`{"name", "type": "nth_weekday", "month", "weekday", "n"}` (`n` is -1 for the last one) or `{"name", "type": "after", "holiday", "days"}`. The file models the
17 days of Gov't Code §662.003(a) (national) and (b) (state), which Tax Code §1.06 calls "legal state or national holiday"; §662.003 says each list "includes only" those
days. It does not say whether a holiday on a weekend shifts to a Friday or Monday, so none is modeled, and optional and local holidays are left out (see
`holidays_note` in the file). Run
`python scripts/deadlines.py --notice-date 2027-04-01 [--tax-year 2027] [--hearing-date D] [--arb-order-date D] [--all] [--ics out.ics] [--json]`
to see the result, including the statutory and rolled dates.

## Minimal example

```json
{
  "path": "homestead",
  "tax_year": 2027,
  "county": "Example County",
  "cad": {"name": "Example County Appraisal District", "address": "100 Appraisal Way, Exampleville, TX 75000"},
  "filing": {"methods": [{"method": "Online", "detail": "Use the district protest portal."}]},
  "notice_date": "2027-04-15",
  "owner": {"name": "Pat Sample", "mailing_address": "123 Example Street, Exampleville, TX 75000"},
  "subject": {
    "address": "123 Example Street, Exampleville, TX 75000",
    "cad_account": "R000123456",
    "sqft": 2100,
    "appraised_value": 465000
  },
  "legal_basis": {"market_value_cite": "Tax Code §41.41(a)(1)"},
  "tax_rates": {"total": 2.15},
  "comps": [
    {"address": "118 Sample Court, Exampleville, TX 75000", "price": 438000, "sqft": 2050},
    {"address": "207 Demo Lane, Exampleville, TX 75000", "price": 421500, "sqft": 2180}
  ],
  "argued_value": 430000
}
```

Full examples: `examples/sample-case.json` (homestead), `examples/sample-case-rental.json` (rental) and `examples/sample-case-capped.json` (homestead with a market value above the capped appraised value), with their
generated packages in `examples/sample-output/`.
