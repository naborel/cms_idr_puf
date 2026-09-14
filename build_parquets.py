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
  - Percent columns: xlsx quarters store these as TEXT ("1,014%"); CSV quarters store
      them as decimal multiples (7.91). Parsed per value -- anything carrying a literal
      "%" is stripped and divided by 100. See _parse_numeric_smart.
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
    'Service Code Modifier(s)',
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

# QPA-specific numeric-pattern conversion. 'Offer' also substring-matches the
# categorical 'Offer Selected from Provider or Issuer' column, so it must be
# excluded -- it was invisible for years because that column was always empty
# until CMS started populating it in 2025 Q3.
QPA_NUMERIC_PATTERNS = ['QPA', 'Offer', 'Prevailing', 'Percent']
QPA_NUMERIC_EXCLUDE = ['Offer Selected from Provider or Issuer']

# CMS suppression/missing-data markers seen across quarters.
# NR / N/R -- original markers (2023 Q1 onward).
# ^        -- new in 2025 Q3, seen in QPA dollar columns (QPA, offers).
# +, *     -- new in 2025 Q3, seen only in "offer as % of QPA" /
#             "as Percent of Median" columns. Confirmed by sampling raw rows;
#             both are redaction symbols, not data corruption.
SUPPRESSION_TOKENS = ['NR', 'N/R', '^', '+', '*']


def _parse_numeric_smart(s):
    """
    Parse a column that may hold EITHER decimal multiples or percent-formatted text,
    deciding per value rather than per column.

    This matters because convert_numeric_cols runs after all quarters are concatenated,
    so one column legitimately holds both formats at once:

      CSV quarters (2025+)      ->  7.91          already a multiple, take as-is
      XLSX quarters (2023/2024) ->  '1,014%'      text; strip and divide by 100 -> 10.14

    Any value carrying a literal '%' is stripped of '%' and ',' and divided by 100.
    Values without '%' are stripped of '$' and ',' and taken at face value. Suppression
    markers (NR / N/R / ^ / + / *) are already pd.NA by this point (normalize() replaces
    them) and stay null.

    Returns (converted_series, had_percent_mask).

    Regression guard: before this existed, pd.to_numeric('1,014%') coerced silently to
    NaN, which wiped every percent column for 2024 Q3 and Q4 -- 1.6M line items, 100%
    null, with no error raised. Do not "simplify" this back to a bare to_numeric.
    """
    orig_notna = s.notna()
    txt = s.where(orig_notna).astype(str).str.strip()
    has_pct = txt.str.endswith('%', na=False) & orig_notna
    cleaned = (txt.str.replace(',', '', regex=False)
                  .str.replace('$', '', regex=False)
                  .str.rstrip('%'))
    num = pd.to_numeric(cleaned, errors='coerce')
    num = num.mask(has_pct, num / 100.0)
    return num, has_pct


def convert_numeric_cols(df, patterns, exclude=None, label=""):
    """Convert columns whose name contains any of the given substrings to numeric.

    exclude: column names to skip even if they match a pattern -- needed because
    e.g. 'Offer' as a substring also matches the categorical column
    'Offer Selected from Provider or Issuer'.

    Prints a per-quarter parse report so a format change in a future CMS release
    surfaces loudly instead of silently becoming null.
    """
    exclude = exclude or []
    targets = [c for c in df.columns
               if c not in exclude and any(p in c for p in patterns)]
    if not targets:
        return df

    has_q = 'Quarter' in df.columns
    report = []
    for col in targets:
        before = df[col].notna()
        conv, had_pct = _parse_numeric_smart(df[col])
        after = conv.notna()
        df[col] = conv
        if has_q:
            t = pd.DataFrame({'q': df['Quarter'].values,
                              'b': before.values, 'a': after.values, 'p': had_pct.values})
            g = t.groupby('q', dropna=False).agg(non_null=('b', 'sum'),
                                                 parsed=('a', 'sum'),
                                                 pct_scaled=('p', 'sum'))
            for q, r in g.iterrows():
                report.append((q, col, int(r.non_null), int(r.parsed), int(r.pct_scaled)))

    if report:
        rep = pd.DataFrame(report, columns=['Quarter', 'column', 'non_null', 'parsed', 'pct_scaled'])
        agg = rep.groupby('Quarter')[['non_null', 'parsed', 'pct_scaled']].sum()
        agg['lost'] = agg['non_null'] - agg['parsed']
        agg['pct_fmt_%'] = (100.0 * agg['pct_scaled'] / agg['non_null'].replace(0, pd.NA)).round(1)
        print(f"\n  -- numeric parse report{(' [' + label + ']') if label else ''} "
              f"({len(targets)} columns) --")
        print(agg.to_string())
        bad = agg[agg['lost'] > 0]
        if len(bad):
            print("  !! values that were non-null but did not parse "
                  "(unrecognised format or new CMS marker):")
            worst = rep.assign(lost=rep.non_null - rep.parsed).query("lost > 0") \
                       .sort_values('lost', ascending=False).head(12)
            print(worst.to_string(index=False))
        dead = agg[(agg['non_null'] > 0) & (agg['parsed'] == 0)]
        if len(dead):
            raise ValueError(
                f"Every value failed to parse for quarter(s) {list(dead.index)} -- "
                "this is the 2024Q3/Q4 percent-string failure mode. Refusing to build.")
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
    Null values stay null. astype(str) turns a real NaN into the string
    'nan' and a suppressed value (already pd.NA from the suppression-token
    replace above) into the string '<NA>' -- mask both back to pd.NA based
    on the original nullness rather than pattern-matching the string output,
    since astype(str)'s null representation isn't consistent.
    """
    for col in FORCE_STR_COLS:
        if col in df.columns:
            s = df[col]
            df[col] = s.astype(str).where(s.notna(), pd.NA)
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
    df = df.replace({tok: pd.NA for tok in SUPPRESSION_TOKENS})

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

    oon = convert_numeric_cols(oon, NUMERIC_PATTERNS, label="OON")
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

    qpa = convert_numeric_cols(qpa, QPA_NUMERIC_PATTERNS, exclude=QPA_NUMERIC_EXCLUDE, label="QPA")
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

    air = convert_numeric_cols(air, NUMERIC_PATTERNS, label="AIR")
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
