# Mapping dollar amounts to the Federal IDR OON Public Use File

A method note. The federal IDR PUF splits each dispute across two sheets and gives them no
common key. This document defines the link we use to attach real dollar amounts to individual
dispute lines, the validation behind it, its coverage, and the rules for using it.

---

## 1. Two sheets, one population, deliberately separated

| Sheet | Rows |
|---|---|
| QPA and Offers | 8,338,286 |
| OON Emergency and Non-Emergency | 8,233,903 |
| OON Air Ambulance | 104,383 |
| OON + Air | **8,338,286** |

The QPA sheet is the union of the two dispute sheets, quarter by quarter. **Every line in the QPA
sheet is the same dispute line as exactly one line in the OON sheet.** CMS simply decides which
facts appear on which sheet.

| | OON sheet | QPA sheet |
|---|---|---|
| Identifiers | Dispute Number, DLI Number | none |
| Provider and plan detail | name, email domain, NPI, practice size | none |
| IDR entity and outcome | certified IDR entity, determination outcome, days to decide | none |
| Service code, place of service, quarter, line-item type, initiating party, default flag | Both | Both |
| Geography | state | region (MSA) |
| QPA and offers | as a percent of QPA | **actual dollars** |

**Every dollar figure sits on the sheet with no identifiers.** The OON sheet names the carrier,
the provider, the IDR entity and the outcome, but expresses every amount as a ratio. The QPA
sheet holds the actual QPA and the actual offers, and names nobody.

So the obvious analysis — what did the plan offer, what did the provider ask, what was awarded,
and by whom — is not available in either sheet alone. Nor can it be reached by tying claim data
to dispute numbers, because the dispute numbers live on the sheet without dollars.

---

## 2. One field ties the sheets together

The OON sheet publishes one field that CMS intends as context, and that works as a key:

> **`QPA as Percent of Median QPA`**

It is the line's QPA divided by the median QPA of its peer group. Because the denominator is
computed across thousands of other lines, the ratio lands on a value that very few lines share —
far fewer than any service, geography or outcome field narrows to. Reconstruct the denominator and
the field becomes a fingerprint that identifies individual lines across both sheets.

**We have determined how CMS computes that benchmark and validated it.** Combined with the three
offer ratios, it links the QPA sheet's dollars to the OON sheet's named parties and outcomes at
the line level.

---

## 3. The benchmark, and proof that we have it right

**CMS computes the median QPA over Service Code × Quarter × Geographical Region, within each
standalone quarterly release.**

To test this without circular reasoning, we linked the two sheets using **only the three offer
ratios**, deliberately excluding `QPA as Percent of Median QPA`, and kept only lines resolving to
exactly one candidate on each side. That produces **1,272,099 confirmed line pairs in which the
median played no part in the link.** On each pair we computed the median ourselves and compared
our value to CMS's published one.

**1,270,800 of 1,272,099 pairs match exactly — 99.90%.**

| Quarter | Confirmed pairs | Match rate |
|---|---|---|
| 2023 Q1 | 5,201 | 97.92% |
| 2023 Q2 | 1,463 | 100.00% |
| 2023 Q3 | 8,769 | 99.33% |
| 2023 Q4 | 12,541 | 99.00% |
| 2024 Q1 | 27,709 | 99.24% |
| 2024 Q2 | 60,786 | 98.75% |
| 2024 Q3 | 91,009 | 99.98% |
| 2024 Q4 | 122,575 | 99.98% |
| 2025 Q1 | 151,426 | **100.00%** |
| 2025 Q2 | 225,757 | **100.00%** |
| 2025 Q3 | 268,563 | **100.00%** |
| 2025 Q4 | 296,300 | **100.00%** |
| **All** | **1,272,099** | **99.90%** |

Every quarter clears 98%, and each of the last four reproduces exactly.

---

## 4. What the QPA sheet then yields

| Metric | Definition | Why it matters |
|---|---|---|
| Benchmark price | Median QPA by service code, quarter and region | The reference every offer is measured against |
| Provider ask | Provider offer ÷ QPA | How far above the benchmark providers price their claims |
| Plan offer multiple | Plan offer ÷ QPA | Whether the plan anchored its offer at the QPA |
| Offer spread | Provider offer ÷ plan offer | The size of the gap the arbitrator had to split |
| Award | Prevailing offer, in dollars | What was actually paid |
| Award over QPA | Prevailing offer − QPA, in dollars | Dollar exposure above the benchmark price |
| Anchoring rate | Share of plan offers at 1.00× QPA | Whether the carrier made a real offer or restated the QPA |

Linked to the OON sheet, every one of these resolves to a named carrier, a named provider, a
named IDR entity and a known outcome.

---

## 5. Eligibility — Dallas-Fort Worth-Arlington, TX

A line is usable when it carries a QPA, both offers and a prevailing offer, and is not a default.
Defaults are excluded because the plan never made an offer, so the award followed by rule rather
than by comparison.

| Step | Lines | Lost | % of region |
|---|---|---|---|
| All QPA lines in region | 662,306 | — | 100.0% |
| QPA present | 527,631 | −134,675 | 79.7% |
| Provider offer present | 515,754 | −11,877 | 77.9% |
| Plan offer present | 507,679 | −8,075 | 76.7% |
| Prevailing offer present | 507,679 | 0 | 76.7% |
| Not a default | **504,430** | −3,249 | **76.2%** |

