"""
IDR PUF Data Loader
=====================
Reads all quarters (2023 Q1 – 2025 Q2) of CMS Federal IDR Public Use Files
from year-organised raw data folders and writes three consolidated parquet files:

  parquet/oon_all_quarters.parquet   -- OON Emergency & Non-Emergency
  parquet/qpa_all_quarters.parquet   -- QPA and Offers
  parquet/air_all_quarters.parquet   -- OON Air Ambulance

Expected raw data layout:
  ./2023/    *.xlsx files for 2023 quarters
  ./2024/    *.xlsx files for 2024 quarters
  ./2025/    *.csv  files for 2025 quarters (Q1 OON split into 2 chunks,
                                              Q2 OON split into 3 chunks)

Transformations applied:
  - Column rename: "as Percent of QPA" → "as % of QPA" (changed in 2023 Q3)
  - Global replace: "NR" / "N/R" → NaN (CMS suppression markers)
  - Currency columns: strip "$" and "," before numeric conversion (IDRE Compensation)
  - Force string columns: Service Code, Place of Service Code, Type of Service Code,
      Item or Service Description, Practice/Facility Specialty or Type,
      Ambulance Vehicle Type, Ambulance Vehicle Clinical Capacity Level
  - Numeric columns: offer/QPA percent columns, NPI Number, Length of Time,
      IDRE Compensation, QPA dollar amounts
  - Provider domain mapping: Provider_Group, Provider_Category (from idr_mappings.py)
  - Carrier domain mapping: Carrier_Group, Anthem_Flag (from idr_mappings.py)
  - Outcome bucket: Outcome_Bucket column added (OON and Air only)
  - Quarter tag: Quarter column added to every row

Notes:
  - 2025 files are CSVs; 2023/2024 are xlsx
  - 2025 Q1 OON split into 2 chunks; 2025 Q2 OON split into 3 chunks
  - TODO: Remove leading space from "QPA and Offers" sheetname in 2023Q2 file on fresh download
  - TODO: Rename 'Air Ambulance' sheet to 'OON Air Ambulance' in 2023Q2 file on fresh download
"""

import os
import pandas as pd
import numpy as np
from idr_mappings import apply_all_maps, add_outcome_bucket

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR = r"."
OUT_DIR  = r"./parquet"
os.makedirs(OUT_DIR, exist_ok=True)

def fp(filename):  return os.path.join(DATA_DIR, filename)
def out(filename): return os.path.join(OUT_DIR, filename)


