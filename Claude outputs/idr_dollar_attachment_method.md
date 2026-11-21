# Attaching real dollar amounts to Federal IDR dispute lines

## 1. The problem

CMS publishes each IDR dispute line twice, on two sheets, and gives them no shared key.

| | OON sheet | QPA and Offers sheet |
|---|---|---|
| Identifiers | Dispute Number, DLI Number | none |
| Provider and plan | name, NPI, email domain, size | none |
| IDR entity, outcome, days to decide | yes | none |
| Quarter, service code, place of service, line-item type, default flag | yes | yes |
| Geography | state | region (MSA) |
| QPA and the three offers | **as percentages only** | **as actual dollars** |

| Sheet | Lines |
|---|---|
| OON | 8,233,903 |
| Air Ambulance | 104,383 |
| QPA and Offers | 8,338,286 |
| OON + Air | **8,338,286** |

The totals tie exactly, every quarter. **Every line on the QPA sheet is the same dispute line as
exactly one line on the OON sheet.** CMS simply chose which facts to print on which sheet.

The consequence: the sheet that names the carrier prints no dollars, and the sheet with the
dollars names nobody. Asking "what did this carrier offer, in dollars" is unanswerable from
either sheet alone. Dispute Numbers do not help — they live on the sheet without dollars.

## 2. The key

The OON sheet publishes four percentage fields:

```
Provider/Facility Offer as % of QPA
Health Plan/Issuer Offer as % of QPA
Prevailing Party Offer as % of QPA
QPA as Percent of Median QPA
```

The first three are each offer divided by that line's QPA. The fourth is that line's QPA divided
by the median QPA of its peer group.

The same four numbers can be **computed** from the QPA sheet's dollars. Computed on one side,
published on the other, they become a fingerprint — and the fourth is the powerful one, because
its denominator is a statistic drawn from thousands of other lines, so it lands on a value very
few lines share.

Four steps to use it.

---

## 3. Step 1 — Define the cell and compute its median

A **cell** is the group CMS computes one median over: **quarter × service code × geographical
region.** Nothing coarser works. Code 99284, 2025 Q4, Texas:

| Geographical Region | Lines in cell | Median QPA |
|---|---|---|
| Dallas-Fort Worth-Arlington, TX | 16,754 | $252.55 |
| Austin-Round Rock-Georgetown, TX | 11,886 | $288.11 |
| Houston-The Woodlands-Sugar Land, TX | 10,919 | $250.34 |
| San Antonio-New Braunfels, TX | 9,463 | $344.43 |
| Longview, TX | 5,841 | $215.28 |
| Beaumont-Port Arthur, TX | 2,797 | $359.32 |

One code, one quarter, one state — **$215 to $359.** The region is not optional, and the OON
sheet does not have it. That is the whole difficulty.

We compute the median for every cell on the QPA sheet: 6,574,180 lines carry a region, giving
59,291 cells.

## 4. Step 2 — Compute the four ratios on every QPA line

Each ratio is rounded to two decimals, matching CMS's published precision.

**Example A** — Dallas-Fort Worth-Arlington TX, 2025 Q4, code 99284, place of service 23, batched,
provider prevailed.

| Field | Value |
|---|---|
| QPA | $897.59 |
| Provider/Facility Offer | $5,037.38 |
| Health Plan/Issuer Offer | $1,008.93 |
| Prevailing Offer | $5,037.38 |
| Median QPA for its cell (16,754 lines) | $252.55 |

```
Provider offer % of QPA  = 5,037.38 / 897.59 = 5.6121  -> 5.61
Plan offer % of QPA      = 1,008.93 / 897.59 = 1.1240  -> 1.12
Prevailing % of QPA      = 5,037.38 / 897.59 = 5.6121  -> 5.61
QPA % of median QPA      =   897.59 / 252.55 = 3.5541  -> 3.55
```

