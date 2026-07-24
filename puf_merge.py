"""
PUF Quarter Merge
===================
Merges a transformed new-quarter DataFrame into the existing parquet table
and writes the result back out. Writes to a temp file first and atomically
swaps it into place, so a failed/interrupted write never corrupts the
existing parquet.

Usage:
    from puf_checker import check_file
    from puf_transform import transform_quarter
    from puf_merge import merge_quarter

    report = check_file(raw_path, file_type="oon", quarter="2025Q3")
    report.summary()  # review before proceeding

    new_oon = transform_quarter(raw_path, file_type="oon", quarter="2025Q3")

    merge_quarter(new_oon, file_type="oon", quarter="2025Q3")               # dry run (default)
    merge_quarter(new_oon, file_type="oon", quarter="2025Q3", dry_run=False)  # actually writes

Nothing here touches git -- committing/pushing the updated parquet files is a
separate, explicit step.
"""

import os
import gc
import time
import pandas as pd
import pyarrow.parquet as pq

PARQUET_DIR = "parquet"
FILE_PARQUET = {
    "oon": "oon_all_quarters.parquet",
    "qpa": "qpa_all_quarters.parquet",
    "air": "air_all_quarters.parquet",
}
ENGINE = "fastparquet"  # matches load_parquet.py


def merge_quarter(new_df, file_type, quarter, dry_run=True):
    """
    new_df: output of puf_transform.transform_quarter()
    file_type: 'oon' | 'qpa' | 'air'
    quarter: e.g. '2025Q3' -- must match the format already in the parquet
    dry_run: if True (default), reports what would happen but writes nothing.
             Pass dry_run=False to actually overwrite the parquet file.
    """
    if file_type not in FILE_PARQUET:
        raise ValueError(f"file_type must be one of {list(FILE_PARQUET)}, got {file_type!r}")

    parquet_path = os.path.join(PARQUET_DIR, FILE_PARQUET[file_type])

    pf = pq.ParquetFile(parquet_path)
    old_columns = set(pf.schema_arrow.names)
    old_row_count = pf.metadata.num_rows

    existing_quarters = pq.read_table(parquet_path, columns=["Quarter"]).to_pandas()["Quarter"]
    if (existing_quarters == quarter).any():
        raise ValueError(
            f"Quarter '{quarter}' is already present in {parquet_path} "
            f"({(existing_quarters == quarter).sum():,} rows). Refusing to merge a duplicate."
        )

    if "Quarter" not in new_df.columns or (new_df["Quarter"] != quarter).any():
        raise ValueError("new_df must have every row tagged with Quarter == the quarter being merged.")

    new_columns = set(new_df.columns)
    added = sorted(new_columns - old_columns)
    missing = sorted(old_columns - new_columns)

    print(f"=== Merge: {file_type.upper()} - {quarter} ===")
    print(f"Existing rows: {old_row_count:,}")
    print(f"New rows:      {len(new_df):,}")
    print(f"Combined rows: {old_row_count + len(new_df):,}")
    if added:
        print(f"Columns added by this quarter (NaN-backfilled for history): {added}")
    if missing:
        print(f"Columns this quarter doesn't have (NaN for these new rows): {missing}")

    if dry_run:
        print("\n[DRY RUN] No files written. Call with dry_run=False to write.")
        return None

    old_df = pd.read_parquet(parquet_path, engine=ENGINE)
    combined = pd.concat([old_df, new_df], ignore_index=True)

    expected = old_row_count + len(new_df)
    assert len(combined) == expected, f"row count mismatch after concat: got {len(combined)}, expected {expected}"

    # fastparquet can back the read DataFrame with a memory-mapped view of
    # parquet_path, which keeps a handle on it open until old_df is actually
    # collected. Drop the reference and force collection before trying to
    # replace that same path, or os.replace reliably fails with WinError 5
    # (Access denied) no matter how long we wait/retry -- this isn't an
    # external lock, it's our own process.
    del old_df
    gc.collect()

    tmp_path = parquet_path + ".tmp"
    combined.to_parquet(tmp_path, compression="snappy", index=False)

    # os.replace(tmp_path, parquet_path) reliably fails with WinError 5
    # (Access denied) right after a file is written -- confirmed by testing
    # that it's elapsed wall-clock time that fixes it, not a fresh process or
    # dropping in-process references, and observed even on small (~4MB)
    # files, so file size isn't the driver either. Something external holds
    # a brief lock on newly-written files in this environment (antivirus,
    # an indexer, or the dev environment's own file watcher) that clears on
    # its own, sometimes taking several minutes. Retry with real patience.
    max_attempts = 30
    for attempt in range(max_attempts):
        try:
            os.replace(tmp_path, parquet_path)
            break
        except PermissionError:
            if attempt == max_attempts - 1:
                raise
            time.sleep(30)

    print(f"\nWrote {parquet_path}  ({len(combined):,} total rows)")
    return combined
