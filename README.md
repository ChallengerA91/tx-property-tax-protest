# Texas Property Tax Protest, a Claude Code skill

Give Claude your appraisal notice. It checks your county record, finds comparable sales and
neighbor appraisals, builds the evidence package, works out your real deadlines, and
rehearses the hearing with you.

Works for **homeowners** and for **rental or investment property**, in any Texas county.

> Verified against official Texas sources on 2026-10-08, for the 2027 protest season.
> The Legislature meets in 2027 and can change the rules. Check the exemption amounts and
> deadlines with your appraisal district before you rely on them.

## What you get

One command turns a short interview into five files:

| File | What it is |
|---|---|
| `comp_analysis.xlsx` | Subject property, comp table with adjustments, median and average adjusted value, neighbor value-per-square-foot ranking, and a rental income sheet when it applies |
| `protest_letter.docx` | One-to-two-page letter to your appraisal district with your comps and opinion of value |
| `filing_checklist.md` | How to file in your county, what to bring, exemptions to claim, and a savings table |
| `dashboard.html` | A single page with your value against the comps, estimated savings, and a deadline timeline. Opens offline |
| `deadlines.ics` | Calendar file with your protest and follow-up dates and reminders |

See real output built from a fictional address:
[homestead](examples/sample-output/homestead/),
[capped homestead](examples/sample-output/capped/) (where a lower market value may save
nothing this year) and [rental](examples/sample-output/rental/).

## How it works

Eight steps, one question at a time, with a running savings estimate:

1. Pick your path: homestead or rental.
2. Find your property and county appraisal district.
3. Enter your appraised value and notice date. You get your protest deadline right away.
4. Answer a few questions about your situation.
5. Claude checks the county record for description errors and missing exemptions.
6. Claude gathers comps and neighbor appraisals (or you paste in MLS or CAD data).
7. You agree on a strategy and an opinion of value. Claude builds the package.
8. You get filing instructions, and an optional mock hearing where Claude plays the appraiser.

## What it covers

- **Protest strategies:** market value, unequal appraisal, description errors, condition
  issues, and a recent purchase price.
- **Exemptions:** homestead, over-65 and disabled, disabled veteran and survivor
  exemptions, with the filing forms and deadlines. The 2025 changes are included: the school
  homestead exemption is now $140,000.
- **Rentals:** income approach (rent, vacancy, expenses, cap rate). The 20% cap on
  non-homestead increases ends after tax year 2026; the skill explains what that means
  for 2027.
- **Hearings:** informal and ARB scripts, rebuttals to common appraiser arguments, and a
  mock hearing.
- **After the ARB:** binding arbitration, SOAH, and district court, with deadlines and costs.
- **Counties:** the 25 most populous Texas counties, with portal links, phone numbers and
  filing methods. See [counties.md](skills/tx-property-tax-protest/references/counties.md).
  Any other county works too, with fewer built-in details.

Every figure, deadline and statute citation lives in
[law-and-figures.md](skills/tx-property-tax-protest/references/law-and-figures.md) with its
source, date and confidence tag. Items that could not be fully confirmed are listed there
too.

## Install

1. Clone this repo:

   ```bash
   git clone https://github.com/ChallengerA91/tx-property-tax-protest.git
   ```

2. Copy the `skills/tx-property-tax-protest` folder into your Claude Code skills folder:
   `~/.claude/skills/` on macOS and Linux, or `%USERPROFILE%\.claude\skills\` on Windows.

3. Install the Python packages the scripts need (Python 3.10 or newer):

   ```bash
   pip install -r skills/tx-property-tax-protest/scripts/requirements.txt
   ```

## Use it

Start Claude Code and say:

```text
Protest my property taxes at 1234 Main St, Denton TX
```

Claude asks whether this is your home or a rental, then walks through the steps. Your files
land in `output/`.

To try the scripts without Claude, build the sample package:

```bash
python skills/tx-property-tax-protest/scripts/build_package.py examples/sample-case.json --out my-output
```

## Key dates

Your protest deadline is the later of May 15 or 30 days after your notice. When that day is a
weekend or holiday, it moves to the next business day: in 2027, May 15 is a Saturday, so the
deadline is Monday, May 17. The skill computes your exact dates from your notice date. The
rules and sources are in
[deadlines.md](skills/tx-property-tax-protest/references/deadlines.md).

## Limits

- It gives information, not legal or tax advice. Confirm figures and deadlines with your
  appraisal district, and consider a licensed professional for large or complicated cases.
- It prepares your protest but does not file it for you.
- Local facts it cannot know, such as which taxing units added extra exemptions, come from
  your county record and tax bill.
- Comp sites sometimes block automated browsing. When that happens, Claude asks you to paste
  the data.

## Contributing

Pull requests are welcome, especially county details, corrections to the references (cite a
source), and edge cases. Install the test packages with
`pip install -r skills/tx-property-tax-protest/scripts/requirements-dev.txt`, then run
`python -m pytest` before sending one.

## License

See [LICENSE](LICENSE).
