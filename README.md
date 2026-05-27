# CMS Federal IDR Public Use File (PUF) — Analysis Toolkit

This repository contains aggregated parquet data and Python utilities for analyzing the **Federal Independent Dispute Resolution (IDR) Public Use Files** published by CMS, covering Q1 2022 through Q2 2025.

---

## Repository Structure

```
cms_idr_puf/
├── parquet/                        # Aggregated data files (all quarters combined)
│   ├── oon_all_quarters.parquet    # OON Emergency & Non-Emergency disputes (large, via Git LFS)
│   ├── qpa_all_quarters.parquet    # QPA and Offers
│   ├── air_all_quarters.parquet    # OON Air Ambulance disputes
│   ├── supp_summary_disputes_initiated.parquet
│   ├── supp_provider_size.parquet
│   ├── supp_plan_type.parquet
│   ├── supp_closure_reasons.parquet
│   ├── supp_eligibility.parquet
│   ├── supp_initiations_by_state.parquet
│   ├── supp_top_initiating_parties.parquet
│   ├── supp_top_noninitiating_parties.parquet
│   ├── supp_payment_determination_outcomes.parquet
│   ├── supp_qpa_by_cost_band.parquet
│   └── supp_qpa_by_specialty.parquet
│
├── load_parquet.py                 # Loader: reads all parquet files into named dataframes
├── idr_mappings.py                 # Domain mappings: standardizes provider & carrier names
└── Untitled1.ipynb                 # Exploratory analysis notebook
```

---

## Data

The parquet files are aggregations of the raw CMS IDR PUF quarterly releases. There are three **PUF** files and eleven **supplemental** table files:

### PUF Files
| Dataframe | Description |
|-----------|-------------|
| `oon` | OON Emergency & Non-Emergency disputes (all quarters) |
| `qpa` | QPA and Offers (all quarters) |
| `air` | OON Air Ambulance disputes (all quarters) |

### Supplemental Tables
| Dataframe | CMS Table | Description |
|-----------|-----------|-------------|
| `supp_disputes_initiated` | Table 1 | Disputes initiated by type |
| `supp_provider_size` | Table 2 | Disputes by provider size |
| `supp_plan_type` | Table 3 | Disputes by health plan type |
| `supp_closure_reasons` | Table 4 | Closure reasons |
| `supp_eligibility` | Table 5 | Eligibility determinations |
| `supp_state` | Table 7 | Initiations by state |
| `supp_top_initiating` | Table 8 | Top 10 initiating parties |
| `supp_top_noninitiating` | Table 9 | Top 10 non-initiating parties |
| `supp_outcomes` | Table 12 | Payment determination outcomes |
| `supp_cost_band` | Table 13 | Prevailing offer vs QPA by cost band |
| `supp_specialty` | Table 14 | Prevailing offer vs QPA by specialty |

> **Note:** `oon_all_quarters.parquet` (~190MB) is stored via [Git LFS](https://git-lfs.github.com). Make sure Git LFS is installed before cloning.

---

## Usage

### Loading data

```python
from load_parquet import load_all

# Load supplemental tables only (fast)
(oon, qpa, air, supp_disputes_initiated, supp_provider_size,
 supp_plan_type, supp_closure_reasons, supp_eligibility, supp_state,
 supp_top_initiating, supp_top_noninitiating, supp_outcomes,
 supp_cost_band, supp_specialty) = load_all(include_puf=False)

# Load everything including PUF files
(...) = load_all(include_puf=True)
```

### Applying domain mappings

`idr_mappings.py` maps provider and carrier email domains to standardized group names and categories:

```python
from idr_mappings import apply_provider_map, apply_carrier_map, add_outcome_bucket

oon = apply_provider_map(oon)   # adds Provider_Group, Provider_Category
oon = apply_carrier_map(oon)    # adds Carrier_Group, Anthem_Flag
oon = add_outcome_bucket(oon)   # adds Outcome_Bucket
```

**Provider categories:**
- `PE-Backed National` — national physician staffing groups backed by private equity
- `Physician-Owned Group` — large national groups that are physician-owned, no PE
- `Billing/Revenue Cycle` — RCM, billing, coding, or IDR filing companies
- `Law Firm` — law firms filing IDR disputes on behalf of providers
- `Hospital System` — health system entities
- `Specialty Group` — clinical specialty practices (anesthesia, radiology, neuromonitoring)
- `Unknown` — unmapped domain

**Outcome buckets** (from `add_outcome_bucket`):
- `Contested Provider Win` / `Contested Plan Win`
- `Default Provider Win` / `Default Plan Win`
- `Other / Split`

---

## Requirements

```
pandas
numpy
pyarrow  # or fastparquet
```

---

## Data Source

Raw quarterly PUF files published by CMS:
[https://www.cms.gov/nosurprises/policies-and-resources/reports](https://www.cms.gov/nosurprises/policies-and-resources/reports)
