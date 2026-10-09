---
name: tx-property-tax-protest
description: >
  Protest a Texas property tax appraisal, for homeowners and for rental or investment
  property. Use this skill whenever the user mentions property taxes, a tax protest, an
  appraisal notice, the CAD or appraisal district, an ARB hearing, comparable sales,
  unequal appraisal, or wants to lower their property tax bill. It also covers missed
  exemptions: homestead, over-65, disabled, and disabled veteran. The skill checks the
  county record, finds comps and neighbor appraisals, builds an evidence package
  (spreadsheet, protest letter, checklist, dashboard, calendar file), computes the
  user's real deadlines, and can run a mock hearing. Works for any Texas county; the 25
  largest have built-in filing details.
user_invocable: true
triggers:
  - protest property taxes
  - property tax protest
  - lower property taxes
  - appraisal notice
  - appraisal protest
  - unequal appraisal
  - ARB hearing
  - mock hearing
  - rental property tax
  - homestead exemption
  - disabled veteran exemption
---

# Texas Property Tax Protest

Take the user from an appraisal notice to a filed protest and a prepared hearing. Be direct
and efficient: plain sentences, no jokes, no filler.

## Rules for every run

1. **One question at a time.** Ask, wait for the answer, move on. Start each step with a
   progress line: `Step 3 of 8: Your situation`.
2. **Facts come from `references/`, never from memory.** Do not state a dollar amount,
   deadline, percentage or statute cite unless it is in `references/law-and-figures.md`,
   `references/deadlines.md`, `references/income-approach.md` or `references/beyond-arb.md`.
   Copy it exactly. If the file marks something unresolved or secondary-only, say so.
   Take CAD details (name, address, phone, filing methods) only from
   `scripts/county_lookup.py`, the user's notice, the CAD website, or the user. Never fill
   them in from memory.
3. **Check the as-of date.** The references were verified on 2026-10-08 for tax year 2027.
   The Legislature meets from 2027-01-12 and can change exemptions and rules. If today's
   date, or the date on the user's notice, is after that, tell the user once, early, to
   confirm exemption amounts and deadlines with the appraisal district (CAD) before
   relying on them.
4. **Disclaimer, kept light.** Use this one sentence: "This is general information, not
   legal or tax advice. Confirm figures and deadlines with your appraisal district."
   Say it once at the start and once in Step 8 before the filing steps. Use the same sentence
   for `disclaimer_text` in `case.json`; the spreadsheet, checklist and dashboard print it
   as a footer. The protest letter never carries it, because it goes to the CAD. Do not
   repeat it anywhere else.
5. **Savings meter.** After any step that adds an exemption, corrects an error or sets a
   stronger value, print one line: `Estimated savings so far: $X to $Y per year`. Use the
   formulas under "What is computed" in `references/case-schema.md`, or run
   `scripts/savings.py` once `work/case.json` is complete. Say the first time that these
   are scenarios, not predictions.
6. **Never invent evidence.** Comps, neighbor values, rents, expenses and cap rates come from
   a source the user can show at the hearing. Record the source for each one. Adjustment
   amounts must have a stated basis (paired sales, CAD data, or a market source). Mark an
   adjustment as an estimate if it has none.
7. **Never submit anything for the user.** Do not file a protest, upload to a CAD portal or
   send email. Prepare it and tell them where and how to file.

## Setup

- Create `work/` (drafts, notes, `case.json`) and `output/` (final files) in the user's
  working folder. Both are git-ignored. Tell the user that their address and account number
  stay in those folders.
- The `scripts/` folder is next to this file, not in the user's folder. Run scripts by their
  full path. Install once: `pip install -r <skill folder>/scripts/requirements.txt`.
- Use the browser tools for the CAD site, Redfin, Zillow and similar. If a site blocks
  automated browsing or the user has MLS or a CAD export, ask them to paste the data and
  map it into `comps[]` or `neighbors[]`. This fallback is always allowed.

## The steps

