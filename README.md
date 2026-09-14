# CMS Federal IDR Public Use Files — Processed Parquets

This repo contains processed parquet files built from the CMS Federal Independent Dispute Resolution (IDR) Public Use Files, covering Q1 2023 through Q4 2025.

The No Surprises Act established a federal arbitration process for out-of-network payment disputes between providers and health plans. CMS publishes quarterly data files on every dispute that went through that process.

---

## What's in here

| File | Rows | Description |
|------|------|-------------|
| `parquet/oon_all_quarters.parquet` | 8,233,903 | OON Emergency & Non-Emergency dispute line items |
| `parquet/qpa_all_quarters.parquet` | 8,338,286 | QPA and dollar-level offer amounts |
| `parquet/air_all_quarters.parquet` | 104,383 | OON Air Ambulance disputes |
| `parquet/supp_*.parquet` | — | 11 aggregated CMS summary tables — currently through Q2 2025; see [ADDING_A_QUARTER.md](ADDING_A_QUARTER.md) |
| `carrier_map/carrier_crosswalk.parquet` | 30,168 | `(plan name, email domain)` → carrier, parent, type, submitter |
| `carrier_map/provider_filer_crosswalk.parquet` | 849 | provider email domain → filer, business model |

The three main PUF files cover all 12 quarters concatenated into single tables. The supplemental files each cover a specific CMS-published summary table across all quarters.

Scripts:
- `build_parquets.py` — rebuilds the three PUF parquets from scratch from raw CMS xlsx/csv files (full historical rebuild)
- `rebuild_all.py` — the same rebuild, checkpointed per batch so it can be stopped and resumed; use this for the full 12-quarter run
- `publish_parquets.py` — verifies a rebuild against what is published, recompresses to ZSTD, and writes into `parquet/` (see [PUSH.md](PUSH.md))
- `carrier_map/apply_map.py` — regenerates the carrier and provider crosswalks from the parquets
- `build_supplemental.py` — rebuilds the supplemental parquets from the CMS supplemental xlsx files
- `load_parquet.py` — convenience loader that reads all parquets into named dataframes
- `idr_mappings.py` — provider and carrier domain maps (see below)
- `puf_checker.py` / `puf_transform.py` / `puf_merge.py` — incremental pipeline for adding a newly-released quarter without a full rebuild; see [ADDING_A_QUARTER.md](ADDING_A_QUARTER.md)

---

## Rebuild history

These parquets were rebuilt from the raw CMS files after two parsing defects were found in the
earlier build. If you are holding a copy from before that rebuild, replace it.

**1. Percent-formatted text silently dropped (2024Q3–2024Q4).** The offer-as-%-of-QPA columns
arrive in some quarters as text with a trailing percent sign (`'1,014%'`). `pd.to_numeric`
coerced those to `NaN` without error, emptying the columns for two quarters — about 1.6M line
items. The parser now decides per *value* rather than per column, and divides by 100 only where
a `%` was actually present. That second half matters: the raw file stores `445%` where the
parquet stores `4.45`, so stripping the sign without rescaling would have introduced a silent
100× error, which is worse than the null it replaced.

**2. A categorical column destroyed by substring matching.** `QPA_NUMERIC_PATTERNS` contained
`'Offer'`, which matched the *categorical* column `Offer Selected from Provider or Issuer` in the
QPA file and coerced it to numeric — blanking it for every quarter before 2025Q3. A code comment
had recorded this as "CMS always left it empty." It was not empty; the pipeline emptied it.

The rebuild is row-count exact against all 12 raw quarters and regression-free on the ten
quarters that were unaffected. `build_parquets.py` now prints a per-quarter parse report and
raises if any quarter parses zero values for a column it expects to populate.

## Outcome resolution

`Offer Selected from Provider or Issuer` is the actual per-line result and is preferred
wherever it exists, but it is blank on 354,245 lines (4.3%), spread evenly across all twelve
quarters — a real gap in the source, not a parsing failure. On 354,130 of those the
dispute-level `Payment Determination Outcome` *is* populated, so the outcome falls back to it
and only **115 lines** end up unclassifiable. The fallback is dispute-level, so on a batched
dispute it reports the dispute's overall result rather than that specific line's; that is why it
is a fallback and not the primary.

## Carrier and provider crosswalks

`carrier_map/` replaces the old email-domain-as-identity approach. The domain alone is not
trustworthy, and the file proves it: `multiplan.com` is 64% Cigna but also carries Kaiser and
Horizon; `clearhs.com` is 78% UMR **and** Meritain — UnitedHealthcare and Aetna under one
domain; `bcbsil.com` is 55% Blue Cross plans of *Texas and Oklahoma*, because HCSC runs five
plans off shared infrastructure.

