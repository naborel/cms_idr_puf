#!/usr/bin/env python3
"""
Reconcile the published parquets against the raw CMS files.

The validation notebook checks the parquet against itself and against reference figures
derived from it -- that proves internal consistency, not fidelity to the source. This checks
the thing the notebook cannot: that every row and every column in the raw CMS releases
actually made it into the parquet.

Two failure modes it is built to catch, both structural to how rebuild_all.py works:

1. DROPPED COLUMNS. conform() pins each batch to target_schema(), which is read from the
   PREVIOUS parquet. Any column CMS adds that is not already in that schema is silently
   dropped by df.reindex(columns=names). It logs a NOTE, but rebuild.log is overwritten on
   every run, so the evidence does not survive. This script compares raw headers to parquet
   columns directly.

2. SILENTLY SKIPPED QUARTERS. build_part() returns True -- "complete" -- when the source
   file is missing, so a manifest typo or an unrestored raw file produces zero rows for that
   quarter and the build still reports success.

Row counts use pyarrow's CSV reader and openpyxl rather than a naive line count, because the
PUF carries free-text fields that contain embedded newlines.

Usage:
    py3 reconcile_raw.py                  # all quarters, all three datasets
    py3 reconcile_raw.py --kinds oon      # one dataset
    py3 reconcile_raw.py --quarters 2024Q3,2024Q4
    py3 reconcile_raw.py --exact          # count xlsx rows instead of trusting the
                                          #   sheet dimension record (much slower)
"""
import os, sys, time, argparse

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    import pyarrow.csv as pacsv
except ImportError:
    sys.exit("pyarrow is required.  conda install -y pyarrow")
try:
    import openpyxl
except ImportError:
    openpyxl = None

RAW, OUT = "Raw Files", "parquet"

def x(y, name):   return os.path.join(RAW, str(y), name)
def c25(q, part): return os.path.join(RAW, "2025", f"Federal IDR PUF for 2025 {q} - {part} (As of January 21, 2026).csv")
def c26(q, part): return os.path.join(RAW, "2025", f"Federal IDR PUF for 2025 {q} - {part} (As of January 26, 2026) (CSV).csv")

# Mirrors rebuild_all.MANIFEST. If that file changes, change this with it.
MANIFEST = [
  ("2023Q1","xlsx", x(2023,"2023-q1-federal-idr-puf_0.xlsx")),
  ("2023Q2","xlsx", x(2023,"Federal-IDR-PUF-for-2023-Q2.xlsx")),
  ("2023Q3","xlsx", x(2023,"Federal IDR PUF for 2023 Q3.xlsx")),
  ("2023Q4","xlsx", x(2023,"Federal IDR PUF for 2023 Q4.xlsx")),
  ("2024Q1","xlsx", x(2024,"federal-idr-puf-for-2024-q1-as-of-march-18-2025.xlsx")),
  ("2024Q2","xlsx", x(2024,"federal-idr-puf-for-2024-q2-as-of-march-18-2025.xlsx")),
  ("2024Q3","xlsx", x(2024,"federal-idr-puf-for-2024-q3-as-of-may-28-2025.xlsx")),
  ("2024Q4","xlsx", x(2024,"federal-idr-puf-for-2024-q4-as-of-may-28-2025.xlsx")),
  ("2025Q1","csv", {"oon":c25("Q1","OON Emergency & Non-Emergency"),
                    "qpa":c25("Q1","QPA and Offers"), "air":c25("Q1","OON Air Ambulance")}),
  ("2025Q2","csv", {"oon":c25("Q2","OON Emergency & Non-Emergency"),
                    "qpa":c25("Q2","QPA and Offers"), "air":c25("Q2","OON Air Ambulance")}),
  ("2025Q3","csv", {"oon":c26("Q3","OON Emergency & Non-Emergency"),
                    "qpa":c26("Q3","QPA and Offers"), "air":c26("Q3","OON Air Ambulance")}),
  ("2025Q4","csv", {"oon":c26("Q4","OON Emergency & Non-Emergency"),
                    "qpa":c26("Q4","QPA and Offers"), "air":c26("Q4","OON Air Ambulance")}),
]
SHEETS = {"oon":"OON Emergency and Non-Emergency", "qpa":"QPA and Offers", "air":"OON Air Ambulance"}

# Engineered by the build, so absent from raw by design -- never report these as extra.
ENGINEERED = {"Quarter","Provider_Group","Provider_Category","Carrier_Group",
              "Anthem_Flag","Outcome_Bucket"}

# normalize() rewrites this variant before the parquet is written (2023 Q1-Q2 -> Q3 onward).
def canon(c):
    return (c.strip().replace("as Percent of QPA","as % of QPA")
                     .replace("As Percent of QPA","as % of QPA"))