### Start (before Step 1)
Give the disclaimer sentence. Ask first whether they are **preparing a protest** or
**already have an ARB order** they want to appeal. For an order, open `references/beyond-arb.md`,
ask for the date on the order, and compute follow-on deadlines with
`python scripts/deadlines.py --tax-year YYYY --arb-order-date YYYY-MM-DD`. Otherwise ask
which path applies: **homestead** (they live in it) or **rental/investment**. Tell them the
plan in one sentence: eight steps, an evidence package at the end, and a mock hearing if
they want one.

### Step 1: Property and county
Ask for the address or CAD account number. Find the county, then run
`python scripts/county_lookup.py "<county>"` for its CAD name, website, phone, protest portal,
filing methods and quirks. Do not open `references/counties.json` directly; it is large.
If the script reports that the county is not covered, use the Comptroller's appraisal
district directory linked in `references/counties.md`, and take the CAD name, address and
filing methods from the notice, the CAD website or the user. Counties marked partially
verified need a confirmation from the CAD site before you tell the user how to file. Save
the notes to `work/property_details.txt`.

### Step 2: Notice and value
Ask for the appraised value, the date on the notice, and whether the notice shows **one
value or two** (a market value and a lower appraised or capped value).
- **Homestead with two values:** put the market value in `subject.market_value` and the
  taxable appraised value in `subject.appraised_value`. A lower market value saves tax only
  if it falls below the appraised value (`references/law-and-figures.md` section 4). Tell
  the user that now.
- **Rental:** the answer tells you whether any cap on the 2027 notice is still showing
  (see Step 5).
- **No notice date:** ask the user to find the notice (mail or the CAD portal). If they
  cannot, run `deadlines.py` with `--notice-date <tax year>-04-01` as a placeholder and
  label every deadline "assumed".

Run `python scripts/deadlines.py --notice-date YYYY-MM-DD --tax-year YYYY`. Tell the user
the statutory protest deadline, the date it moves to when it falls on a weekend or holiday,
and the last business day before it; some portals close on the original date, so advise
filing by that earlier day. Compare the deadline with today's date. If it has passed, read
`references/deadlines.md` for late-protest options before going on.

### Step 3: Their situation
Ask one at a time, skipping what does not apply to the path:
purchase price and date; known problems (foundation, flood, repairs, noise, nearby
commercial); whether the home is their homestead and whether the exemption is on file;
age 65 or older; disabled; veteran and VA rating; surviving spouse.
For a 65+ or disabled owner, ask whether the tax bill or notice shows a **school tax
ceiling** (a freeze). If it does, set `tax_rates.school_ceiling: true`. Savings then leave
out school-tax savings, and you must tell the user the figure is uncertain until they know
the ceiling amount. For rentals, rent, vacancy and expenses are collected in Step 5.

### Step 4: County record and exemptions
Open the property on the CAD site. Record the fields listed in `references/case-schema.md`
under `subject`, plus value history, exemptions on file, protest status, taxing units and
their rates, and the total tax rate. Check the description line by line against what the
user knows (square footage, baths, year built, lot size, features). Compare exemptions on
file with `references/law-and-figures.md` sections 1 to 3. A missing exemption can be worth
more than the protest, so flag it clearly, give the filing steps and form from that file,
and update the savings meter. Rental owners have no homestead exemptions (those need the
owner's principal residence), but ask whether the owner is a disabled veteran: a disabled
veteran exemption can be designated against any one property the veteran owns, including a
rental.

### Step 5: Evidence
- **Homestead.** Read `references/strategies.md`, then gather both kinds of evidence:
  sales comps (CAD, Redfin or Zillow, web search, MLS if the user has it) and neighbor
  appraisals from the CAD site for the unequal-appraisal ground. Aim for 5 to 8 sales comps (a practical target, not a legal rule).
  Good comps are close in location, size and age, sold near January 1 of the tax year, and
  were arm's-length sales. Those are selection guidelines, not legal rules. Follow
  `references/unequal-appraisal.md` for the neighbor sample. Listings and online estimates
  go in as `price_type: "listing"` or `"estimate"`; they support the argument but are not
  counted as sales.
- **Rental.** Read `references/income-approach.md`. Gather sales comps and neighbor
  appraisals as above. Add the `income` block only if the user has a rent source (lease or
  rent roll), vacancy, expenses, and a **cap rate with a source**. If they have no sourced
  cap rate, skip the income block, point them to the sourcing section of that file, and
  never suggest a number. Duplexes to fourplexes can lead with the income approach.
  Tell the user, and put the same text in `income.circuit_breaker_note` if you include
  `income`: "Texas's 20% limit on appraisal increases for non-homestead property (Tax Code
  §23.231) is written to end after tax year 2026. Under current law it does not apply to
  tax year 2027. The Legislature meets in 2027 and could change that, so check whether your
  notice shows one value or two."

