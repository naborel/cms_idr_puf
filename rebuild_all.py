"""
Streaming full rebuild of the three consolidated parquet files.

Why this exists rather than just running build_parquets.py:
  build_parquets.py loads every quarter into memory and concatenates before writing.
  That needs many GB. This runs the same normalisation, but streams: one batch at a
  time, one quarter-part at a time, so peak memory stays flat.

It reuses build_parquets' own normalize/convert/map functions, so the corrected
percent handling (_parse_numeric_smart) applies here identically.

Source selection:
  2023, 2024  -> xlsx (only format CMS shipped)
  2025        -> CSV  (the 2025 workbooks split OON/QPA across numbered sheets)

Output schema is pinned to the EXISTING parquet's schema so the result is a drop-in
replacement for load_parquet.py / puf_checker.py / build_dashboard_data.py.

Run:  nohup python rebuild_all.py > rebuild.log 2>&1 &
"""
import os, sys, gc, time, glob, traceback
import pandas as pd, numpy as np, pyarrow as pa, pyarrow.parquet as pq, openpyxl

import build_parquets as B
from idr_mappings import apply_all_maps, add_outcome_bucket

RAW        = "Raw Files"
PARTS      = os.path.join(os.path.expanduser("~"), "idr_parts")   # VM scratch, outside the user's folder
OUT_DIR    = "parquet"
XLSX_BATCH = 100_000
CSV_CHUNK  = 250_000
os.makedirs(PARTS, exist_ok=True)

SHEETS = {"oon": B.SHEET_OON, "qpa": B.SHEET_QPA, "air": B.SHEET_AIR}

# pandas applies these as na_values automatically in read_csv/read_excel. The xlsx path
# here reads raw cells via openpyxl (to stream within the memory budget), which bypasses
# that, so apply them explicitly -- otherwise 'N/A' survives as a literal string and the
# parse report reports tens of thousands of false "lost" values.
PANDAS_NA = ['', '#N/A', '#N/A N/A', '#NA', '-1.#IND', '-1.#QNAN', '-NaN', '-nan',
             '1.#IND', '1.#QNAN', '<NA>', 'N/A', 'NA', 'NULL', 'NaN', 'None',
             'n/a', 'nan', 'null']

def x(y, name):  return f"{RAW}/{y}/{name}"
def c25(q, part): return f"{RAW}/2025/Federal IDR PUF for 2025 {q} - {part} (As of January 21, 2026).csv"
def c26(q, part): return f"{RAW}/2025/Federal IDR PUF for 2025 {q} - {part} (As of January 26, 2026) (CSV).csv"

# quarter tag format is "2023Q1" -- year first (ADDING_A_QUARTER.md "Quarter format")
MANIFEST = [
  ("2023Q1", "xlsx", x(2023, "2023-q1-federal-idr-puf_0.xlsx")),
  ("2023Q2", "xlsx", x(2023, "Federal-IDR-PUF-for-2023-Q2.xlsx")),
  ("2023Q3", "xlsx", x(2023, "Federal IDR PUF for 2023 Q3.xlsx")),
  ("2023Q4", "xlsx", x(2023, "Federal IDR PUF for 2023 Q4.xlsx")),
  ("2024Q1", "xlsx", x(2024, "federal-idr-puf-for-2024-q1-as-of-march-18-2025.xlsx")),
  ("2024Q2", "xlsx", x(2024, "federal-idr-puf-for-2024-q2-as-of-march-18-2025.xlsx")),
  ("2024Q3", "xlsx", x(2024, "federal-idr-puf-for-2024-q3-as-of-may-28-2025.xlsx")),
  ("2024Q4", "xlsx", x(2024, "federal-idr-puf-for-2024-q4-as-of-may-28-2025.xlsx")),
  ("2025Q1", "csv", {"oon": c25("Q1", "OON Emergency & Non-Emergency"),
                     "qpa": c25("Q1", "QPA and Offers"),
                     "air": c25("Q1", "OON Air Ambulance")}),
  ("2025Q2", "csv", {"oon": c25("Q2", "OON Emergency & Non-Emergency"),
                     "qpa": c25("Q2", "QPA and Offers"),
                     "air": c25("Q2", "OON Air Ambulance")}),
  ("2025Q3", "csv", {"oon": c26("Q3", "OON Emergency & Non-Emergency"),
                     "qpa": c26("Q3", "QPA and Offers"),
                     "air": c26("Q3", "OON Air Ambulance")}),
  ("2025Q4", "csv", {"oon": c26("Q4", "OON Emergency & Non-Emergency"),
                     "qpa": c26("Q4", "QPA and Offers"),
                     "air": c26("Q4", "OON Air Ambulance")}),
]

def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)

# ── target schema, pinned to the existing parquet ────────────────────────────
def target_schema(kind):
    p = os.path.join(OUT_DIR, f"{kind}_all_quarters.parquet")
    return pq.read_schema(p)

