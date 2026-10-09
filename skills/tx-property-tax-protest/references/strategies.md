# Protest strategies and how to choose

**Written for tax year 2027 (valuation date January 1, 2027). Statute cites and figures come from `law-and-figures.md` unless a line says otherwise. Statute text for §1.04(7), §23.01 and §23.013 was re-read on 2026-10-08 at tcss.legis.texas.gov (see Sources).**

A protest asks the ARB to change the value on the notice. The two grounds are in Tax Code §41.41(a):

- **(a)(1)** the appraised value is too high (market value);
- **(a)(2)** unequal appraisal.

Description errors, condition problems and a recent purchase price are kinds of evidence for (a)(1), not separate grounds. In `case.json`, `strategy` is `market_value`, `unequal_appraisal` or `both` (see `case-schema.md`).

## Rules that apply to every strategy

- **Value date.** Property is appraised at market value as of January 1 (§23.01(a)). For 2027 that is January 1, 2027. Evidence about later events is weak unless it shows the January 1 condition.
- **Burden.** In a value or unequal-appraisal protest the CAD must prove its case by a preponderance of the evidence presented at the hearing (§41.43(a)).
- **No fee, no upside risk at the ARB.** The CAD may not charge a fee to protest (§41.41(d)). The ARB cannot set the value above the value in the records the CAD submitted unless the owner asks for and agrees to it (§41.47(c-2)). File on time, then build the evidence. Deadlines are in `deadlines.md`.
- **Read both numbers on the notice.** A homestead under the 10% cap is taxed on the lesser of market value and last year's appraised value + 10% + new improvements (§23.23(a)). A lower market value saves tax this year only if it falls below the capped amount. Do this check before choosing a strategy.
- **A win carries forward.** After a reduction through protest, arbitration or suit, the CAD may raise the value the next year only with clear and convincing evidence (§23.01(e)). For an unequal-appraisal win the CAD has an easier route to meet that burden (see `unequal-appraisal.md`, pitfalls).

## Decision table: if X, lead with Y

| If | Lead with | `strategy` | Add |
|---|---|---|---|
| The CAD record has a wrong fact (area, bath count, year built, lot size, a feature you do not have) | Description error (section 3) | `market_value` | Re-run comps with the corrected facts |
| You bought at arm's length inside the sales window and paid less than the CAD value | Purchase price (section 5) | `market_value` | Sales comps; unequal appraisal if neighbors support it |
| Closed sales of similar homes sit below the CAD value | Market value (section 1) | `market_value` | Purchase price, condition |
| The CAD appraises similar nearby homes lower per sq ft than yours (subject ranks high) | Unequal appraisal (section 2) | `unequal_appraisal` | Sales comps if they also point lower |
| Sales comps and neighbor appraisals both point lower | The set with the cleaner comparables | `both` | State both grounds in the letter |
| A defect you can document (foundation, flooding, needed repairs, nuisance) | Condition (section 4), in dollars | `market_value` | Adjust comps for the same defect |
| Your supportable value is above the capped appraised value on the notice | Do not expect tax savings this year; decide whether to protest | n/a | A lower market value still shrinks the gap the cap closes each year |
| You have no evidence yet | File anyway to keep the right; gather evidence before the hearing | decide later | Request the CAD's evidence at filing |
| An exemption is missing or was denied | Not a value strategy. Apply with the CAD; if denied, protest under §41.41(a)(4) (`law-and-figures.md` section 5 covers total exemptions) | n/a | `legal_basis.additional` |
| The property is a rental | `income-approach.md` | n/a | See "Homestead and rental" below |

## 1. Market value (§41.41(a)(1))

**When it applies.** Similar homes sold for less than the CAD's value, or the market fell, or the CAD's value cannot be squared with what homes like yours sell for.

**Evidence that carries weight.**
- Closed sales, not listings or online estimates. A sale is not considered comparable unless it is within 24 months of the valuation date, or within 36 months for residential property in counties with more than 150,000 people. In a smaller county an older sale may be used only if too few sold in the window (§23.013(b), (b-1)).
- Comparability follows the factors in §23.013(d): location, lot and improvement square footage, age, condition, access, amenities, views, and legal burdens such as easements or deed restrictions.
- Each sale adjusted for market change between the sale date and January 1 (§23.013(c)) and for differences from the subject. Adjustments and comparable selection must follow generally accepted appraisal methods (§23.01(f), (h)).
- The source of every sale (MLS export, county record, agent) and its date.

**What the CAD will counter.** Comps are not comparable, the market is up, mass appraisal, sale not arm's length. Replies are in `hearing-script.md` (R1 to R4, R8 to R11).

**In case.json.** `strategy: "market_value"`; `legal_basis.market_value_cite: "Tex. Tax Code §41.41(a)(1)"`; `comps[]` with `price_type`, `sale_date` and `adjustments[]` (positive when the comp is inferior to the subject); `market_notes[]`; `argued_value` below `subject.market_value` (the same as `subject.appraised_value` when no cap applies).

## 2. Unequal appraisal (§41.41(a)(2))

**When it applies.** The CAD's own appraisals of comparable properties are lower per square foot than yours. The claim is about how the district treats your property relative to others, not about what the home would sell for.

**Evidence that carries weight.** The CAD's appraisals of a reasonable number of comparable properties, appropriately adjusted, with your property's rank and the median. The owner wins unless the CAD proves one of the three tests in §41.43(b).

