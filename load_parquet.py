"""
IDR Parquet Loader
===================
Loads all IDR parquet files into named dataframes.

PUF dataframes:
  oon  -- OON Emergency & Non-Emergency (all quarters)
  qpa  -- QPA and Offers (all quarters)
  air  -- OON Air Ambulance (all quarters)

Supplemental dataframes:
  supp_disputes_initiated      -- Table 1  disputes initiated by type
  supp_provider_size           -- Table 2  disputes by provider size
  supp_plan_type               -- Table 3  disputes by health plan type
  supp_closure_reasons         -- Table 4  closure reasons
  supp_eligibility             -- Table 5  eligibility determinations
  supp_state                   -- Table 7  initiations by state
  supp_top_initiating          -- Table 8  top 10 initiating parties
  supp_top_noninitiating       -- Table 9  top 10 non-initiating parties
  supp_outcomes                -- Table 12 payment determination outcomes
  supp_cost_band               -- Table 13 prevailing offer vs QPA by cost band
  supp_specialty               -- Table 14 prevailing offer vs QPA by specialty
"""

import pandas as pd
from pathlib import Path

# ── Update to wherever your parquet files live ────────────────────────────────
PARQUET_DIR = Path("./parquet")

def pq(filename):
    return PARQUET_DIR / filename


def load_all(include_puf=True):

    if include_puf:
        print("Loading PUF files...")

        oon = pd.read_parquet(pq("oon_all_quarters.parquet"))
        print(f"  oon:  {len(oon):>12,} rows  |  {oon['Quarter'].nunique()} quarters  |  {len(oon.columns)} columns")

        qpa = pd.read_parquet(pq("qpa_all_quarters.parquet"))
        print(f"  qpa:  {len(qpa):>12,} rows  |  {qpa['Quarter'].nunique()} quarters  |  {len(qpa.columns)} columns")

        air = pd.read_parquet(pq("air_all_quarters.parquet"))
        print(f"  air:  {len(air):>12,} rows  |  {air['Quarter'].nunique()} quarters  |  {len(air.columns)} columns")

    else:
        print("Skipping PUF files.")
        oon = qpa = air = None

    print("\nLoading supplemental tables...")

    supp_disputes_initiated = pd.read_parquet(pq("supp_summary_disputes_initiated.parquet"))
    print(f"  supp_disputes_initiated:   {len(supp_disputes_initiated):>6,} rows")

    supp_provider_size = pd.read_parquet(pq("supp_provider_size.parquet"))
    print(f"  supp_provider_size:        {len(supp_provider_size):>6,} rows")

    supp_plan_type = pd.read_parquet(pq("supp_plan_type.parquet"))
    print(f"  supp_plan_type:            {len(supp_plan_type):>6,} rows")

    supp_closure_reasons = pd.read_parquet(pq("supp_closure_reasons.parquet"))
    print(f"  supp_closure_reasons:      {len(supp_closure_reasons):>6,} rows")

    supp_eligibility = pd.read_parquet(pq("supp_eligibility.parquet"))
    print(f"  supp_eligibility:          {len(supp_eligibility):>6,} rows")

    supp_state = pd.read_parquet(pq("supp_initiations_by_state.parquet"))
    print(f"  supp_state:                {len(supp_state):>6,} rows")

    supp_top_initiating = pd.read_parquet(pq("supp_top_initiating_parties.parquet"))
    print(f"  supp_top_initiating:       {len(supp_top_initiating):>6,} rows")

    supp_top_noninitiating = pd.read_parquet(pq("supp_top_noninitiating_parties.parquet"))
    print(f"  supp_top_noninitiating:    {len(supp_top_noninitiating):>6,} rows")

    supp_outcomes = pd.read_parquet(pq("supp_payment_determination_outcomes.parquet"))
    print(f"  supp_outcomes:             {len(supp_outcomes):>6,} rows")

    supp_cost_band = pd.read_parquet(pq("supp_qpa_by_cost_band.parquet"))
    print(f"  supp_cost_band:            {len(supp_cost_band):>6,} rows")

    supp_specialty = pd.read_parquet(pq("supp_qpa_by_specialty.parquet"))
    print(f"  supp_specialty:            {len(supp_specialty):>6,} rows")

    print("\nAll files loaded.")

    return (
        oon, qpa, air,
        supp_disputes_initiated,
        supp_provider_size,
        supp_plan_type,
        supp_closure_reasons,
        supp_eligibility,
        supp_state,
        supp_top_initiating,
        supp_top_noninitiating,
        supp_outcomes,
        supp_cost_band,
        supp_specialty,
    )


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    (
        oon, qpa, air,
        supp_disputes_initiated,
        supp_provider_size,
        supp_plan_type,
        supp_closure_reasons,
        supp_eligibility,
        supp_state,
        supp_top_initiating,
        supp_top_noninitiating,
        supp_outcomes,
        supp_cost_band,
        supp_specialty,
    ) = load_all(include_puf=False)  # NOTE: If you want to include/exclude PUF files, change this