# ── File manifest ─────────────────────────────────────────────────────────────
QUARTERS = [
    {
        'quarter'  : 'Q1 2023',
        'filetype' : 'xlsx',
        'oon'      : '2023/2023-q1-federal-idr-puf_0.xlsx',
        'qpa'      : '2023/2023-q1-federal-idr-puf_0.xlsx',
        'air'      : '2023/2023-q1-federal-idr-puf_0.xlsx',
    },
    {
        'quarter'  : 'Q2 2023',
        'filetype' : 'xlsx',
        'oon'      : '2023/Federal-IDR-PUF-for-2023-Q2.xlsx',
        'qpa'      : '2023/Federal-IDR-PUF-for-2023-Q2.xlsx',
        'air'      : '2023/Federal-IDR-PUF-for-2023-Q2.xlsx',
    },
    {
        'quarter'  : 'Q3 2023',
        'filetype' : 'xlsx',
        'oon'      : '2023/Federal IDR PUF for 2023 Q3.xlsx',
        'qpa'      : '2023/Federal IDR PUF for 2023 Q3.xlsx',
        'air'      : '2023/Federal IDR PUF for 2023 Q3.xlsx',
    },
    {
        'quarter'  : 'Q4 2023',
        'filetype' : 'xlsx',
        'oon'      : '2023/Federal IDR PUF for 2023 Q4.xlsx',
        'qpa'      : '2023/Federal IDR PUF for 2023 Q4.xlsx',
        'air'      : '2023/Federal IDR PUF for 2023 Q4.xlsx',
    },
    {
        'quarter'  : 'Q1 2024',
        'filetype' : 'xlsx',
        'oon'      : '2024/federal-idr-puf-for-2024-q1-as-of-march-18-2025.xlsx',
        'qpa'      : '2024/federal-idr-puf-for-2024-q1-as-of-march-18-2025.xlsx',
        'air'      : '2024/federal-idr-puf-for-2024-q1-as-of-march-18-2025.xlsx',
    },
    {
        'quarter'  : 'Q2 2024',
        'filetype' : 'xlsx',
        'oon'      : '2024/federal-idr-puf-for-2024-q2-as-of-march-18-2025.xlsx',
        'qpa'      : '2024/federal-idr-puf-for-2024-q2-as-of-march-18-2025.xlsx',
        'air'      : '2024/federal-idr-puf-for-2024-q2-as-of-march-18-2025.xlsx',
    },
    {
        'quarter'  : 'Q3 2024',
        'filetype' : 'xlsx',
        'oon'      : '2024/federal-idr-puf-for-2024-q3-as-of-may-28-2025.xlsx',
        'qpa'      : '2024/federal-idr-puf-for-2024-q3-as-of-may-28-2025.xlsx',
        'air'      : '2024/federal-idr-puf-for-2024-q3-as-of-may-28-2025.xlsx',
    },
    {
        'quarter'  : 'Q4 2024',
        'filetype' : 'xlsx',
        'oon'      : '2024/federal-idr-puf-for-2024-q4-as-of-may-28-2025.xlsx',
        'qpa'      : '2024/federal-idr-puf-for-2024-q4-as-of-may-28-2025.xlsx',
        'air'      : '2024/federal-idr-puf-for-2024-q4-as-of-may-28-2025.xlsx',
    },
    {
        'quarter'  : 'Q1 2025',
        'filetype' : 'csv',
        'oon'      : [
            '2025/Federal IDR PUF for 2025 Q1 - OON Emergency & Non-Emergency (As of January 21, 2026) chunk1.csv',
            '2025/Federal IDR PUF for 2025 Q1 - OON Emergency & Non-Emergency (As of January 21, 2026) chunk2.csv',
        ],
        'qpa'      : '2025/Federal IDR PUF for 2025 Q1 - QPA and Offers (As of January 21, 2026).csv',
        'air'      : '2025/Federal IDR PUF for 2025 Q1 - OON Air Ambulance (As of January 21, 2026).csv',
    },
    {
        'quarter'  : 'Q2 2025',
        'filetype' : 'csv',
        'oon'      : [
            '2025/Federal IDR PUF for 2025 Q2 - OON Emergency & Non-Emergency (As of January 21, 2026) chunk1.csv',
            '2025/Federal IDR PUF for 2025 Q2 - OON Emergency & Non-Emergency (As of January 21, 2026) chunk2.csv',
            '2025/Federal IDR PUF for 2025 Q2 - OON Emergency & Non-Emergency (As of January 21, 2026) chunk3.csv',
        ],
        'qpa'      : '2025/Federal IDR PUF for 2025 Q2 - QPA and Offers (As of January 21, 2026).csv',
        'air'      : '2025/Federal IDR PUF for 2025 Q2 - OON Air Ambulance (As of January 21, 2026).csv',
    },
]

SHEET_OON = 'OON Emergency and Non-Emergency'
SHEET_QPA = 'QPA and Offers'
SHEET_AIR = 'OON Air Ambulance'


# ── Type conversion helpers ───────────────────────────────────────────────────

# Columns that must always be string (codes, descriptions, names)
FORCE_STR_COLS = [
    'Service Code',
    'Place of Service Code',
    'Type of Service Code',
    'Item or Service Description',
    'Practice/Facility Specialty or Type',
    'Air Ambulance Vehicle Type',
    'Air Ambulance Vehicle Clinical Capacity Level',
    'Geographical Region',
]

