"""
PUF Field Checker
==================
Validates a new raw CMS IDR PUF quarter file against the schema and known
value domains already present in the current parquet files, before it gets
merged in. Read-only -- never modifies parquet or raw files.

Usage:
    from puf_checker import check_file

    report = check_file(
        "federal-idr-puf-2025-q3/Federal IDR PUF for 2025 Q3 - OON Emergency & Non-Emergency (As of January 26, 2026) (CSV).csv",
        file_type="oon",
        quarter="2025Q3",
    )
    report.summary()

NOTE: the Quarter tag format actually stored in the parquet files is "2025Q3"
(no space, year-first) -- NOT the "Q3 2025" format documented in CLAUDE.md and
coded into build_parquets.py's QUARTERS manifest. The two have drifted; this
module matches the real, on-disk format.

What it checks:
  - Column diff       -- columns present in the current parquet but missing from
                          the new file, and new columns not yet seen
  - Suppression tokens -- non-numeric values in currency/numeric columns that
                          aren't already known (NR, N/R, N/A, ^)
  - Categorical drift  -- new values in key categorical columns not present
                          anywhere in the current parquet
  - Domain-map coverage-- provider/carrier email domains not in idr_mappings,
                          ranked by row count
  - Quarter collision  -- refuses if the target Quarter is already loaded
  - Row-count sanity   -- vs. the most recent quarter already on file

Reference schema and known values are derived live from the current parquet
files each run (via pyarrow, column-pruned -- no full-table load), so there's
no separate snapshot to keep in sync.
"""

import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Union, List

import pandas as pd
import pyarrow.parquet as pq

from idr_mappings import DOMAIN_MAP, CARRIER_MAP, ANTHEM_PATTERNS
from build_parquets import CURRENCY_COLS, NUMERIC_PATTERNS, SUPPRESSION_TOKENS

PARQUET_DIR = "parquet"

FILE_PARQUET = {
    "oon": "oon_all_quarters.parquet",
    "qpa": "qpa_all_quarters.parquet",
    "air": "air_all_quarters.parquet",
}

# Columns added during transform -- never present in a raw CMS file
DERIVED_COLS = {
    "Provider_Group", "Provider_Category",
    "Carrier_Group", "Anthem_Flag",
    "Outcome_Bucket", "Quarter",
}

# Suppression/missing markers already handled by the transform pipeline.
# "N/A" is included too -- pandas' default na_values would normally absorb it
# silently, but this module reads raw files with keep_default_na=False so it
# shows up as a literal token and needs to be in the known set explicitly.
KNOWN_SUPPRESSION_TOKENS = set(SUPPRESSION_TOKENS) | {"N/A"}

# Key categorical columns worth watching for new/unseen values.
# Not every file type has every column -- presence is checked per file.
CATEGORICAL_COLS = [
    "Payment Determination Outcome",
    "Default Decision",
    "Initiating Party",
    "Health Plan Type",
    "Type of Dispute",
    "Dispute Line Item Type",
    "Type of Service Code",
    "Offer Selected from Provider or Issuer",
    "Practice/Facility Size",
]

# Column name variants seen across quarters -- normalize before diffing
COLUMN_RENAMES = {
    "as Percent of QPA": "as % of QPA",
    "As Percent of QPA": "as % of QPA",
}

PROVIDER_DOMAIN_COL = "Provider Email Domain"
CARRIER_DOMAIN_COL = "Health Plan/Issuer Email Domain"

_ANTHEM_REGEX = "|".join(ANTHEM_PATTERNS)


def _quarter_sort_key(q):
    m = re.match(r"(\d{4})Q(\d)", str(q).strip())
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def _rename_columns(columns):
    cleaned = [c.strip() for c in columns]
    return [COLUMN_RENAMES.get(c, c) for c in cleaned]


