"""
IDR Supplemental Tables Builder
=================================
Reads all 10 quarters of CMS Federal IDR Supplemental Table xlsx files and
writes one parquet per logical sub-table to the parquet/ directory.

Expected raw data layout:
  ./2023/    Federal-IDR-Supplemental-Tables-for-2023-Q*.xlsx
  ./2024/    federal-idr-supplemental-tables-for-2024-q*.xlsx
  ./2025/    federal-idr-supplemental-tables-2025-q*.xlsx

Output parquet files:
  parquet/supp_summary_disputes_initiated.parquet     -- Table 1
  parquet/supp_provider_size.parquet                  -- Table 2
  parquet/supp_plan_type.parquet                      -- Table 3
  parquet/supp_closure_reasons.parquet                -- Table 4
  parquet/supp_eligibility.parquet                    -- Table 5
  parquet/supp_initiations_by_state.parquet           -- Table 7
  parquet/supp_top_initiating_parties.parquet         -- Table 8
  parquet/supp_top_noninitiating_parties.parquet      -- Table 9
  parquet/supp_payment_determination_outcomes.parquet -- Table 12
  parquet/supp_qpa_by_cost_band.parquet               -- Table 13
  parquet/supp_qpa_by_specialty.parquet               -- Table 14

Notes:
  - All sheets are human-readable stacked tables, not raw tabular data
  - Each sub-table is parsed by detecting its title row ("Table N:")
  - 2025 Q1+ adds a 'Church Plan' column to Table 9 — earlier quarters NaN
  - Table numbering is consistent across all 10 quarters
  - 'Contents' sheet is skipped (legend only)
  - Some cells contain comma-formatted strings e.g. '63,395' — to_num handles these
"""

import os
import re
import pandas as pd
import numpy as np

# ── Config ────────────────────────────────────────────────────────────────────
DATA_DIR = r"."
OUT_DIR  = r"./parquet"

def fp(f):  return os.path.join(DATA_DIR, f)
def out(f): return os.path.join(OUT_DIR, f)


# ── File manifest ─────────────────────────────────────────────────────────────
QUARTERS = [
    ('Q1 2023', '2023/Federal-IDR-Supplemental-Tables-for-2023-Q1.xlsx'),
    ('Q2 2023', '2023/Federal-IDR-Supplemental-Tables-for-2023-Q2.xlsx'),
    ('Q3 2023', '2023/Federal IDR Supplemental Tables for 2023 Q3.xlsx'),
    ('Q4 2023', '2023/Federal IDR Supplemental Tables for 2023 Q4.xlsx'),
    ('Q1 2024', '2024/federal-idr-supplemental-tables-for-2024-q1-as-of-march-18-2025.xlsx'),
    ('Q2 2024', '2024/federal-idr-supplemental-tables-for-2024-q2-as-of-march-18-2025.xlsx'),
    ('Q3 2024', '2024/federal-idr-supplemental-tables-for-2024-q3-as-of-may-28-2025_0.xlsx'),
    ('Q4 2024', '2024/federal-idr-supplemental-tables-for-2024-q4-as-of-may-28-2025-1.xlsx'),
    ('Q1 2025', '2025/federal-idr-supplemental-tables-2025-q1.xlsx'),
    ('Q2 2025', '2025/federal-idr-supplemental-tables-2025-q2.xlsx'),
]


# ── Numeric conversion helper ─────────────────────────────────────────────────

def to_num(series):
    """Strip comma formatting then convert to numeric. Unconvertible → NaN."""
    return pd.to_numeric(
        series.astype(str).str.replace(',', '', regex=False).str.strip(),
        errors='coerce'
    )


# ── Core parser ───────────────────────────────────────────────────────────────

def load_raw(filepath, sheet_name):
    """Load a sheet with no header parsing — returns raw dataframe."""
    return pd.read_excel(filepath, sheet_name=sheet_name, header=None, engine='openpyxl')