Save raw data to `work/comps_data.txt`.

### Step 6: Analysis
Write a draft `work/case.json` as soon as you have comps and neighbors, and build it to
`work/draft` to see the computed medians, unequal-appraisal statistics and savings. Adjust
each comp with a stated basis. Compare the subject's CAD value per square foot with the
neighbors. Recommend a strategy (`market_value`, `unequal_appraisal` or `both`) and an
**argued value**, show the numbers behind them, and let the user adjust. The argued value is
the user's opinion of value, not a formula output. Update the savings meter.

### Step 7: Build the package
Finish `work/case.json` following `references/case-schema.md`. Set `prepared_on` to today's
date. Fill the legal fields from the references, not from memory: `legal_basis` cites, each
`exemptions` item's amount, `cite` and `how_to_claim`. Take the `cad` and `filing` blocks
from `python scripts/county_lookup.py "<county>" --case-fragment` when the county is
covered. Then run:

```bash
python scripts/build_package.py work/case.json --out output
```

This writes `comp_analysis.xlsx`, `protest_letter.docx`, `filing_checklist.md`,
`dashboard.html` and `deadlines.ics`. The script lists every field error at once; fix them
and rerun. Tell the user to read the letter and the spreadsheet before filing.

### Step 8: Hand-off
Show this summary, with real numbers:

```
PROPERTY TAX PROTEST SUMMARY
Subject:             [address]   CAD account: [number]
Market value:        $[x]        Argued value: $[y]
Estimated savings:   $[low] to $[high] per year (protest)
                     + exemptions: [list, or "none missing"]
Protest deadline:    [statutory date; moved date if it applies; last business day before]
Files:               output/ (spreadsheet, letter, checklist, dashboard, calendar)
```

Then say the disclaimer sentence once more, walk through how to file in this county (from
`filing_checklist.md`), and offer: the calendar file for the deadlines, the mock hearing,
and, if they later lose at the ARB, `references/beyond-arb.md`. Once they have a hearing
date or an ARB order, rerun `scripts/deadlines.py` with `--hearing-date` or
`--arb-order-date` to get the follow-on deadlines.

## Mock hearing (optional)

Offer it once at hand-off. If the user opts in, follow the mock-hearing rules in
`references/hearing-script.md` (section 6). Use only the user's real case data. End with
exactly three concrete improvements.

## References

| Need | File |
|---|---|
| Any exemption, cap, protest ground, burden of proof, deadline or form | `references/law-and-figures.md` |
| How each deadline is computed | `references/deadlines.md` |
| County, CAD website, phone, portal, filing methods | `scripts/county_lookup.py`, `references/counties.md` |
| Choosing and combining strategies | `references/strategies.md` |
| Neighbor-appraisal workflow | `references/unequal-appraisal.md` |
| Rental income approach, circuit-breaker status | `references/income-approach.md` |
| Hearing scripts, rebuttals, mock hearing | `references/hearing-script.md` |
| Binding arbitration, SOAH, court | `references/beyond-arb.md` |
| `case.json` fields and what the scripts compute | `references/case-schema.md` |

Load a reference only when its step needs it.
