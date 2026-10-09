# Unequal appraisal workflow (homeowner, using the CAD's own data)

**Written for tax year 2027. Statute cites and figures come from `law-and-figures.md` unless a line says otherwise (see Sources). Example numbers are fictional and match `examples/sample-case.json`.**

## 1. What the claim is

- The ground is §41.41(a)(2): unequal appraisal of the owner's property.
- The CAD carries the burden (§41.43(a)). The owner wins unless the CAD proves one of the three tests in section 2 (§41.43(b)).
- It uses the district's own records, so it works when sales are thin, or when the value is near what homes sell for but higher than the neighbors' appraisals.
- It asks how the district treats your property relative to others. It does not ask what the home would sell for. It can be combined with market value (`strategy: "both"`). See `strategies.md` for when to lead with it.

## 2. The three tests the CAD can use to defeat the claim

| Test | Statute | The CAD must show | In practice |
|---|---|---|---|
| Ratio, representative sample | §41.43(b)(1) | Your appraisal ratio is at or below the median level of appraisal of a reasonable and representative sample of other properties in the district | District-wide ratio study. Ask for the sample and the market value it assigns your property |
| Ratio, similar properties | §41.43(b)(2) | Your ratio is at or below the median of a reasonable number of properties similarly situated to, or of the same general kind or character as, yours | The same, with a narrower sample |
| Comparable appraisals | §41.43(b)(3) | Your appraised value is at or below the median appraised value of a reasonable number of comparable properties, appropriately adjusted | Your main test. You build this comparison from the CAD's records |

Reading the tests:

- The CAD needs to prove only one test. Build a sample that holds up under (b)(3), and ask what ratio data it holds for (b)(1) and (b)(2).
- An appraisal ratio is appraised value divided by market value (§1.12(b)(2); land appraised on a non-market basis uses a different benchmark, §1.12(b)(1)). The median is the middle value of an ordered list, or the average of the two middle values when the count is even (§1.12(c)).
- The statute sets no minimum count, radius, size limit or age limit. It says "reasonable number" and "comparable ... appropriately adjusted". Selecting comparables and adjusting them must follow generally accepted appraisal methods (§23.01(f)); those include the Appraisal Institute texts, USPAP and mass-appraisal publications (§23.01(h)).
- At the ARB the ratio tests have no 10% margin. In court the ratio tests apply only if the property exceeds the median by at least 10 percent; the comparables test has no margin (§42.26(a); `beyond-arb.md` section 6).

## 3. Choose the comparable sample

Write the selection criteria before looking at any values. Then apply them to every property, not to the ones that help.

| Match on | Why |
|---|---|
| Same CAD, same property type and improvement class (single-family detached with single-family detached; not townhome, duplex or condo) | "Same general kind or character" (§41.43(b)(2)); §23.013(d) |
| Location: same subdivision or neighborhood code first; widen only if too few, and record the reason | §23.013(d) lists location first |
| Living area close to the subject's | §23.013(d): lot and improvement square footage |
| Year built and quality or condition class | §23.013(d): age, condition |
| Lot, stories, garage, pool, foundation | §23.013(d): amenities; adjusted later |
| The same tax year's values you are protesting | Mixing years compares different appraisals |

Example filter for the fictional subject (2,100 sq ft, built 2005, Sample Meadows): single-family, same subdivision, 1,900 to 2,300 sq ft, built 2000 to 2010. The statute sets no such limits; pick yours first and be ready to say why.

Leave out, and write down why: new construction or partial-year values, land appraised under a special-appraisal subchapter, properties with an unrecorded teardown or major change, vacant lots.

Keep a log with one line per property: in or out, and the reason. Keep properties that do not help you. A set built from stated criteria is harder to attack than a hand-picked few.

## 4. Pull the data from the CAD site

| Field | Why |
|---|---|
| Account number, address, neighborhood or subdivision code | Selection and proof |
| Property type, improvement class | Same kind |
| Living area (sq ft) | $/sq ft denominator |
| Year built, quality and condition class | Comparability |
| Beds, baths, stories, foundation, garage | Comparability, adjustments |
| Pool and other improvements, with the CAD's value for each | Adjustments from the CAD's own numbers |
| Lot size, land value, improvement value | Land versus improvement check |
| Market value and appraised (capped) value, and exemptions on file | Cap check |
| Prior-year value | Trend |
| Sale price and date, if the CAD shows them | Ratio method (section 7) |

Record the date pulled and keep a printout or screenshot of each record. If the site blocks automated browsing, ask the user to paste the table or upload a CAD export. Leave a gap blank rather than filling it from memory or a third-party site.