# Columns to convert to numeric after stripping currency formatting
CURRENCY_COLS = [
    'IDRE Compensation',
    'QPA',
    'Provider/Facility Offer',
    'Health Plan/Issuer Offer',
    'Prevailing Offer',
]

# Substring patterns for columns to convert to numeric
NUMERIC_PATTERNS = [
    'as % of QPA',
    'as Percent of Median',
    'NPI Number',
    'Length of Time',
    'IDRE Compensation',
]


def convert_numeric_cols(df, patterns):
    """Convert columns whose name contains any of the given substrings to numeric."""
    for col in df.columns:
        if any(p in col for p in patterns):
            df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def convert_currency_cols(df):
    """Strip $ and commas, then convert to numeric for currency-formatted columns."""
    for col in CURRENCY_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str)
                       .str.replace(r'[$,]', '', regex=True)
                       .str.strip(),
                errors='coerce'
            )
    return df


def force_string_cols(df):
    """
    Cast code/description columns to string.
    These come through as int in some xlsx quarters and str in others.
    Null values become pd.NA rather than the string 'nan'.
    """
    for col in FORCE_STR_COLS:
        if col in df.columns:
            df[col] = df[col].astype(str).replace('nan', pd.NA)
    return df


def cast_object_numerics(df):
    """
    Safety net: after concat, find any remaining object columns that are
    overwhelmingly numeric (>90% parseable) and convert them.
    Catches mixed int/str columns that slipped through earlier steps.
    """
    for col in df.select_dtypes(include='object').columns:
        if col in FORCE_STR_COLS:
            continue
        non_null = df[col].dropna()
        if len(non_null) == 0:
            continue
        converted = pd.to_numeric(
            non_null.astype(str).str.replace(r'[$,]', '', regex=True),
            errors='coerce'
        )
        if converted.notna().sum() / len(non_null) > 0.90:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r'[$,]', '', regex=True),
                errors='coerce'
            )
    return df


# ── Normalization ─────────────────────────────────────────────────────────────

def normalize(df, quarter):
    """
    Apply all cross-quarter normalization to a freshly loaded dataframe.
    Safe to call on any sheet type (oon, qpa, air).
    """
    # 1. Strip whitespace from column names
    df.columns = [c.strip() for c in df.columns]

    # 2. Standardize column name variant introduced in 2023 Q3
    #    "as Percent of QPA" (Q1–Q2 2023) → "as % of QPA" (Q3 2023 onward)
    df.columns = [
        c.replace('as Percent of QPA', 'as % of QPA')
         .replace('As Percent of QPA', 'as % of QPA')
        for c in df.columns
    ]

    # 3. Replace CMS suppression/missing markers globally
    df = df.replace({'NR': pd.NA, 'N/R': pd.NA})

    # 4. Force code/description columns to string before any numeric conversion
    df = force_string_cols(df)

    # 5. Strip currency formatting and convert
    df = convert_currency_cols(df)

    # 6. Tag quarter
    df['Quarter'] = quarter

    return df


# ── Loaders ───────────────────────────────────────────────────────────────────

def load_xlsx_sheet(filepath, sheet_name, quarter):
    print(f"  Loading xlsx: {os.path.basename(filepath)} | sheet: {sheet_name}")
    df = pd.read_excel(filepath, sheet_name=sheet_name, engine='openpyxl')
    return normalize(df, quarter)


def load_csv(filepath, quarter):
    print(f"  Loading csv:  {os.path.basename(filepath)}")
    df = pd.read_csv(filepath, low_memory=False)
    return normalize(df, quarter)


def load_csv_chunks(filepaths, quarter):
    chunks = [load_csv(f, quarter) for f in filepaths]
    return pd.concat(chunks, ignore_index=True)


# ── Build functions ───────────────────────────────────────────────────────────