---

## 6. A single line, carried across

QPA sheet — Dallas-Fort Worth-Arlington TX, 2025 Q4, service code 99284, place of service 23,
batched, award in favor of the provider:

| Field | Value in the QPA sheet | How it appears in the OON sheet |
|---|---|---|
| QPA | $897.59 | not published |
| Provider/Facility Offer | $5,037.38 | `Provider/Facility Offer as % of QPA` = **5.61** |
| Health Plan/Issuer Offer | $1,008.93 | `Health Plan/Issuer Offer as % of QPA` = **1.12** |
| Prevailing Offer | $5,037.38 | `Prevailing Party Offer as % of QPA` = **5.61** |
| Median QPA — 99284, 2025 Q4, Dallas, 16,754 lines | $252.55 | `QPA as Percent of Median QPA` = **3.55** |

Applying those values against the OON sheet:

| Constraint | OON lines remaining |
|---|---|
| All OON + Air lines with published ratios, non-default | 5,361,410 |
| `Quarter` = 2025Q4 | 1,007,497 |
| `Service Code` = 99284 | 184,113 |
| `Place of Service Code` = 23 | 182,280 |
| `Dispute Line Item Type` = Batched | 96,611 |
| `Offer Selected from Provider or Issuer` = In Favor of Provider/Facility | 81,610 |
| `QPA as Percent of Median QPA` = 3.55 | **53** |
| `Health Plan/Issuer Offer as % of QPA` = 1.12 | **1** |

**DISP-4519006 / DLI-12775571** — Blue Cross and Blue Shield of Texas, initiated by a health care
facility, decided by Federal Hearings and Appeals Services, Inc.

One field does the work: the reconstructed median ratio cuts 81,610 candidates to 53. One offer
ratio finishes it.

The story that line now tells: BCBS Texas offered **1.12× the QPA** against a provider asking
**5.61×**, and the arbitrator awarded the provider **$5,037.38** on a benchmark price of **$252.55**.

---

## 7. Independent confirmation

Two fields appear in both sheets and are excluded from the link, so their agreement is a test of
it. Across 1,666,622 one-to-one line pairs nationwide:

| Held-out field | Pairs tested | Agreement |
|---|---|---|
| Initiating Party | 1,522,173 | **100.00%** |
| Certified IDR Entity | 745,413 | **100.00%** |

The IDR entity test is the demanding one — the most common entity accounts for 29.5% of lines, so
a mistaken link would disagree constantly. It never does.

---

## 8. Completeness

Dallas-Fort Worth-Arlington, TX, twelve quarters:

| | Lines | % of eligible | % of region |
|---|---|---|---|
| Eligible lines | 504,430 | 100.0% | 76.2% |
| Matched to the OON sheet | 501,687 | **99.5%** | 75.7% |
| Dollars and carrier both unambiguous | 427,476 | **84.7%** | 64.5% |
| Resolved to one specific dispute line | 268,293 | **53.2%** | 40.5% |

The middle row is the one that matters for analysis. Because the four ratio fields *are* the match
key, every candidate in a group carries identical published ratios by construction — group members
differ in who the dispute belonged to, not in what the numbers were. So a group match still
delivers the dollars; the only open question is attribution.

Measured across the 501,687 matched lines: the carrier is unique in **95.1%** of cases, and the
QPA dollar is identical across the matched key in **96.7%**. Where the QPA dollar does vary, the
spread is rounding rather than real dispersion — median **$0.09** (0.10%), 90th percentile $92.
Requiring both an unambiguous carrier and identical dollars leaves **427,476 lines, 84.7% of
eligible.**

Chicago-Naperville-Elgin, IL-IN-WI confirms the pattern: 70,604 eligible of 84,585, **98.4%**
matched, **81.6%** with dollars and carrier unambiguous, **32.2%** resolved to a single line.

**Of every 100 dispute lines in the Dallas region, we can attach real dollar amounts to 76, name
the carrier behind those dollars on 65, and identify the exact dispute on 41.**

---

## 9. Rules for use

1. **Price statistics from the linked set; outcome statistics from the full OON sheet.** The link
   requires both offers, which removes roughly 87% of defaults. BCBS Texas shows a 0.3% default
   rate on the linked set against ~37% unlinked.
2. **Separate repricing vendors from carriers.** Carriers offer at a median **1.02×** QPA with
   **67.5%** anchored at the QPA; MultiPlan/Claritev offers at **3.52×** with **11%** anchored.
   Pooling them lifts the median plan offer above QPA and erases the anchoring finding.
3. **Report medians, not means.** Offer ratios reach four significant figures at the tail.
4. **The eligible set over-represents higher-volume, less-batched lines**, since suppressed lines
   are the low-volume tail.
5. **Component lines are out of scope** — 11 exist across the entire OON sheet.
6. **Modifiers are not usable** — `Service Code Modifier(s)` is populated on 0.9% of lines, so
   assistant-surgeon, bilateral and PC/TC pricing cannot be distinguished.
7. **Column sets change between releases.** The QPA sheet gained `Dispute Line Item Type` after
   the earliest quarters. Verify columns on every refresh rather than inheriting the prior
   quarter's schema.