def find_table_start(raw, table_number):
    """Find the row index where 'Table {N}:' appears in column 0."""
    pattern = re.compile(rf'Table\s+{table_number}\s*:', re.IGNORECASE)
    for i, val in enumerate(raw[0]):
        if isinstance(val, str) and pattern.match(val.strip()):
            return i
    return None


def extract_simple_table(raw, table_number, header_row_offset=1, skip_rows=0):
    """
    Extract a sub-table starting at Table N.
    Reads until the next blank row or next Table title.
    """
    start = find_table_start(raw, table_number)
    if start is None:
        return None

    header_row = start + header_row_offset
    data_start  = header_row + 1 + skip_rows

    end = len(raw)
    for i in range(start + 1, len(raw)):
        val = raw.iloc[i, 0]
        if isinstance(val, str) and re.match(r'Table\s+\d+\s*:', val.strip(), re.IGNORECASE):
            end = i
            break

    headers = raw.iloc[header_row].tolist()
    data    = raw.iloc[data_start:end].copy()
    data    = data.dropna(how='all')
    data.columns = headers
    data    = data.reset_index(drop=True)
    data    = data.dropna(axis=1, how='all')

    return data


# ── Sheet-specific parsers ────────────────────────────────────────────────────

def parse_summary_tables(raw, quarter):
    """Summary Tables sheet — parse each sub-table individually."""
    results = {}

    # Table 1: Disputes Initiated
    t1 = extract_simple_table(raw, 1, header_row_offset=1)
    if t1 is not None:
        t1.columns = ['Category', 'OON_Emergency_NonEmergency', 'Air_Ambulance', 'Total']
        t1 = t1[t1['Category'].notna()].copy()
        for col in ['OON_Emergency_NonEmergency', 'Air_Ambulance', 'Total']:
            t1[col] = to_num(t1[col])
        t1['Quarter'] = quarter
        results['summary_disputes_initiated'] = t1

    # Table 2: Provider/Facility Size
    t2 = extract_simple_table(raw, 2, header_row_offset=1)
    if t2 is not None:
        t2.columns = ['Provider_Size', 'OON_Emergency_NonEmergency']
        t2 = t2[t2['Provider_Size'].notna()].copy()
        t2['OON_Emergency_NonEmergency'] = to_num(t2['OON_Emergency_NonEmergency'])
        t2['Quarter'] = quarter
        results['provider_size'] = t2

    # Table 3: Health Plan Type
    t3 = extract_simple_table(raw, 3, header_row_offset=1)
    if t3 is not None:
        t3.columns = ['Health_Plan_Type', 'OON_Emergency_NonEmergency', 'Air_Ambulance', 'Total']
        t3 = t3[t3['Health_Plan_Type'].notna()].copy()
        for col in ['OON_Emergency_NonEmergency', 'Air_Ambulance', 'Total']:
            t3[col] = to_num(t3[col])
        t3['Quarter'] = quarter
        results['plan_type'] = t3

    # Table 4: Closure Reasons
    t4 = extract_simple_table(raw, 4, header_row_offset=1)
    if t4 is not None:
        t4 = t4[t4.iloc[:, 0].notna()].copy()
        for col in t4.columns[1:]:
            t4[col] = to_num(t4[col])
        t4['Quarter'] = quarter
        results['closure_reasons'] = t4

    # Table 5: Eligibility
    t5 = extract_simple_table(raw, 5, header_row_offset=1)
    if t5 is not None:
        t5 = t5[t5.iloc[:, 0].notna()].copy()
        for col in t5.columns[1:]:
            t5[col] = to_num(t5[col])
        t5['Quarter'] = quarter
        results['eligibility'] = t5

    return results


