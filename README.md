# CMS Federal IDR Public Use Files — Processed Parquets

This repo contains processed parquet files built from the CMS Federal Independent Dispute Resolution (IDR) Public Use Files, covering Q1 2023 through Q2 2025.

The No Surprises Act established a federal arbitration process for out-of-network payment disputes between providers and health plans. CMS publishes quarterly data files on every dispute that went through that process.

---

## What's in here

| File | Description |
|------|-------------|
| `parquet/oon_all_quarters.parquet` | ~5.25M rows of OON Emergency & Non-Emergency disputes |
| `parquet/qpa_all_quarters.parquet` | ~5.33M rows of QPA and dollar-level offer amounts |
| `parquet/air_all_quarters.parquet` | ~77K rows of OON Air Ambulance disputes |
| `parquet/supp_*.parquet` | 11 aggregated summary tables (provider size, plan type, state, outcomes, etc.) |

The three main PUF files cover all 10 quarters concatenated into single tables. The supplemental files each cover a specific CMS-published summary table across all quarters.

Scripts:
- `build_parquets.py` — rebuilds the three PUF parquets from raw CMS xlsx/csv files
- `build_supplemental.py` — rebuilds the supplemental parquets from the CMS supplemental xlsx files
- `load_parquet.py` — convenience loader that reads all parquets into named dataframes
- `idr_mappings.py` — provider and carrier domain maps (see below)

---

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

### Supplemental tables
The CMS supplemental xlsx files are human-formatted Excel workbooks with stacked summary tables, not raw tabular data. We parse each named table out of the workbook by detecting its title row, extract the relevant rows, and normalize numeric columns. CMS also added a `Church Plan` column to Table 9 starting in 2025 Q1; earlier quarters have that column as null.

---

## Data source

CMS Federal IDR Public Use Files: https://www.cms.gov/healthplan-price-transparency/resources/independent-dispute-resolution-data

Raw files are not included in this repo due to size.