**Capped homestead.** Compare market value to market value for the subject and every neighbor. For a homestead under the §23.23 cap, §42.26(d) (court) and §1.12(d) (ratios) require this. §41.43(b)(3) itself says "appraised value", so expect the CAD to ask which you used; keep the capped values in a note. In `case.json`, put the subject's CAD market value in `subject.market_value` and the taxable (capped) value in `subject.appraised_value`. For each entry in `neighbors[]`, enter that neighbor's market value in `appraised_value` (the schema's field name) and keep any capped figure in a note key such as `"_capped_value": 395000`. The generated savings figure already counts only the reduction below the taxable value, so do not recompute it by hand.

## 5. Compute

1. **$/sq ft** = value / living area, for the subject and each neighbor, using the same value type for all.
2. **Median** of the neighbors' $/sq ft. Also note the average and range, for context only.
3. **Rank** of the subject among subject plus neighbors, 1 = highest $/sq ft.
4. **Percentile** = share of neighbors at or below the subject; ties count half.
5. **Equalized value** = neighbor median $/sq ft x subject sq ft. Gap = appraised value - equalized value.
6. **Land check** when lots differ: compare land value per lot sq ft and improvement value per living sq ft separately. Total $/sq ft hides a lot-size difference.
7. **Savings** = (appraised - argued) x total rate / 100, with the rate in dollars per $100.

Worked example (fictional; it matches the generated sheet for `examples/sample-case.json`):

| Rank | Address | Value | Sq ft | $/sq ft |
|---|---|---|---|---|
| 1 | 134 Example Street | $470,000 | 2,090 | $224.88 |
| 2 | **123 Example Street (subject)** | **$465,000** | **2,100** | **$221.43** |
| 3 | 130 Example Street | $447,000 | 2,170 | $205.99 |
| 4 | 121 Example Street | $428,000 | 2,080 | $205.77 |
| 5 | 122 Example Street | $436,000 | 2,120 | $205.66 |
| 6 | 133 Example Street | $452,000 | 2,200 | $205.45 |
| 7 | 125 Example Street | $441,000 | 2,150 | $205.12 |
| 8 | 129 Example Street | $417,000 | 2,040 | $204.41 |
| 9 | 126 Example Street | $409,000 | 2,010 | $203.48 |

Eight neighbors. Median $205.56 (average of the 4th and 5th values), average $207.60, range $203.48 to $224.88. Subject rank 2 of 9, percentile 88% (87.5% rounded). Equalized value $431,671; gap $33,329. At the fictional total rate of 2.15 per $100 that gap is about $717 a year. The neighbor at $224.88 is above the subject; it stays in, and the median does not depend on it.

The statute tests the median. Lead with the median and the equalized value. Rank and percentile help the panel see the picture; they are not the legal test.

## 6. Adjust

$/sq ft is a first screen. §41.43(b)(3) says "appropriately adjusted" and §23.01(f) requires recognized methods, so adjust for differences that remain after selection.

- Adjust for size, age or quality class, lot, pool, garage, other improvements and condition.
- Take amounts from the CAD's own numbers: the line-item value on each account (pool, garage, porch), land value per lot, improvement value per living sq ft. If the schedule is not visible, request it under §41.461. Unsupported round numbers are what the CAD attacks.
- Direction: subtract the value of a feature the neighbor has and you lack; add it if the reverse. Fictional example: the district lists a pool at $18,000 on a neighbor's account and your lot has none, so take $18,000 off that neighbor's value before dividing by its sq ft.
- Keep a table: neighbor, item, amount, source.

The generated unequal-appraisal sheet shows unadjusted CAD data. Put the adjustment table on a separate page, state the adjusted median in `arguments[]`, and set `argued_value` from the adjusted comparison.

## 7. Appraisal ratio method (when reliable sale prices exist)

Use it only for neighbors whose arm's-length sale price you can document (MLS export, agent, closing documents).

1. For each sold neighbor: CAD value / sale price.
2. The median of those ratios is the neighborhood's level of appraisal.
3. Subject ratio = CAD value / your supported market value.
4. If the subject's ratio is above the median, it is appraised at a higher level than its neighbors. Equalized value = your market value x the median ratio.

Separate fictional illustration: neighbor ratios 0.96, 0.97, 0.95, median 0.96. Subject CAD value $465,000 / supported market value $430,000 = 1.08. Equalized value $430,000 x 0.96 = $412,800. This applies the arithmetic of the (b)(1) and (b)(2) tests; the statute does not prescribe a method, and the CAD can dispute your market value.

## 8. Fill in case.json and read the output

- `strategy`: `"unequal_appraisal"` or `"both"`. `legal_basis.unequal_cite`: `"Tex. Tax Code §41.41(a)(2)"`.
- `neighbors[]`: `address`, `appraised_value`, `sqft`, `year_built`, optional `cad_account`. At least one needs `sqft`; neighbors without it are ignored in the statistics.
- `argued_value` must be below `subject.market_value` (which equals `subject.appraised_value` when no cap applies). It is your judgment; the equalized value is the starting point.
- `arguments[]`: adjustments, the sample criteria, the cap note.

```json
"neighbors": [
  {"address": "121 Example Street", "appraised_value": 428000, "sqft": 2080, "year_built": 2005, "_capped_value": 395000}
]
```

The workbook gets an **Unequal Appraisal** sheet: rank, address, value, sq ft, $/sq ft, year built, and the subject minus each neighbor; then neighbor count, median, average and range, subject $/sq ft, rank ("2 of 9"), percentile, equalized value, appraised value and difference. The letter adds a bullet with the subject's $/sq ft, rank and median, and a neighbor table.

## 9. Letter and hearing language

Extra bullets for `arguments[]` (fictional values):

- "The district appraises eight single-family homes on Example Street, built 2003 to 2006 with 2,010 to 2,200 sq ft of living area, at a median of $205.56 per square foot. My property is appraised at $221.43."
- "The selection criteria were set before values were reviewed. Every property meeting them is included."

Spoken at the hearing (about 45 seconds):

> I am protesting on market value and on unequal appraisal, under Tax Code section 41.41(a)(1) and (a)(2). On unequal appraisal, I compared the district's own appraisals of eight homes near mine, built 2003 to 2006, 2,010 to 2,200 square feet. Their median is $205.56 per square foot. Mine is $221.43, second highest of nine. At the median my home would be appraised at $431,671, which is $33,329 below the notice. Under section 41.43(b), the protest is decided for me unless the district shows my value is at or below the median of comparable properties, appropriately adjusted, or meets one of the ratio tests. My sales evidence indicates $421,000. I ask for $425,000.

## 10. Counters specific to unequal appraisal

For counters shared with market value (average $/sq ft, neighbors' appraisals as evidence, different quality, the 10% cap) see `hearing-script.md` R5 to R7 and R12.

| The CAD says | Reply |
|---|---|
| "Our ratio study shows the district is at its median level." | Ask for the sample, how many properties, and the market value it assigned to yours. The ratio tests only help it if your ratio is at or below the median. Make the request under §41.461 |
| "Per-square-foot is not an adjustment method." | Agree it is a screen. Show the adjusted comparison and the CAD-sourced amounts (§23.01(f)) |
| "You chose neighbors that help you." | Show the written criteria, the log of every property considered, and the reasons for exclusions |
| "Lot sizes differ." | Show land and improvement values compared separately (section 5, step 6) |
| "We have our own comparable set." | Ask for the list and adjustments; compare each to your property. The CAD's sample must follow the same generally accepted methods (§23.01(f)) |

## 11. Pitfalls

- **Cherry-picking.** Dropping neighbors only because they hurt you. The statute asks for a reasonable and representative or comparable set.
- **Mixing property types.** Townhomes, duplexes, condos, acreage, or different improvement classes in one sample.
- **Capped values.** Comparing a capped value to uncapped values. Use market value and keep the capped figure in a note.
- **Different years.** Pull every value for the tax year you are protesting.
- **Total $/sq ft only.** Check land and improvements when lots differ.
- **Rank as the test.** The test is the median.
- **Unsupported adjustments.** Round numbers with no source.
- **Weaker carry-forward.** After an unequal-appraisal win the CAD can meet its next-year burden by showing the inequality was corrected for the properties considered (§23.01(e)). Expect less protection than after a market-value win.
- **Settlement terms.** An agreement with the chief appraiser is final for the matter it covers (§1.111(e)). Read it first.

## Sources

`law-and-figures.md` sections 4 (rows on §42.26(d), §23.01(e)), 5 (§41.43) and 6; `beyond-arb.md` section 6; `case-schema.md`; scripts `analysis.py` and `render_xlsx.py` for the computed fields. Statute text read 2026-10-08 at tcss.legis.texas.gov (Legislative Council, same text as statutes.capitol.texas.gov): §1.12 and §1.111(e) in TX.1.htm, §23.01 and §23.013 in TX.23.htm, §41.43 in TX.41.htm, §42.26 in TX.42.htm, each at https://tcss.legis.texas.gov/resources/TX/htm/TX.<chapter>.htm.