**Example B** — Chattanooga TN-GA, 2023 Q2, code 99283, provider prevailed.

| Field | Value |
|---|---|
| QPA | $78.49 |
| Provider/Facility Offer | $225.00 |
| Health Plan/Issuer Offer | $82.41 |
| Prevailing Offer | $225.00 |
| Median QPA for its cell (916 lines) | $79.87 |

```
Provider offer % of QPA  = 225.00 / 78.49 = 2.8666  -> 2.87
Plan offer % of QPA      =  82.41 / 78.49 = 1.0499  -> 1.05
Prevailing % of QPA      = 225.00 / 78.49 = 2.8666  -> 2.87
QPA % of median QPA      =  78.49 / 79.87 = 0.9827  -> 0.98
```

A line is only fingerprintable if all four dollars are present and it is not a default:

| QPA sheet | Lines |
|---|---|
| All lines | 8,338,286 |
| Region published | 6,574,180 |
| Region and a QPA dollar | 5,244,809 |
| All four dollars | 4,962,685 |
| Not a default — **fingerprintable** | **4,898,336** |

## 5. Step 3 — Normalise two fields before comparing

Two formatting defects would otherwise break every comparison.

**Place of service.** Example B's line reads `23.0` on the QPA sheet and `23` on the OON sheet.
59,532 lines are affected, all in 2023 Q2. Fix: strip a trailing `.0`, pad to two characters.
277 OON lines carry the mirror defect on service code.

**Dispute Line Item Type.** The QPA sheet does not carry this field in the earliest releases —
Example B's line is blank where its OON counterpart reads `Single`. Fix: when it is absent, treat
it as a wildcard rather than as a literal blank.

## 6. Step 4 — Match, most specific field set first

| Tier | Fields compared |
|---|---|
| **1** | Quarter · Service Code · Place of Service Code · Offer Selected · Dispute Line Item Type · Initiating Party · Certified IDR Entity · the four ratios |
| **2** | the same, without Initiating Party and Certified IDR Entity |
| **3** | the same, without Dispute Line Item Type |

A line is matched at the most specific tier that finds it, and never re-matched at a looser one.

### Example 1 — narrowing to a single line

Example A's computed values, applied against all 8,233,903 OON lines:

| Constraint added | OON lines remaining |
|---|---|
| — | 8,233,903 |
| Quarter = 2025Q4 | 1,407,684 |
| Service Code = 99284 | 230,478 |
| Place of Service Code = 23 | 228,364 |
| Dispute Line Item Type = Batched | 128,632 |
| Offer Selected = Provider | 106,786 |
| **QPA as Percent of Median QPA = 3.55** | **54** |
| Provider Offer as % of QPA = 5.61 | **1** |
| Plan Offer as % of QPA = 1.12 | 1 |
| Prevailing Offer as % of QPA = 5.61 | 1 |

One line. `DISP-4519006 / DLI - 12775571` — Blue Cross and Blue Shield of Texas. The median ratio
alone removes 99.95% of what the service and geography fields left behind.

### Example 2 — narrowing to a group, and why that is still sound

Example B's computed values:

| Constraint added | OON lines remaining |
|---|---|
| — | 8,233,903 |
| Quarter = 2023Q2 | 113,121 |
| Service Code = 99283 | 12,276 |
| Place of Service Code = 23 | 12,263 |
| Offer Selected = Provider | 7,639 |
| **QPA as Percent of Median QPA = 0.98** | **263** |
| Provider Offer as % of QPA = 2.87 | 67 |
| Plan Offer as % of QPA = 1.05 | **66** |
| Prevailing Offer as % of QPA = 2.87 | 66 |

Not one line — 66. And on the QPA sheet, the identical fingerprint also returns exactly 66 lines.
A closed block: those 66 are those 66, in some order.

**That is sufficient, because the question asked is "what were the dollars", not "which line is
this".** Inside those 66 QPA-sheet lines:

