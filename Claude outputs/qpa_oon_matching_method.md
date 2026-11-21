# Mapping dollar amounts to the Federal IDR OON Public Use File

A method note. The federal IDR PUF splits each dispute across two sheets and gives them no
common key. This document defines the link we use to attach real dollar amounts to individual
dispute lines, the validation behind it, its coverage, and the rules for using it.

---

## 1. The two sheets are one population

| Sheet | Rows |
|---|---|
| QPA and Offers | 8,338,286 |
| OON Emergency and Non-Emergency | 8,233,903 |
| OON Air Ambulance | 104,383 |
| OON + Air | **8,338,286** |

The QPA sheet is the union of the two dispute sheets, quarter by quarter. Every QPA row has
exactly one counterpart. The task is identifying which one.

---

## 2. What each sheet carries

The sheets are complementary, not overlapping. Neither is usable alone.

| | QPA sheet | OON sheet |
|---|---|---|
| Dollar amounts (QPA, both offers, prevailing) | **yes** | no |
| Ratio columns (offers as % of QPA, QPA as % of median QPA) | no | **yes** |
| Geography | `Geographical Region` — MSA / rest-of-state | `Location of Service` — state |
| Dispute and line-item IDs | no | **yes** |
| Provider and health plan names, NPI, email domain | no | **yes** |
| Certified IDR entity, determination outcome, time to decide | no | **yes** |
| Service code, place of service, quarter, line-item type, initiating party, default flag | yes | yes |

Three consequences govern everything downstream:

- **The dollars and the dispute identity never appear on the same row.** Attaching a QPA to a
  named carrier requires a derived link.
- **The two geography columns are different fields at different granularity.** They cannot be
  joined. A QPA row reads "Dallas-Fort Worth-Arlington, TX"; its counterpart reads "TX".
- **The region and the median-QPA ratio live in different sheets**, so CMS's published ratio
  cannot be checked against a recomputed one row by row without the link.

`Service Code Modifier(s)` is present in both sheets but populated on 78,819 of 8,338,286 rows
(0.9%), so modifier-driven pricing — assistant surgeon, bilateral, PC/TC splits — is not
observable.

---

## 3. Suppression: four markers, two independent rule sets

| Marker | Sheet | Meaning |
|---|---|---|
| `^` | QPA | Masks the row's entire pricing — QPA and all three offers together, never one alone |
| `+` | QPA | Masks the QPA **only**; the offers remain visible |
| `N/A` | both | Not applicable — no offer was made |
| `N/R` | OON | Not reported |

2024 Q1 column patterns (QPA, provider offer, plan offer, prevailing offer):

| Pattern | Rows |
|---|---|
| value, value, value, value | 126,343 |
| `^`, `^`, `^`, `^` | 25,693 |
| value, value, `N/A`, value | 15,327 |
| `+`, value, value, value | 11,611 |
| value, `N/A`, value, value | 4,526 |
| `+`, value, `N/A`, value | 3,903 |
| `+`, `N/A`, `N/A`, `N/A` | 3,554 |

`+` is the consequential one: CMS holds the QPA on those rows and declines to print it. The two
sheets apply their masks independently, so a dispute can have its dollar hidden on one sheet and
its ratio printed on the other. Section 8 quantifies that.

> Our parquet maps `^`, `+`, `N/A` and `N/R` all to null, which discards the reason a cell is
> blank. A per-column suppression-reason field on re-ingest would preserve it.

---

## 4. Median QPA: definition and validation

**CMS computes the median QPA over Service Code × Quarter × Geographical Region, within each
standalone quarterly release.**

The data dictionary names service code and region but not the time window. Quarter is required:
each PUF is generated fresh from one quarter's determinations.

This is validated on pairs linked **without** the median, so the test is independent of the field
it tests — 1,328,285 one-to-one pairs built from the offer ratios alone:

| Denominator | Pairs reproduced exactly |
|---|---|
| **Service Code × Quarter × Geographical Region** | **1,327,155 of 1,328,219 — 99.92%** |
| Service Code × Quarter (national) | 107,586 — 8.10% |

| Quarter | Pairs | Region median | National median |
|---|---|---|---|
| 2023 Q3 | 9,273 | 99.61% | 15.29% |
| 2023 Q4 | 12,674 | 99.98% | 20.12% |
| 2024 Q1 | 28,777 | 99.26% | 20.11% |
| 2024 Q2 | 63,887 | 98.79% | 15.32% |
| 2024 Q3 | 96,165 | 99.98% | 11.96% |
| 2024 Q4 | 129,181 | 99.99% | 8.20% |
| 2025 Q1 | 160,575 | **100.00%** | 8.48% |
| 2025 Q2 | 238,801 | **100.00%** | 6.50% |
| 2025 Q3 | 280,955 | **100.00%** | 6.54% |
| 2025 Q4 | 307,931 | **100.00%** | 6.00% |

Each of the last four quarters reproduces exactly. A region-free denominator fails on 92% of rows.

---

## 5. The link

Dollar amounts are converted to ratios, which makes values from the two sheets directly
comparable at two decimal places.

| Field | Derivation |
|---|---|
| `q`, `sc`, `pos` | Quarter, Service Code, Place of Service Code |
| `dd`, `dlit`, `sel` | Dispute Line Item Type, Type of Service Code, which offer prevailed |
| `pp` | Provider offer ÷ QPA |
| `hp` | Plan offer ÷ QPA |
| `vp` | Prevailing offer ÷ QPA |
| `qm` | QPA ÷ median QPA (§4) |

`qm` carries the most discriminating power: its denominator varies by code × quarter × region, so
it encodes geography that neither sheet shares.

