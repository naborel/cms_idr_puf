"""
PUF Quarter Transform
=======================
Normalizes a new raw CMS IDR PUF quarter file into the same shape as the
existing parquet tables, ready to concat on. Reuses the exact normalization
functions from build_parquets.py (normalize, convert_currency_cols,
force_string_cols, convert_numeric_cols, cast_object_numerics) so a
from-scratch historical rebuild and an incremental quarter-add can never
silently drift apart the way the Ambulance Vehicle Type columns did.

Usage:
    from puf_transform import transform_quarter

    new_oon = transform_quarter(
        "federal-idr-puf-2025-q3/Federal IDR PUF for 2025 Q3 - OON Emergency & Non-Emergency (As of January 26, 2026) (CSV).csv",
        file_type="oon",
        quarter="2025Q3",
    )

Run puf_checker.check_file() first and review the report -- this function
does not re-validate, it just transforms.

Quarter tags must match the format already stored in the parquet files:
"2025Q3" (no space, year-first) -- not "Q3 2025".
"""

import pandas as pd

from build_parquets import (
    normalize, convert_numeric_cols, cast_object_numerics, NUMERIC_PATTERNS,
    QPA_NUMERIC_PATTERNS, QPA_NUMERIC_EXCLUDE,
)
from idr_mappings import apply_all_maps, add_outcome_bucket

# file types that get provider/carrier domain maps + outcome bucket applied
MAPPED_TYPES = {"oon", "air"}


def transform_quarter(raw_path, file_type, quarter):
    """
    raw_path: single CSV path, or list of CSV chunk paths for one quarter/type
              (mirrors the old chunk1/chunk2/chunk3 pattern used for 2025 Q1/Q2).
    file_type: 'oon' | 'qpa' | 'air'
    quarter:   e.g. '2025Q3' -- must match the format already in the parquet.

    Returns a normalized DataFrame ready to pd.concat onto the existing table.
    """
    if file_type not in ("oon", "qpa", "air"):
        raise ValueError(f"file_type must be 'oon', 'qpa', or 'air', got {file_type!r}")

    paths = [raw_path] if isinstance(raw_path, str) else list(raw_path)

    chunks = []
    for path in paths:
        print(f"  Loading: {path}")
        raw = pd.read_csv(path, low_memory=False)
        chunks.append(normalize(raw, quarter))

    df = pd.concat(chunks, ignore_index=True) if len(chunks) > 1 else chunks[0]

    if file_type == "qpa":
        df = convert_numeric_cols(df, QPA_NUMERIC_PATTERNS, exclude=QPA_NUMERIC_EXCLUDE)
    else:
        df = convert_numeric_cols(df, NUMERIC_PATTERNS)
    df = cast_object_numerics(df)

    if file_type in MAPPED_TYPES:
        df = apply_all_maps(df)
        df = add_outcome_bucket(df)

    return df
