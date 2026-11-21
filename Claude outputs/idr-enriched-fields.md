# Enriched IDR parquets — field reference

`enrich_puf.py` reads `oon_all_quarters.parquet` and `qpa_all_quarters.parquet` and writes
enriched copies. Every original column is preserved; the fields below are appended. Row counts
are asserted against the sources on every run.

```
py3 enrich_puf.py --src <parquet folder> --out <output folder>
```

---

## OON file — new fields

| Field | Meaning |
|---|---|
| `Geographical Region (linked)` | The MSA the line belongs to. The OON sheet publishes only a state; this is recovered through the match. |
| `Median QPA ($)` | CMS's benchmark for the line's cell — service code × quarter × region, within the quarterly release. |
| `QPA ($)` | The line's actual Qualifying Payment Amount. |
| `Provider/Facility Offer ($)` | Actual provider offer. |
| `Health Plan/Issuer Offer ($)` | Actual plan offer. |
| `Prevailing Offer ($)` | Actual awarded amount. |
| `QPA vs Median QPA ($)` | `QPA − Median QPA`. How far above or below benchmark this line was priced. |
| `Award over QPA ($)` | `Prevailing Offer − QPA`. Dollar exposure above the benchmark. |
| `QPA Source` | How the dollar was obtained — see below. |
| `Match Method` | Which path produced the match. |
| `Match Type` | `Exact 1:1`, `Fingerprint group`, or `Cell lookup`. |
| `Match Diagnostic` | **The exact field list used**, or the exact reason no assignment was made. |
| `QPA Lines in Match` | How many QPA-sheet lines share this fingerprint. |
| `OON Lines in Match` | How many OON lines share it. |
| `Regions in Match` | Distinct regions in the matched group. `1` means the median is unambiguous. |
| `Candidate Dollars in Cell` | For the cell-lookup path, how many distinct dollars were possible. |
| `QPA Lines in Cell` | Volume behind the cell, for weighting judgement. |
| `Dollar Status` | `Assigned`, `Unresolved`, or `No published median ratio`. |

### Coverage, all 8,233,903 OON lines

| `Dollar Status` | Lines | % |
|---|---|---|
| **Assigned** | **4,971,040** | **60.4%** |
| No published median ratio | 2,576,139 | 31.3% |
| Unresolved | 686,724 | 8.3% |

The 31.3% is a hard floor: CMS suppresses `QPA as Percent of Median QPA` on those lines, so there
is nothing to anchor a dollar to. **Of the 5,657,764 lines that do carry the ratio, 87.9% get
dollars.**

### `QPA Source`

| Value | Lines | Of which defaults | Precision |
|---|---|---|---|
| `Matched line (exact)` | 4,689,095 | 25,393 | Exact — the dollar is read off the matched QPA line |
| `Cell lookup (exact)` | 141,557 | 91,813 | Exact — only one dollar in the cell produces this ratio |
| `Cell lookup (within 2%)` | 72,770 | 32,050 | Candidate dollars differ by ≤2%; the highest-volume one is used |
| `Derived from median ratio (within 1%)` | 67,618 | 392 | `QPA % of Median × Median QPA`; 97.0% land within 1% of truth, median error 0.15% |

**149,648 defaulted lines now carry dollars** — previously impossible, because the fingerprint
needs both offers and a default has none. The cell-lookup path needs only the published ratio.

### `Match Method` and `Match Diagnostic`

| `Match Method` | Lines | `Match Diagnostic` reads |
|---|---|---|
| Fingerprint, full | 4,059,053 | Quarter + Service Code + Place of Service Code + Offer Selected + Dispute Line Item Type + Initiating Party + Certified IDR Entity + Provider Offer % + Plan Offer % + Prevailing Offer % + QPA % of Median |
| Fingerprint, no party/IDRE | 425,973 | the same, without Initiating Party and Certified IDR Entity |
| Fingerprint, ratios only | 90,225 | the same, without Dispute Line Item Type (the QPA sheet lacks it in 2023 Q1–Q2) |
| Cell lookup | 739,176 | Quarter + Service Code + Location of Service + QPA % of Median |
| Fingerprint, region ambiguous | 1,695 | group spans several regions, so no median is assigned |