def csv_scan(path):
    """Row count and header via pyarrow -- quoting-aware, so embedded newlines are safe.

    Every column is forced to string. Type inference would otherwise abort on CMS
    suppression markers ('N/R', '^', '+', '*') sitting in numeric columns, and we only
    need to count rows here, not interpret them."""
    with pacsv.open_csv(path) as r:
        names = list(r.schema.names)
    opts = pacsv.ConvertOptions(column_types={c: pa.string() for c in names},
                                null_values=[], strings_can_be_null=False)
    n = 0
    with pacsv.open_csv(path, convert_options=opts) as r:
        for batch in r:
            n += batch.num_rows
    return n, [canon(c) for c in names]

def xlsx_scan(path, sheet, exact=False):
    if openpyxl is None:
        return None, None, "openpyxl not installed"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    cands = [s for s in wb.sheetnames if s.strip().lower() == sheet.strip().lower()]
    if not cands:                      # 2023Q2 ships a leading space / alternate name
        cands = [s for s in wb.sheetnames if sheet.strip().lower() in s.strip().lower()]
    if not cands:
        wb.close(); return None, None, f"sheet {sheet!r} not found in {wb.sheetnames}"
    ws = wb[cands[0]]
    rows = ws.iter_rows(values_only=True)
    header = [canon(str(c)) for c in next(rows) if c is not None]
    if exact:
        n = sum(1 for _ in rows)
    else:
        n = (ws.max_row or 1) - 1      # dimension record, minus the header
    wb.close()
    return n, header, None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kinds", default="oon,qpa,air")
    ap.add_argument("--quarters", default="all")
    ap.add_argument("--exact", action="store_true",
                    help="count xlsx rows rather than trusting the sheet dimension record")
    a = ap.parse_args()
    kinds = a.kinds.split(",")
    qsel  = None if a.quarters == "all" else set(a.quarters.split(","))

    pq_cols, pq_rows = {}, {}
    for kind in kinds:
        p = os.path.join(OUT, f"{kind}_all_quarters.parquet")
        if not os.path.exists(p):
            sys.exit(f"missing {p} -- run this from the repo root")
        f = pq.ParquetFile(p)
        pq_cols[kind] = set(f.schema_arrow.names)
        t = f.read(columns=["Quarter"]).to_pandas()["Quarter"]
        pq_rows[kind] = t.value_counts().to_dict()
        print(f"{kind}: {f.metadata.num_rows:,} rows, {len(pq_cols[kind])} columns")

    print()
    hdr = f"{'quarter':8} {'kind':5} {'raw rows':>13} {'parquet':>13} {'delta':>11}  columns"
    print(hdr); print("-"*len(hdr)+"-"*30)

    problems, missing_src = [], []
    for qtag, ftype, src in MANIFEST:
        if qsel and qtag not in qsel: continue
        for kind in kinds:
            path = src if ftype == "xlsx" else src[kind]
            got  = pq_rows[kind].get(qtag, 0)
            if not os.path.exists(path):
                print(f"{qtag:8} {kind:5} {'SOURCE MISSING':>13} {got:>13,}")
                missing_src.append((qtag, kind, path)); continue
            t0 = time.time()
            if ftype == "csv":
                n, names = csv_scan(path); err = None
            else:
                n, names, err = xlsx_scan(path, SHEETS[kind], exact=a.exact)
            if err:
                print(f"{qtag:8} {kind:5} {'ERROR':>13} {got:>13,}   {err}")
                problems.append(f"{qtag}/{kind}: {err}"); continue

            dropped = [c for c in names if c not in pq_cols[kind]]
            delta   = got - n
            note    = "ok" if not dropped else f"DROPPED {dropped}"
            flag    = "" if delta == 0 else "  <-- ROW MISMATCH"
            print(f"{qtag:8} {kind:5} {n:>13,} {got:>13,} {delta:>+11,}  {note}{flag}"
                  f"   [{time.time()-t0:.0f}s]")
            if dropped: problems.append(f"{qtag}/{kind}: columns in raw but not in parquet: {dropped}")
            if delta:   problems.append(f"{qtag}/{kind}: {abs(delta):,} rows "
                                        f"{'missing from' if delta<0 else 'extra in'} the parquet")

    print()
    if missing_src:
        print("RAW SOURCES NOT FOUND (cannot verify these quarters):")
        for q,k,p in missing_src: print(f"  {q}/{k}  {p}")
        print()
    if problems:
        print("=" * 78); print("  RECONCILIATION FAILED"); print("=" * 78)
        for p in problems: print("  * " + p)
    elif not missing_src:
        print("=" * 78)
        print("  Every raw row and every raw column is accounted for in the parquets.")
        print("=" * 78)
    else:
        print("No discrepancies in the quarters that could be checked.")

if __name__ == "__main__":
    main()