| | Distinct values |
|---|---|
| QPA | **1** — $78.49 |
| Provider/Facility Offer | **1** — $225.00 |
| Prevailing Offer | **1** — $225.00 |
| Health Plan/Issuer Offer | 2 — $82.41 (65 lines) and $82.42 (1 line) |

Every line in the block carries the same QPA and the same provider offer. The plan offer differs
by **one cent** on one line out of 66 — both round to the same published 1.05. So the dollars are
determined even though the individual row is not.

This is the general case, not a lucky one. Across all 4,979,123 OON lines we assign:

| How the dollar was obtained | Lines | Share |
|---|---|---|
| **Matched line — the block had one distinct QPA dollar** | **4,689,095** | **94.2%** |
| Cell lookup, one possible dollar | 141,557 | 2.8% |
| Derived as QPA % of median × median | 75,701 | 1.5% |
| Cell lookup, candidates within 2% | 72,770 | 1.5% |

Only 35% of assigned lines are strict 1:1. Restricting to those would discard two thirds of the
coverage to gain nothing, because in 94.2% of cases the block speaks with one voice on the dollar.

| Block size | Assigned lines | Share |
|---|---|---|
| 1 (exact 1:1) | 1,755,166 | 35.3% |
| 2–10 | 1,426,472 | 28.6% |
| 11–100 | 1,181,107 | 23.7% |
| 100+ | 434,367 | 8.7% |
| cell lookup | 182,011 | 3.7% |

## 7. A second path, for lines with no offers

A default has no plan offer, so no fingerprint can be built — but a dollar is still recoverable,
because only one ratio is needed, not four.

**Example 3** — `DISP-1086195 / DLI - 2921646`, 2024 Q3, code 77063, Location of Service `TX`,
defaulted, UnitedHealthcare. Published `QPA as Percent of Median QPA = 3.02`. No provider offer
ratio printed.

Enumerate every Texas cell for that code and quarter, and ask which one contains a real QPA
dollar whose ratio to its own median rounds to exactly 3.02:

| Candidate region | Median QPA | A QPA dollar at ratio 3.02? |
|---|---|---|
| Houston-The Woodlands-Sugar Land | $33.46 | **yes — $101.14** |
| Dallas-Fort Worth-Arlington | $55.00 | no |
| Austin-Round Rock-Georgetown | $59.45 | no |
| El Paso | $27.10 | no |
| Granbury | $65.20 | no |
| …5 more TX regions | | no |

One survivor from ten. QPA **$101.14**, median **$33.46**, region Houston — on a defaulted line.

This path carries **149,892 defaulted lines**, which the fingerprint cannot reach at all. Section 8
proves it works.

## 8. Proving the second path

The fingerprint can be checked against CMS's own published ratio. The cell lookup cannot — it is
used precisely where CMS prints too little to check against. So it is tested on lines where the
answer is already known.

**Design.** Take the 4,689,095 OON lines the fingerprint priced. Their dollar is the control. Now
run the cell lookup on those same lines, using only quarter, service code, Location of Service and
the published median ratio — it never sees the fingerprint's answer. Compare.

| Candidates the lookup found | Lines tested | Dollar exact | Dollar within 1% | Median exact | Region exact |
|---|---|---|---|---|---|
| **exactly one — accepted** | **1,409,766** | **98.85%** | **98.88%** | **97.04%** | **98.39%** |
| within 0.5% — accepted | 314,297 | 79.09% | 99.12% | 97.23% | 97.42% |
| within 2% — accepted | 192,787 | 74.31% | 93.22% | 94.03% | 94.55% |
| further apart — **refused** | 2,711,763 | 61.08% | 66.19% | 66.07% | 65.42% |

The last row is the point. On lines where the lookup finds several distant candidates it is right
only 61% of the time — and those are exactly the lines it refuses to price. **The gate is doing the
work, not luck.** Accept only a single surviving candidate and accuracy is 98.85%; accept anything
and it collapses by 38 points.