Where nothing is assigned, `Match Diagnostic` says which wall was hit — *"QPA as Percent of Median
QPA not published"*, *"spans N regions - median not determinable"*, *"found N candidate dollars too
far apart to choose"*, or *"No match on any field set"*.

---

## QPA file — new fields

| Field | Meaning |
|---|---|
| `Median QPA ($)` | The benchmark for this line's cell. |
| `QPA as Percent of Median QPA (calculated)` | Reproduces the OON sheet's published field. |
| `Provider/Facility Offer as % of QPA (calculated)` | Reproduces the OON equivalent. |
| `Health Plan/Issuer Offer as % of QPA (calculated)` | Reproduces the OON equivalent. |
| `Prevailing Party Offer as % of QPA (calculated)` | Reproduces the OON equivalent. |
| `QPA vs Median QPA ($)` · `Award over QPA ($)` | Same definitions as the OON side. |
| `Service Code (normalized)` · `Place of Service Code (normalized)` | Decimal artifacts stripped, place of service zero-padded to two characters. Required for any join — the 2023 Q2 sheet stores place of service as a number. |
| `Fingerprint` | Pipe-delimited match key. Joins straight to the OON side with no rebuild. |
| `Lines in Median Cell` | Volume behind the median. |
| `Metric Status` | `Complete`, `No median (region not published)`, or `No QPA dollar published`. |

| `Metric Status` | Lines | % |
|---|---|---|
| Complete | 5,244,882 | 62.9% |
| No median (region not published) | 2,372,899 | 28.5% |
| No QPA dollar published | 720,505 | 8.6% |

4,900,684 lines carry a `Fingerprint`.

---

## How the median is assigned, and why it needs a match

CMS computes the median QPA per **service code × quarter × geographical region**. The OON sheet
publishes only a state. A state cannot stand in for a region: across the twelve quarters, **78% of
lines sit in a (quarter, code, state) cell whose candidate region medians span more than 10%** —
Texas alone carries Houston, Dallas, Austin, San Antonio and Longview at materially different
levels. So the region, and therefore the median, has to come from a row-level match.

Two paths do that:

**Fingerprint.** Match the OON line to a QPA line on the ratio fields plus quarter, service code,
place of service, which offer prevailed, line-item type, initiating party and IDR entity. Precise,
but it requires both offers, so it cannot reach defaults.

**Cell lookup.** For a given quarter, service code and state, enumerate every QPA dollar that
would produce the line's published `QPA as Percent of Median QPA`. Where exactly one dollar
qualifies, the cell and the dollar are both determined. Validated against 1,381,495 lines whose
true dollar was already known: **98.8% exact.** This path needs only the ratio, which is why it
reaches defaults and lines with a missing offer.

---

## Cautions

1. **Outcome statistics belong to the unenriched OON file.** Lines whose dollars come from the
   fingerprint are contested by construction, so win and default rates computed on the assigned
   subset are not representative. `Default Decision` is preserved — filter on it explicitly.
2. **A median of ratios is not the ratio of medians.** `median(offer ÷ QPA)` and
   `median(offer) ÷ median(QPA)` differ, sometimes materially. Report the ratio you actually
   computed.
3. **Normalize before joining.** Use the normalized service code and place of service columns.
   Raw `Place of Service Code` reads `"23.0"` in the 2023 Q2 QPA sheet and `"23"` in the OON sheet.
4. **`(Dispute Number, DLI Number)` is not unique** — 8,433 pairs repeat across rows with different
   service codes. Never use it as a join key.
5. **Lines assigned `Cell lookup (within 2%)` or `Derived from median ratio` carry a known error
   band.** Filter on `QPA Source` when precision matters.
6. Air ambulance is not enriched.