def parse_initiations_by_state(raw, quarter):
    """Table 7 — state initiations."""
    start = find_table_start(raw, 7)
    if start is None:
        return None

    headers = ['State_Territory', 'OON_Emergency_NonEmergency', 'Air_Ambulance', 'Total']

    data_start = start + 5
    data = raw.iloc[data_start:].copy()
    data = data.dropna(how='all')
    data = data[data.iloc[:, 0].notna()]

    rows = []
    for _, row in data.iterrows():
        val = row.iloc[0]
        if isinstance(val, str) and re.match(r'Table\s+\d+', val.strip(), re.IGNORECASE):
            break
        rows.append(row.tolist()[:4])

    df = pd.DataFrame(rows, columns=headers)
    df['State_Territory'] = df['State_Territory'].astype(str).str.replace(r'[+*†‡]', '', regex=True).str.strip()
    for col in ['OON_Emergency_NonEmergency', 'Air_Ambulance', 'Total']:
        df[col] = to_num(df[col])
    df['Quarter'] = quarter
    return df


def parse_top_initiating(raw, quarter):
    """Table 8 — top 10 initiating parties."""
    start = find_table_start(raw, 8)
    if start is None:
        return None

    data_start = start + 2
    end = find_table_start(raw, 9)
    if end is None:
        end = len(raw)

    data = raw.iloc[data_start:end].copy()
    data = data.dropna(how='all')
    data = data[data.iloc[:, 0].notna()]

    df = pd.DataFrame({
        'Initiating_Party': data.iloc[:, 0].values,
        'Total_Disputes':   to_num(data.iloc[:, 1]),
        'Pct_of_Disputes':  to_num(data.iloc[:, 2]),
    })
    df['Quarter'] = quarter
    return df


def parse_top_noninitiating(raw, quarter):
    """
    Table 9 — top 10 non-initiating parties with plan type subtotals.
    2025 Q1+ adds a 'Church Plan' column — handled by position.
    """
    start = find_table_start(raw, 9)
    if start is None:
        return None

    data_start = start + 3
    end = find_table_start(raw, 10)
    if end is None:
        end = len(raw)

    data = raw.iloc[data_start:end].copy()
    data = data.dropna(how='all')
    data = data[data.iloc[:, 0].notna()]

    base_cols = [
        'Non_Initiating_Party',
        'Total_Disputes',
        'Pct_of_Disputes',
        'Self_Insured',
        'Fully_Insured',
        'Individual_Market',
        'FEHB',
        'Non_Federal_Govt',
    ]

    n_cols = data.shape[1]
    if n_cols >= 10:
        cols = base_cols + ['Church_Plan', 'No_Issuer_Response']
    else:
        cols = base_cols + ['No_Issuer_Response']

    data_trimmed = data.iloc[:, :len(cols)].copy()
    data_trimmed.columns = cols

    for c in cols[1:]:
        data_trimmed[c] = to_num(data_trimmed[c])

    data_trimmed['Quarter'] = quarter
    return data_trimmed.reset_index(drop=True)


def parse_payment_determination_outcomes(raw, quarter):
    """Table 12 — payment determination outcome counts."""
    start = find_table_start(raw, 12)
    if start is None:
        return None

    data_start = start + 2
    end = find_table_start(raw, 13)
    if end is None:
        end = len(raw)

    data = raw.iloc[data_start:end].copy()
    data = data.dropna(how='all')
    data = data[data.iloc[:, 0].notna()]

    df = pd.DataFrame({
        'Metric':           data.iloc[:, 0].values,
        'OON_NonEmergency': to_num(data.iloc[:, 1]),
        'Air_Ambulance':    to_num(data.iloc[:, 2]),
        'Total':            to_num(data.iloc[:, 3]),
    })
    df['Quarter'] = quarter
    return df


def parse_qpa_by_cost_band(raw, quarter):
    """Table 13 — prevailing offer vs QPA by cost band."""
    start = find_table_start(raw, 13)
    if start is None:
        return None

    data_start = start + 2
    end = find_table_start(raw, 14)
    if end is None:
        end = len(raw)

    data = raw.iloc[data_start:end].copy()
    data = data.dropna(how='all')
    data = data[data.iloc[:, 0].notna()]

    df = pd.DataFrame({
        'QPA_Range':                       data.iloc[:, 0].values,
        'Median_Prevailing_Offer_Pct_QPA': to_num(data.iloc[:, 1]),
        'Total_Payment_Determinations':    to_num(data.iloc[:, 2]),
        'Total_Items_or_Services':         to_num(data.iloc[:, 3]),
    })
    df['Quarter'] = quarter
    return df