@dataclass
class CheckReport:
    file_type: str
    quarter: str
    row_count: int = 0
    prior_quarter: str = None
    prior_row_count: int = None
    missing_columns: List[str] = field(default_factory=list)
    new_columns: List[str] = field(default_factory=list)
    unknown_suppression_tokens: Counter = field(default_factory=Counter)
    new_categorical_values: dict = field(default_factory=dict)
    unmapped_provider_domains: Counter = field(default_factory=Counter)
    unmapped_carrier_domains: Counter = field(default_factory=Counter)
    quarter_already_present: bool = False

    @property
    def ok(self):
        """True if nothing found that should block a merge (INFO-level items don't count)."""
        return not (
            self.quarter_already_present
            or self.missing_columns
            or self.unknown_suppression_tokens
            or self.new_categorical_values
        )

    def summary(self, top_n=15):
        print(f"=== Field check: {self.file_type.upper()} - {self.quarter} ===")
        line = f"Rows: {self.row_count:,}"
        if self.prior_quarter:
            pct = (self.row_count / self.prior_row_count - 1) * 100 if self.prior_row_count else 0
            line += f"   (prior quarter {self.prior_quarter}: {self.prior_row_count:,}, {pct:+.1f}%)"
        print(line)

        if self.quarter_already_present:
            print(f"\n[FAIL] Quarter '{self.quarter}' is already present in {FILE_PARQUET[self.file_type]}")

        if self.missing_columns:
            print(f"\n[WARN] Missing columns (present in current parquet, absent from this file):")
            for c in self.missing_columns:
                print(f"    - {c}")

        if self.new_columns:
            print(f"\n[WARN] New columns (not in current parquet -- will backfill NaN for earlier quarters):")
            for c in self.new_columns:
                print(f"    - {c}")

        if self.unknown_suppression_tokens:
            print(f"\n[WARN] Unrecognized non-numeric tokens in currency/numeric columns:")
            for tok, n in self.unknown_suppression_tokens.most_common(top_n):
                print(f"    - {tok!r}: {n:,} occurrences")

        if self.new_categorical_values:
            print(f"\n[WARN] New values in tracked categorical columns:")
            for col, vals in self.new_categorical_values.items():
                print(f"    - {col}: {sorted(vals)}")

        if self.unmapped_provider_domains:
            total = sum(self.unmapped_provider_domains.values())
            print(f"\n[INFO] Unmapped provider domains ({total:,} rows, not in idr_mappings.DOMAIN_MAP), top {top_n}:")
            for dom, n in self.unmapped_provider_domains.most_common(top_n):
                print(f"    - {dom}: {n:,} rows")

        if self.unmapped_carrier_domains:
            total = sum(self.unmapped_carrier_domains.values())
            print(f"\n[INFO] Unmapped carrier domains ({total:,} rows, not in idr_mappings.CARRIER_MAP, not Anthem-pattern), top {top_n}:")
            for dom, n in self.unmapped_carrier_domains.most_common(top_n):
                print(f"    - {dom}: {n:,} rows")

        print(f"\n{'PASS' if self.ok else 'NEEDS REVIEW'}")