**What the CAD will counter.** Your neighbors differ, the district median ratio is level, per-square-foot is not an adjustment. Replies are in `unequal-appraisal.md`.

**Workflow and case.json fields.** See `unequal-appraisal.md`.

## 3. Errors in the property description

**When it applies.** The CAD record differs from the property: living area, bedrooms or bathrooms, year built, lot size, quality or condition class, or a feature you do not have (pool, finished attic, extra garage bay).

**Evidence that carries weight.** Builder floor plan, survey or plat, your own measurements with photographs, permit records, a prior appraisal or inspection report. Compare the CAD's property record line by line before anything else.

**How to raise it.** There is no separate lettered ground. Argue it as a value error under §41.41(a)(1); Form 50-132 has a "Property description is incorrect" box. The chief appraiser can correct a clerical error at any time if the fix does not raise the tax (§25.25(b)). The ARB can also correct errors before it approves the records (§41.01(a)(3), §41.09, §41.10).

**What the CAD will counter.** Its measurement, aerial imagery or last inspection says otherwise; the plan is not as built; it asks to inspect (reply R14 in `hearing-script.md`). An inspection can also find features the record lacks, so decide before inviting one.

**In case.json.** Put the documented figure in `subject.sqft` (and other subject fields), because the equalized value and $/sq ft use it. Keep the CAD's figure in a note key such as `subject._cad_sqft`. Add a `legal_basis.additional` entry `{"label": "Property description error", "cite": "Tex. Tax Code §41.41(a)(1)"}` and state the correction in `arguments[]`. Then run comps or the unequal analysis with the corrected facts.

## 4. Condition issues

**When it applies.** Foundation movement, flooding or drainage, roof or system failure, needed repairs, or a nuisance such as road noise, power lines or adjacent commercial use, that the CAD's record does not reflect.

**Evidence that carries weight.** The CAD must appraise on the individual characteristics of the property and consider all available evidence specific to it (§23.01(b)). Bring:
- dated photographs showing the condition on or before January 1, 2027;
- written repair estimates from licensed contractors, or an engineer's or inspector's report;
- comparables with the same defect, or comparables adjusted by the estimated cost to cure;
- for nuisance, photographs and measurements of the source, and comps away from it.

**What the CAD will counter.** Normal wear, no proof of effect on market value, the record assumes average condition, repairs done since January 1. Convert each defect to a dollar amount with support, and show the January 1 condition (reply R13 in `hearing-script.md`).

**In case.json.** `strategy: "market_value"`; add a `comps[].adjustments[]` line per defect (for example "Foundation repair needed, estimate attached") or a bullet in `arguments[]`; set `argued_value` to include the adjustment. Add repair estimates and photographs to `filing.hearing_documents`.

## 5. Recent purchase price

**When it applies.** You bought the property at arm's length and paid less than the CAD's value. The statute defines market value as the price at which the property would transfer for cash or its equivalent if it is exposed for sale in the open market with a reasonable time to find a purchaser, both parties know the property's uses and restrictions, and neither can take advantage of the other's exigencies (§1.04(7)). A purchase that meets those conditions fits the definition. The statute does not make a purchase price controlling, and does not set a rule for how long a purchase stays relevant. A purchase inside the 24-month window (36 months for residential property in counties with more than 150,000 people) is easiest to defend because that is the window the statute uses for comparable sales (§23.013(b), (b-1)).

**Evidence that carries weight.** Closing disclosure or settlement statement; the contract; the listing history and days on the market; proof the parties were unrelated and used agents; any seller credits, with the net price; the inspection report; and what personal property was included, if any.

**What the CAD will counter.** Not arm's length, the market moved since the purchase (the statute requires time adjustment for comparable sales, §23.013(c)), the price included other items, a mass-appraised value is more reliable. Replies are in `hearing-script.md` (R2, R4).

**When not to lead with it.** Family or related-party sale, a sale under pressure, a foreclosure or short sale, or a purchase long before January 1, 2027 in a market that has moved.

**In case.json.** `subject.purchase_price` and `subject.purchase_date` (printed in the letter and spreadsheet), plus a `market_notes[]` line that states how the sale was exposed to the market.

## Homestead and rental

- **Homestead.** Strategies 1 to 5 apply. Check the exemptions on file (`law-and-figures.md` sections 1 to 3) and the 10% cap (section 4) before arguing value; a missing exemption can matter more than a value reduction.
- **Rental.** There is no homestead exemption or §23.23 cap. The 20% non-homestead limit (§23.231) is written to end after tax year 2026; confirm whether the notice shows one value or two (`income-approach.md`, section 1, table A). Single-family rentals lead with sales comps and unequal appraisal; the income approach is a supporting exhibit. Duplexes to fourplexes can lead with the income approach. Set `path: "rental"`; `income` is then required. See `income-approach.md` sections 2 and 6.

## Sources

`law-and-figures.md` sections 4, 5, 6 and 10; `deadlines.md`; `case-schema.md`; `income-approach.md`. Tax Code §1.04(7), §23.01(a), (b), (e), (f), (h) and §23.013(a) to (d) read 2026-10-08: https://tcss.legis.texas.gov/resources/TX/htm/TX.1.htm and https://tcss.legis.texas.gov/resources/TX/htm/TX.23.htm (same text as statutes.capitol.texas.gov).
