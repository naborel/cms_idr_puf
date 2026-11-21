# Why Dallas lines don't reach a 1:1 match — diagnostic run

Scope: `Dallas-Fort Worth-Arlington, TX`, all twelve quarters, **662,306** QPA lines.

---

## 1. Where the lines go

| Reason a line cannot be fingerprinted | Lines | % of region |
|---|---|---|
| QPA dollar not published | 134,675 | 20.3% |
| Provider offer not published | 11,877 | 1.8% |
| Plan offer not published | 8,075 | 1.2% |
| Prevailing offer not published | 0 | 0.0% |
| Default, or default flag missing | 3,249 | 0.5% |
| **Fingerprintable** | **504,430** | **76.2%** |

Of the 504,430 fingerprintable lines:

| Outcome | Lines | % of fingerprintable |
|---|---|---|
| Strict 1:1 | 269,398 | 53.4% |
| Balanced block — N QPA lines ↔ exactly N OON lines | 231,849 | 46.0% |
| Unbalanced group | 2,397 | 0.5% |
| **No OON candidate at all** | **786** | **0.2%** |

---

## 2. Two defects found and fixed

**`Place of Service Code` is stored as a decimal in the 2023 Q2 QPA sheet.** 59,532 lines carry
`"23.0"`, `"22.0"`, `"0.0"` where the OON sheet carries `"23"`, `"22"`, `"00"`. These could never
match. Fix: strip a trailing `.0` and zero-pad to two characters, both sides. 277 OON lines carry
the mirror defect on `Service Code`.

**`Dispute Line Item Type` is absent from the QPA sheet in 2023 Q1–Q2.** Matching a null against
a populated value fails. Fix: treat a missing value as a wildcard rather than a literal.

| | Before | After |
|---|---|---|
| Unmatched Dallas lines | 2,822 | **786** |
| Strict 1:1 | 268,293 | **269,398** |

A 72% reduction in unmatched lines. Both fixes are general, not Dallas-specific.

---

## 3. A 1:many match is usually a closed block

**99.0% of group cases have exactly as many QPA lines as OON candidates.** The block is closed:
those N QPA lines are those N OON lines, in some order. Nothing leaks in or out.

Inside a balanced block:

| | |
|---|---|
| Lines whose block has one identical QPA dollar | **93.0%** |
| Median dollar spread within a block | **$0.00** |
| 95th-percentile spread | **$0.01** |
| Lines whose block has a single carrier | **91.0%** |

So a block delivers the dollar amounts with certainty and the carrier with near-certainty. The
only thing unavailable is *which* `Dispute Number` a given line is. Where a block spans several
carriers, the multiset of carriers is known exactly, so carrier-level aggregates over the block
are exact rather than estimated.

**Usable coverage, Dallas:**

| | Lines | % of region |
|---|---|---|
| Dollars + the specific dispute identified | 269,398 | 40.7% |
| Dollars + carrier certain | 481,682 | **72.7%** |
| Dollars usable with exact carrier allocation | 502,682 | **75.9%** |

---

## 4. The remaining 786 are a hard floor

**Every one of the 786 sits in a quarter × service-code cell that contains OON lines whose ratio
columns are suppressed.** The counterpart exists in the OON sheet; CMS redacted the exact fields
the fingerprint is built from. There is nothing left to match on.

Across all twelve quarters CMS suppresses the ratio columns on **1,053,248** non-default OON
lines, so this is the expected residual, not a logic gap.

Relaxation testing confirms no further rule recovers them. Loosening the ratios by ±0.01 to absorb
rounding recovers 43 lines. Everything beyond that requires dropping a key field, which destroys
the specificity that makes the match meaningful.

Where they concentrate:

| Quarter | Lines |
|---|---|
| 2024 Q2 | 425 |
| 2023 Q4 | 172 |
| 2023 Q1 | 145 |
| all others | 44 |

By service code: 99284 (151), then revenue-style codes 812, 790, 952, 811, 142 and air ambulance
A0436, A0431 — low-volume lines, which is exactly what CMS suppresses.

---

## 5. Files

| File | Contents |
|---|---|
| `dallas_non_1to1_lines.csv` | all 235,032 fingerprintable Dallas lines that are not strict 1:1, with candidate counts, distinct carrier count and outcome label |
| `dallas_unmatched_786.csv` | the 786 with no OON candidate, with every field used in the match |