def build_oon():
    print("\n=== Building OON dataset ===")
    all_dfs = []

    for q in QUARTERS:
        quarter, filetype, source = q['quarter'], q['filetype'], q['oon']
        print(f"\n{quarter}:")
        if filetype == 'xlsx':
            all_dfs.append(load_xlsx_sheet(fp(source), SHEET_OON, quarter))
        else:
            all_dfs.append(load_csv_chunks([fp(f) for f in source], quarter))

    print("\nConcatenating all quarters...")
    oon = pd.concat(all_dfs, ignore_index=True)

    oon = convert_numeric_cols(oon, NUMERIC_PATTERNS)
    oon = cast_object_numerics(oon)

    print("Applying domain mappings...")
    oon = apply_all_maps(oon)
    oon = add_outcome_bucket(oon)

    print(f"OON total rows:    {len(oon):,}")
    print(f"OON columns:       {len(oon.columns)}")
    print(f"OON quarters:      {oon['Quarter'].value_counts().sort_index().to_dict()}")
    print(f"OON outcome buckets:\n{oon['Outcome_Bucket'].value_counts().to_string()}")
    return oon


def build_qpa():
    print("\n=== Building QPA dataset ===")
    all_dfs = []

    for q in QUARTERS:
        quarter, filetype, source = q['quarter'], q['filetype'], q['qpa']
        if source is None:
            print(f"{quarter}: no QPA file — skipping")
            continue
        print(f"\n{quarter}:")
        if filetype == 'xlsx':
            all_dfs.append(load_xlsx_sheet(fp(source), SHEET_QPA, quarter))
        else:
            all_dfs.append(load_csv(fp(source), quarter))

    print("\nConcatenating all quarters...")
    qpa = pd.concat(all_dfs, ignore_index=True)

    qpa = convert_numeric_cols(qpa, ['QPA', 'Offer', 'Prevailing', 'Percent'])
    qpa = cast_object_numerics(qpa)

    print(f"QPA total rows:    {len(qpa):,}")
    print(f"QPA quarters:      {qpa['Quarter'].value_counts().sort_index().to_dict()}")
    return qpa


def build_air():
    print("\n=== Building Air Ambulance dataset ===")
    all_dfs = []

    for q in QUARTERS:
        quarter, filetype, source = q['quarter'], q['filetype'], q['air']
        if source is None:
            print(f"{quarter}: no Air file — skipping")
            continue
        print(f"\n{quarter}:")
        if filetype == 'xlsx':
            all_dfs.append(load_xlsx_sheet(fp(source), SHEET_AIR, quarter))
        else:
            all_dfs.append(load_csv(fp(source), quarter))

    print("\nConcatenating all quarters...")
    air = pd.concat(all_dfs, ignore_index=True)

    air = convert_numeric_cols(air, NUMERIC_PATTERNS)
    air = cast_object_numerics(air)

    print("Applying domain mappings...")
    air = apply_all_maps(air)
    air = add_outcome_bucket(air)

    print(f"Air total rows:    {len(air):,}")
    print(f"Air quarters:      {air['Quarter'].value_counts().sort_index().to_dict()}")
    return air


# ── Run ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    oon = build_oon()
    qpa = build_qpa()
    air = build_air()

    print("\n=== Saving parquet files ===")

    oon_out = out('oon_all_quarters.parquet')
    qpa_out = out('qpa_all_quarters.parquet')
    air_out = out('air_all_quarters.parquet')

    oon.to_parquet(oon_out, compression='snappy', index=False)
    print(f"Saved: {oon_out}  ({os.path.getsize(oon_out)/1e6:.1f} MB)")

    qpa.to_parquet(qpa_out, compression='snappy', index=False)
    print(f"Saved: {qpa_out}  ({os.path.getsize(qpa_out)/1e6:.1f} MB)")

    air.to_parquet(air_out, compression='snappy', index=False)
    print(f"Saved: {air_out}  ({os.path.getsize(air_out)/1e6:.1f} MB)")

    print("\nDone.")
    print(f"  OON: {len(oon):,} rows  |  {len(oon.columns)} columns")
    print(f"  QPA: {len(qpa):,} rows  |  {len(qpa.columns)} columns")
    print(f"  Air: {len(air):,} rows  |  {len(air.columns)} columns")