So there are two independent fields:

- **`carrier_group`** — the payer whose money is at stake, resolved from the plan name and
  falling back to the domain only where a single plan owns it. **This is the field to filter on.**
  99.06% resolved, collapsing 1,715 bare domains to 127 named carriers.
- **`submitter_group`** — who actually handled the dispute, from the domain. Repricing vendors
  file under their own domain on behalf of many payers.

Correcting for this moves real numbers: Cigna's dispute volume was understated by 2.3×
(481,206 → 1,100,865 lines) and BCBS Illinois overstated 11× by Texas and Oklahoma disputes.

On the provider side the crosswalk names the **filer** rather than the practice, because that is
the closed set — `halomd.com` files under 725 distinct NPIs, `mdcapitaladvisors.com` under 1,215.
99.26% resolved across 135 domains.

See `carrier_map/README.md` for the full method, the join keys, and the honest edges.

## What we did to the raw files

The raw CMS files aren't simply appendable. Here's what was cleaned up and added:

### Column name alignment
CMS changed a column naming convention in Q3 2023: columns previously named `"... as Percent of QPA"` became `"... as % of QPA"`. We standardized all quarters to the newer `% of QPA` form so the files concatenate cleanly.

### Suppression markers → null
CMS suppresses low-count cells with `"NR"` or `"N/R"`. We replaced these with null values so they don't interfere with numeric operations.

### Service code columns forced to string
Columns like `Service Code`, `Place of Service Code`, and `Type of Service Code` are stored as integers in some quarters and strings in others (e.g., `99213` vs `"99213"`). We force these to string across all quarters to prevent type conflicts on concat.

### Currency stripping
Dollar-formatted columns (`IDRE Compensation`, `QPA`, provider/plan offer amounts) sometimes come through as strings like `"$1,250.00"`. We strip the `$` and commas before converting to float.

### Mixed-type cleanup after concat
After concatenating 10 quarters, some columns end up as object dtype due to mixed int/str across quarters. We apply a pass after concat that converts any column that is >90% parseable as numeric.

### Outcome bucket labels
The raw files have a `Payment Determination Outcome` column and a separate `Default Decision` flag, but no single column that cleanly classifies what happened in a dispute. We added an `Outcome_Bucket` column with five mutually exclusive categories:

- `Contested Provider Win` — arbitrator chose provider's offer, no default
- `Contested Plan Win` — arbitrator chose plan's offer, no default
- `Default Provider Win` — provider won but the plan defaulted (didn't participate)
- `Default Plan Win` — plan won but the provider defaulted
- `Other / Split` — everything else (split decisions, withdrawn, etc.)

### Provider and carrier name standardization
Provider and carrier identities in the raw files are email domains (e.g., `teamhealth.com`, `uhc.com`), not names. We added three columns:

- `Provider_Group` — standardized group name (e.g., `"TeamHealth"`)
- `Provider_Category` — one of: `PE-Backed National`, `Physician-Owned Group`, `Billing/Revenue Cycle`, `Law Firm`, `Hospital System`, `Specialty Group`, or `Unknown`
- `Carrier_Group` — standardized carrier name (e.g., `"UnitedHealthcare"`, `"Aetna"`)
- `Anthem_Flag` — `"Anthem"` if the domain matches any Anthem/Elevance-affiliated pattern, else `"Other"` (catches subsidiaries and regional brands not in the main carrier map)

The full domain-to-name mappings are in `idr_mappings.py`.

### File format changes across years
2023 and 2024 data came as xlsx files (one file per quarter, multiple sheets). Starting in 2025, CMS switched to CSV. Additionally, the 2025 Q1 OON file was split into 2 chunks and the 2025 Q2 OON file into 3 chunks. The build script handles all of this transparently.

Starting 2025 Q3, CMS introduced two new suppression markers (`^` and `+`/`*`) alongside the original `NR`/`N/R`, and added several new columns (`Certified IDR Entity`, `Date of Initiation`, `Service Code Modifier(s)`, and on QPA also `Cost-Sharing Amount`, `Initial Payment Amount`, `Year of Service`). See [ADDING_A_QUARTER.md](ADDING_A_QUARTER.md) for how new quarters like this get validated and merged in.

### Supplemental tables
The CMS supplemental xlsx files are human-formatted Excel workbooks with stacked summary tables, not raw tabular data. We parse each named table out of the workbook by detecting its title row, extract the relevant rows, and normalize numeric columns. CMS also added a `Church Plan` column to Table 9 starting in 2025 Q1; earlier quarters have that column as null.

---

## Data source

CMS Federal IDR Public Use Files: https://www.cms.gov/healthplan-price-transparency/resources/independent-dispute-resolution-data

Raw files are not included in this repo due to size.