**The obvious objection.** The control group is contested lines. The lookup is actually deployed on
defaults. Those are not the same population:

| | Control group | Deployment population |
|---|---|---|
| Lines | 4,689,095 | 214,327 |
| Found exactly one candidate | 30.1% | 66.1% |
| Median lines behind the cell | 47 | **6** |
| Defaulted | 0.5% | 57.8% |

The deployment population sits in far thinner cells. So the control is re-cut by cell volume, to
test the lookup under the same conditions it actually faces:

| Lines behind the cell | Lines tested | Dollar exact | Median exact |
|---|---|---|---|
| **1–5** | 717,322 | **98.04%** | 95.38% |
| 6–10 | 133,440 | 99.31% | 97.77% |
| 11–50 | 300,456 | 99.65% | 98.56% |
| 50+ | 258,548 | 99.90% | 99.52% |

At one to five lines per cell — thinner than the deployment median of six — the lookup is still
**98.04%** dollar-exact. Accuracy declines with thinness, by two points across the whole range.
The result transfers.

## 9. Step 5 — Assign the dollars

For a matched line:

```
QPA                = the block's QPA dollar
Provider offer     = the block's provider offer, or Provider % of QPA x QPA
Plan offer         = the block's plan offer, or Plan % of QPA x QPA
Prevailing offer   = the winning side's offer
```

The last is exact by identity: the prevailing offer equals the selected party's offer on
**100.000%** of all 4,898,336 fingerprintable lines.

## 10. Result

| Outcome | OON lines | Share |
|---|---|---|
| **Dollars assigned** | **4,979,123** | **60.5%** |
| No `QPA as Percent of Median QPA` published | 2,576,139 | 31.3% |
| Unresolved | 678,641 | 8.2% |

The 31.3% is a wall, not a shortfall: CMS suppresses the ratio on those lines, so there is nothing
to anchor a dollar to. **Of the 5,657,764 lines that do carry the ratio, we price 88.0%.**

Why the 678,641 fail:

| Reason | Lines |
|---|---|
| No match on any field set | 341,642 |
| Cell lookup candidates too far apart to choose | 249,821 |
| Block spans two or more different medians | 87,178 |

**308,988 of the 678,641 — 46% — carry a published ratio of exactly 1.00.** That means the line
*is* its cell's median, and every cell contains such a line, so the value discriminates nothing.
It is the single largest driver of failure.

## 11. Every assigned line audits itself

The output carries `QPA ($)` and `Median QPA ($)` separately, so the arithmetic can be checked
against CMS's own published figure on every row:

```
round( QPA / Median QPA , 2 )  ==  QPA as Percent of Median QPA   ?
```

Example B: 78.49 / 79.87 = 0.9827 → **0.98**, matching the published value.

| | Lines |
|---|---|
| Reconciles | 4,967,163 |
| **Does not reconcile — flagged, exclude** | **11,360** |

**99.76% of assigned lines reproduce CMS's published ratio from the dollars we assigned.** The
11,360 that do not are labelled in the data, not silently kept.

## 12. What is not claimed

1. **Price statistics, not outcome statistics.** 94% of assigned dollars come from the fingerprint,
   which requires both offers and so excludes nearly every default. Win and default rates must be
   computed on the full OON sheet, filtering on `Default Decision`.
2. **A block match identifies the dollars, not the dispute.** 35% of assigned lines resolve to one
   specific Dispute Number. The rest give the dollars and the payer, not the row.
3. **Two tiers carry a stated tolerance** — `Cell lookup (within 2%)` and `Derived from median
   ratio` — 148,471 lines, 3.0% of assignments. Filter on the source field when precision matters.
4. **Service Code Modifiers are not usable**, being populated on 0.9% of lines.
5. **Air ambulance is out of scope.**
