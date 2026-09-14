#!/usr/bin/env python3
"""
Publish the rebuilt parquets into parquet/ for commit.

Two things happen here, and both are deliberate:

1. RECOMPRESSION to ZSTD. The build scripts write SNAPPY because it is fast and this repo
   rebuilds often. SNAPPY is the wrong trade for a file that lives in Git LFS and is downloaded
   by every clone: ZSTD is ~27% smaller on this data at no cost to analytical read speed.
   ~460 MB becomes ~337 MB, which matters because GitHub's free LFS allowance is 1,024 MB and
   LFS keeps every version ever pushed.

2. VERIFICATION before anything is overwritten. Row counts and column sets are compared against
   the files already in parquet/. A publish that silently drops rows is worse than no publish,
   so a mismatch aborts instead of writing.

Uses pyarrow only (ships with Anaconda) and streams row group by row group, so peak memory is
one row group rather than the whole 350 MB file.

Usage:   python publish_parquets.py --check    # verify only, touch nothing
         python publish_parquets.py            # verify, then recompress and write
"""
import os, sys, time

try:
    import pyarrow.parquet as pq
except ImportError:
    sys.exit("pyarrow is required.\n"
             "  conda install -y pyarrow        (Anaconda)\n"
             "  python -m pip install pyarrow   (otherwise)")

SRC, DST = "parquet_rebuilt", "parquet"
FILES = ["oon_all_quarters.parquet", "qpa_all_quarters.parquet", "air_all_quarters.parquet"]
# verified against the 12 raw CMS quarters; a rebuild below these has lost data
BASELINE = {"oon_all_quarters.parquet": 8_233_903,
            "qpa_all_quarters.parquet": 8_338_286,
            "air_all_quarters.parquet":   104_383}

check_only = "--check" in sys.argv

def info(path):
    """Row count and column names straight from the footer — no data is read."""
    f = pq.ParquetFile(path)
    return f.metadata.num_rows, set(f.schema_arrow.names)

if not os.path.isdir(SRC):
    sys.exit("No %s/ directory here. Run this from the repo root." % SRC)

print("Verifying %s/ against what is currently published in %s/\n" % (SRC, DST))
ok = True
for name in FILES:
    src, dst = os.path.join(SRC, name), os.path.join(DST, name)
    if not os.path.exists(src):
        print("  %-28s MISSING from %s/" % (name, SRC)); ok = False; continue
    n_src, c_src = info(src)
    print("  %-28s %13s rows" % (name, f"{n_src:,}"), end="")
    problems = []
    base = BASELINE.get(name)
    if base and n_src < base:
        problems.append("below the verified baseline (%s < %s)" % (f"{n_src:,}", f"{base:,}"))
    if os.path.exists(dst):
        n_dst, c_dst = info(dst)
        if n_src < n_dst:
            problems.append("fewer rows than the published file (%s < %s)" % (f"{n_src:,}", f"{n_dst:,}"))
        missing = c_dst - c_src
        if missing:
            problems.append("drops columns: %s" % sorted(missing))
        added = c_src - c_dst
        if added: print("   (+%d new column%s)" % (len(added), "" if len(added)==1 else "s"), end="")
    else:
        print("   (new file)", end="")
    print()
    for p in problems:
        print("      ABORT: " + p); ok = False

if not ok:
    sys.exit("\nVerification failed — nothing written.")
if check_only:
    print("\nVerification passed. Re-run without --check to publish.")
    sys.exit(0)

print("\nRecompressing to ZSTD into %s/\n" % DST)
before = after = 0
for name in FILES:
    src, dst, tmp = os.path.join(SRC, name), os.path.join(DST, name), os.path.join(DST, name + ".tmp")
    t = time.time()
    if os.path.exists(dst): before += os.path.getsize(dst)
    reader = pq.ParquetFile(src)
    writer = None
    written = 0
    try:
        # one row group at a time: constant memory regardless of file size
        for i in range(reader.metadata.num_row_groups):
            tbl = reader.read_row_group(i)
            if writer is None:
                writer = pq.ParquetWriter(tmp, tbl.schema, compression="zstd", compression_level=9)
            writer.write_table(tbl)
            written += tbl.num_rows
    finally:
        if writer is not None: writer.close()
    if written != reader.metadata.num_rows:
        os.remove(tmp)
        sys.exit("ABORT: wrote %s rows but source has %s" % (f"{written:,}", f"{reader.metadata.num_rows:,}"))
    if info(tmp)[0] != reader.metadata.num_rows:
        os.remove(tmp); sys.exit("ABORT: %s failed readback" % name)
    os.replace(tmp, dst)                      # only swap once the new file is proven
    sz = os.path.getsize(dst); after += sz
    print("  %-28s %7.1f MB   [%.0fs]" % (name, sz/1048576, time.time()-t))

print("\n  total %.1f MB" % (after/1048576) + (" (was %.1f MB)" % (before/1048576) if before else ""))
print("\nNext:  git add -A && git commit -m \"Rebuild parquets\" && git push")