def check_file(raw_path: Union[str, List[str]], file_type: str, quarter: str,
                chunksize: int = 250_000) -> CheckReport:
    """
    Validate a raw CMS PUF CSV (or list of CSV chunks) against the current
    parquet for the given file_type ('oon', 'qpa', or 'air').
    """
    if file_type not in FILE_PARQUET:
        raise ValueError(f"file_type must be one of {list(FILE_PARQUET)}, got {file_type!r}")

    paths = [raw_path] if isinstance(raw_path, str) else list(raw_path)
    parquet_path = os.path.join(PARQUET_DIR, FILE_PARQUET[file_type])

    pf = pq.ParquetFile(parquet_path)
    schema_names = set(pf.schema_arrow.names)
    ref_columns = schema_names - DERIVED_COLS

    # ── Quarter presence / row-count baseline ──────────────────────────────
    quarters_series = pq.read_table(parquet_path, columns=["Quarter"]).to_pandas()["Quarter"]
    existing_quarters = quarters_series.value_counts().to_dict()
    quarter_already_present = quarter in existing_quarters
    prior_quarters = sorted(existing_quarters, key=_quarter_sort_key)
    prior_quarter = prior_quarters[-1] if prior_quarters else None
    prior_row_count = existing_quarters.get(prior_quarter)

    # ── Known categorical values, read once (column-pruned) ────────────────
    cat_cols_present = [c for c in CATEGORICAL_COLS if c in schema_names]
    ref_cat_values = {}
    if cat_cols_present:
        cat_table = pq.read_table(parquet_path, columns=cat_cols_present).to_pandas()
        for c in cat_cols_present:
            ref_cat_values[c] = set(cat_table[c].dropna().unique())
        del cat_table

    # ── Column diff (header only) ───────────────────────────────────────────
    header = pd.read_csv(paths[0], nrows=0, dtype=str)
    raw_columns = set(_rename_columns(header.columns))

    missing_columns = sorted(ref_columns - raw_columns)
    new_columns = sorted(raw_columns - ref_columns)

    has_provider_domain = PROVIDER_DOMAIN_COL in raw_columns
    has_carrier_domain = CARRIER_DOMAIN_COL in raw_columns
    scan_numeric_cols = sorted(
        c for c in raw_columns
        if c in CURRENCY_COLS or any(p in c for p in NUMERIC_PATTERNS)
    )
    cat_cols_to_scan = [c for c in CATEGORICAL_COLS if c in raw_columns]

    # ── Stream the raw file(s) in chunks ────────────────────────────────────
    row_count = 0
    unknown_tokens = Counter()
    new_cat_values = {c: set() for c in cat_cols_to_scan}
    unmapped_provider = Counter()
    unmapped_carrier = Counter()

    for path in paths:
        reader = pd.read_csv(
            path, chunksize=chunksize, dtype=str,
            keep_default_na=False, na_values=[], low_memory=False,
        )
        for chunk in reader:
            chunk.columns = _rename_columns(chunk.columns)
            row_count += len(chunk)

            for col in scan_numeric_cols:
                if col not in chunk.columns:
                    continue
                vals = chunk[col].str.strip()
                vals = vals[vals != ""]
                if vals.empty:
                    continue
                cleaned = vals.str.replace(r"[$,]", "", regex=True)
                is_numeric = pd.to_numeric(cleaned, errors="coerce").notna()
                bad = vals[~is_numeric]
                bad = bad[~bad.isin(KNOWN_SUPPRESSION_TOKENS)]
                if len(bad):
                    unknown_tokens.update(bad.value_counts().to_dict())

            for col in cat_cols_to_scan:
                if col not in chunk.columns:
                    continue
                vals = set(chunk[col].unique()) - {""}
                unseen = vals - ref_cat_values.get(col, set())
                if unseen:
                    new_cat_values[col] |= unseen

            if has_provider_domain and PROVIDER_DOMAIN_COL in chunk.columns:
                dom = chunk[PROVIDER_DOMAIN_COL].str.lower().str.strip()
                dom = dom[dom != ""]
                unmapped = dom[~dom.isin(DOMAIN_MAP.keys())]
                if len(unmapped):
                    unmapped_provider.update(unmapped.value_counts().to_dict())

            if has_carrier_domain and CARRIER_DOMAIN_COL in chunk.columns:
                dom = chunk[CARRIER_DOMAIN_COL].str.lower().str.strip()
                dom = dom[dom != ""]
                not_mapped = ~dom.isin(CARRIER_MAP.keys())
                not_anthem = ~dom.str.contains(_ANTHEM_REGEX, regex=True, na=False)
                unmapped = dom[not_mapped & not_anthem]
                if len(unmapped):
                    unmapped_carrier.update(unmapped.value_counts().to_dict())

    new_cat_values = {c: v for c, v in new_cat_values.items() if v}

    return CheckReport(
        file_type=file_type,
        quarter=quarter,
        row_count=row_count,
        prior_quarter=prior_quarter,
        prior_row_count=prior_row_count,
        missing_columns=missing_columns,
        new_columns=new_columns,
        unknown_suppression_tokens=unknown_tokens,
        new_categorical_values=new_cat_values,
        unmapped_provider_domains=unmapped_provider,
        unmapped_carrier_domains=unmapped_carrier,
        quarter_already_present=quarter_already_present,
    )