def parse_qpa_by_specialty(raw, quarter):
    """Table 14 — prevailing offer vs QPA by specialty."""
    start = find_table_start(raw, 14)
    if start is None:
        return None

    data_start = start + 2
    data = raw.iloc[data_start:].copy()
    data = data.dropna(how='all')
    data = data[data.iloc[:, 0].notna()]

    df = pd.DataFrame({
        'CPT_Range':                       data.iloc[:, 0].values,
        'Specialty':                       data.iloc[:, 1].values,
        'Median_Prevailing_Offer_Pct_QPA': to_num(data.iloc[:, 2]),
        'Total_Payment_Determinations':    to_num(data.iloc[:, 3]),
        'Total_Items_or_Services':         to_num(data.iloc[:, 4]),
    })
    df['Quarter'] = quarter
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def build_supplemental():
    os.makedirs(OUT_DIR, exist_ok=True)

    acc = {
        'summary_disputes_initiated':       [],
        'provider_size':                    [],
        'plan_type':                        [],
        'closure_reasons':                  [],
        'eligibility':                      [],
        'initiations_by_state':             [],
        'top_initiating_parties':           [],
        'top_noninitiating_parties':        [],
        'payment_determination_outcomes':   [],
        'qpa_by_cost_band':                 [],
        'qpa_by_specialty':                 [],
    }

    for quarter, filename in QUARTERS:
        path = fp(filename)
        print(f'\n{quarter}: {os.path.basename(path)}')

        raw_summary = load_raw(path, 'Summary Tables')
        for key, df in parse_summary_tables(raw_summary, quarter).items():
            if df is not None and len(df) > 0:
                acc[key].append(df)
                print(f'  Summary/{key}: {len(df)} rows')

        raw_state = load_raw(path, 'Initiations by State')
        df_state = parse_initiations_by_state(raw_state, quarter)
        if df_state is not None:
            acc['initiations_by_state'].append(df_state)
            print(f'  Initiations by State: {len(df_state)} rows')

        raw_parties = load_raw(path, 'Top Disputing Parties')
        df_init = parse_top_initiating(raw_parties, quarter)
        if df_init is not None:
            acc['top_initiating_parties'].append(df_init)
            print(f'  Top Initiating: {len(df_init)} rows')

        df_noninit = parse_top_noninitiating(raw_parties, quarter)
        if df_noninit is not None:
            acc['top_noninitiating_parties'].append(df_noninit)
            print(f'  Top Non-Initiating: {len(df_noninit)} rows')

        raw_outcomes = load_raw(path, 'Payment Determination Outcomes')
        df_outcomes = parse_payment_determination_outcomes(raw_outcomes, quarter)
        if df_outcomes is not None:
            acc['payment_determination_outcomes'].append(df_outcomes)
            print(f'  Payment Outcomes: {len(df_outcomes)} rows')

        df_cost = parse_qpa_by_cost_band(raw_outcomes, quarter)
        if df_cost is not None:
            acc['qpa_by_cost_band'].append(df_cost)
            print(f'  QPA by Cost Band: {len(df_cost)} rows')

        df_spec = parse_qpa_by_specialty(raw_outcomes, quarter)
        if df_spec is not None:
            acc['qpa_by_specialty'].append(df_spec)
            print(f'  QPA by Specialty: {len(df_spec)} rows')

    print('\n=== Saving parquet files ===')
    for key, dfs in acc.items():
        if not dfs:
            print(f'  SKIPPED (no data): {key}')
            continue
        combined = pd.concat(dfs, ignore_index=True)
        out_path = out(f'supp_{key}.parquet')
        combined.to_parquet(out_path, compression='snappy', index=False)
        print(f'  supp_{key}: {len(combined)} rows  →  {out_path}')


if __name__ == '__main__':
    build_supplemental()