def conform(df, schema, qtag, kind, seen_extra):
    """Reindex to the target columns and coerce dtypes so every part is identical."""
    names = list(schema.names)
    extra = [c for c in df.columns if c not in names]
    for e in extra:
        if e not in seen_extra:
            log(f"    NOTE {kind} {qtag}: column not in target schema, dropped: {e!r}")
            seen_extra.add(e)
    df = df.reindex(columns=names)
    for f in schema:
        s = df[f.name]
        if pa.types.is_floating(f.type) or pa.types.is_integer(f.type):
            df[f.name] = pd.to_numeric(s, errors="coerce")
        else:
            # target is string: stringify explicitly. Some quarters ship codes/vehicle
            # types as ints, which pyarrow rejects against a string field.
            df[f.name] = s.astype(str).where(s.notna(), None)
    return pa.Table.from_pandas(df, schema=schema, preserve_index=False, safe=False)

# ── batch producers (resumable) ──────────────────────────────────────────────
def xlsx_batches(path, sheet, skip=0, batch=XLSX_BATCH):
    """Stream a sheet in row batches. `skip` batches are consumed and discarded so a
    partially-completed quarter can resume without redoing the expensive work."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    it = ws.iter_rows(values_only=True)
    hdr = [(str(c).strip() if c is not None else f"_c{i}") for i, c in enumerate(next(it))]
    skip_rows = skip * batch
    for _ in range(skip_rows):
        if next(it, None) is None:
            break
    buf = []
    for r in it:
        buf.append(r)
        if len(buf) >= batch:
            yield pd.DataFrame(buf, columns=hdr).replace(PANDAS_NA, np.nan); buf = []; gc.collect()
    if buf:
        yield pd.DataFrame(buf, columns=hdr).replace(PANDAS_NA, np.nan)
    wb.close()


def csv_batches(path, skip=0, chunk=CSV_CHUNK):
    skiprows = range(1, 1 + skip * chunk) if skip else None
    for d in pd.read_csv(path, low_memory=False, chunksize=chunk, skiprows=skiprows):
        yield d


# ── per-quarter/kind part build, checkpointed per batch ──────────────────────
def build_part(qtag, kind, src, sheet=None, budget=150):
    """Write one parquet file per batch into PARTS/<kind>_<qtag>/.
    Returns True when the quarter/kind is fully complete."""
    d = os.path.join(PARTS, f"{kind}_{qtag}")
    done = os.path.join(d, "_DONE")
    if os.path.exists(done):
        return True
    if not os.path.exists(src):
        log(f"  {kind} {qtag}: SOURCE MISSING {src}"); return True
    os.makedirs(d, exist_ok=True)

    existing = sorted(glob.glob(os.path.join(d, "batch_*.parquet")))
    skip = len(existing)
    if skip:
        log(f"  {kind} {qtag}: resuming after {skip} batch(es)")

    schema = target_schema(kind)
    gen = (xlsx_batches(src, sheet, skip=skip) if sheet else csv_batches(src, skip=skip))
    i = skip; n = 0; seen_extra = set(); t0 = time.time(); finished = True
    for raw in gen:
        df = B.normalize(raw, qtag)
        if kind == "qpa":
            df = B.convert_numeric_cols(df, B.QPA_NUMERIC_PATTERNS,
                                        exclude=B.QPA_NUMERIC_EXCLUDE, label=f"{kind} {qtag}")
        else:
            df = B.convert_numeric_cols(df, B.NUMERIC_PATTERNS, label=f"{kind} {qtag}")
            df = apply_all_maps(df)
            df = add_outcome_bucket(df)
        tbl = conform(df, schema, qtag, kind, seen_extra)
        p = os.path.join(d, f"batch_{i:04d}.parquet")
        pq.write_table(tbl, p + ".tmp", compression="snappy")
        os.replace(p + ".tmp", p)
        n += len(df); i += 1
        log(f"  {kind} {qtag}: batch {i} (+{len(df):,} rows, {time.time()-t0:.0f}s)")
        del df, tbl, raw; gc.collect()
        if time.time() - t0 > budget:
            finished = False
            log(f"  {kind} {qtag}: PAUSED at batch {i} (time budget) -- re-run to continue")
            break
    if finished:
        open(done, "w").write(str(i))
        log(f"  {kind} {qtag}: COMPLETE ({i} batches)")
    return finished


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarters", default="all")
    ap.add_argument("--kinds", default="oon,qpa,air")
    ap.add_argument("--budget", type=int, default=150)
    a = ap.parse_args()
    qsel = None if a.quarters == "all" else set(a.quarters.split(","))
    ksel = a.kinds.split(",")
    t0 = time.time()
    for qtag, ftype, src in MANIFEST:
        if qsel and qtag not in qsel:
            continue
        for kind in ksel:
            if time.time() - t0 > a.budget:
                log("TIME BUDGET REACHED -- re-run to continue"); return
            try:
                ok = build_part(qtag, kind, src if ftype == "xlsx" else src[kind],
                                sheet=SHEETS[kind] if ftype == "xlsx" else None,
                                budget=a.budget - (time.time() - t0))
                if not ok:
                    log("PAUSED -- re-run to continue"); return
            except Exception:
                log(f"  !! {kind} {qtag} FAILED"); traceback.print_exc()
    log("ALL PARTS COMPLETE")


if __name__ == "__main__":
    main()