A row is eligible when it carries a QPA, both offers, a prevailing offer, and is not a default.
Defaults are excluded because the plan made no offer and the award followed by rule rather than
by comparison.

Dallas-Fort Worth-Arlington, TX, twelve quarters:

| Step | Rows |
|---|---|
| All QPA rows in region | 662,575 |
| QPA present | 527,724 |
| Provider offer present | 515,844 |
| Plan offer present | 507,768 |
| Not a default | **504,519** |

---

## 6. Worked example

QPA sheet — Dallas-Fort Worth-Arlington TX, 2025 Q4, service code 99285, POS 23, bundled,
provider prevailed:

| Field | Value |
|---|---|
| QPA | $2,137.00 |
| Provider offer | $23,744.03 |
| Plan offer | $4,303.73 |
| Prevailing offer | $23,744.03 |
| Median QPA — 99285 × 2025 Q4 × Dallas, 7,063 lines | $365.45 |

Derived: `pp` 11.11 · `hp` 2.01 · `vp` 11.11 · `qm` 5.85

| Constraint | OON candidates |
|---|---|
| 2025 Q4 eligible pool | 996,692 |
| Service code 99285 | 102,212 |
| POS 23 | 101,279 |
| `qm` 5.85 | 3,612 |
| Bundled, professional, provider prevailed | 2,645 |
| `pp` 11.11 | 3 |
| `hp` 2.01 | **1** |

**DISP-4261883 / DLI-12028764** — BCBS of Texas, location of service TX. Its published ratios
read 11.11 / 2.01 / 5.85.

---

## 7. Validation and coverage

Two fields are published in both sheets and excluded from the link, so their agreement is an
independent test of it:

| Held-out field | Pairs tested | Agreement |
|---|---|---|
| Initiating Party | 106,471 | **100.0%** |
| Certified IDR Entity | 43,666 | **100.0%** |

The IDR entity test is the stronger of the two — the modal entity accounts for 38.6% of rows, so
chance agreement sits near 15–20%.

Where a fingerprint resolves to a small group rather than a single row, the group is a batched
submission priced identically. **95.4%** of multi-row groups carry one distinct QPA; **93.3%** of
those are a single carrier.

| | Dallas | Chicago |
|---|---|---|
| Region QPA rows | 662,575 | 84,596 |
| Matched to OON | 499,104 — **75.3%** | **82.7%** |
| Carrier attached | 450,732 — **68.0%** | **75.7%** |
| Strict one-to-one | 267,443 — **40.4%** | **26.8%** |

Of every 100 QPA lines in the Dallas region, 75 match a dispute line and 68 carry a named carrier.

---

## 8. The ratios that cannot be reproduced

**CMS prints a median-QPA ratio if and only if the row has a geographical region.** Across the
1,328,285 linked pairs, region and ratio co-occur with no exceptions: 1,328,219 have both, 66
have neither, zero have one without the other.

CMS nonetheless publishes 501,919 more ratios than there are rows printing both a region and a
QPA. Those are rows where **the region is printed and the QPA dollar is masked** by `^` or `+`.
CMS divides by the regional median, prints the ratio in the OON sheet, and withholds the dollar
in the QPA sheet.

| Quarter | Region + QPA printed | CMS ratios published | Region printed |
|---|---|---|---|
| 2023 Q1 | 42,232 | 50,896 | 55,495 |
| 2023 Q2 | 80,827 | 92,390 | 99,714 |
| 2023 Q3 | 51,818 | 63,410 | 68,004 |
| 2023 Q4 | 58,535 | 72,155 | 75,275 |
| 2024 Q1 | 131,450 | 151,572 | 167,065 |
| 2024 Q2 | 262,255 | 294,477 | 331,389 |
| 2024 Q3 | 430,033 | 472,259 | 548,658 |
| 2024 Q4 | 561,219 | 615,181 | 724,500 |
| 2025 Q1 | 684,801 | 748,186 | 847,009 |
| 2025 Q2 | 989,764 | 1,064,117 | 1,256,880 |
| 2025 Q3 | 980,833 | 1,058,795 | 1,218,590 |
| 2025 Q4 | 971,115 | 1,063,363 | 1,181,601 |
| **Total** | **5,244,882** | **5,746,801** | **6,574,180** |

Published counts sit inside the floor and ceiling in all twelve quarters. 2024 Q1 ties to the
workbook exactly: 131,450 rows print both; 35,615 print a region with the QPA masked (`^` 23,704,
`+` 11,911); CMS publishes a ratio for 20,122 of them.

This caps how many lines can be fingerprinted. It does not affect the ones that are.

---

## 9. Rules for use

1. **Price statistics from the linked set; outcome statistics from the full OON sheet.** The link
   requires both offers, which removes roughly 87% of defaults. BCBS of Texas shows a 0.3%
   default rate on the linked set against ~37% unlinked.
2. **Separate repricing vendors from carriers.** Carriers offer at a median **1.02×** QPA with
   **67.5%** anchored at the QPA; MultiPlan/Claritev offers at **3.52×** with **11%** anchored.
   Pooling them lifts the median plan offer above QPA and erases the anchoring finding.
3. **Report medians, not means.** Offer ratios reach four significant figures at the tail.
4. **The eligible set over-represents higher-volume, less-batched lines** — dropped rows are
   80.9% batched against 66.5% of those kept.
5. **Component lines are out of scope.** 351,762 eligible Component rows resolve to 9 one-to-one
   matches.
6. **2023 Q1–Q2 cannot be linked.** The QPA sheet did not yet carry `Dispute Line Item Type`.
   Column sets change between releases; verify them on every refresh rather than inheriting the
   prior quarter's schema.
