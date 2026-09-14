#!/usr/bin/env python3
"""
Publish the rebuilt parquets into parquet/ for commit.

Two things happen here, and both are deliberate:

1. RECOMPRESSION to ZSTD. The build scripts write SNAPPY because it is fast and this repo
   rebuilds often. SNAPPY is the wrong trade for a file that is going to sit in Git LFS and be
   downloaded by every clone: ZSTD is ~27% smaller on this data (measured on a full quarter of
   the OON file) at no cost to read speed for analytical scans. 460 MB becomes ~337 MB, which
   matters because GitHub's free LFS allowance is 1,024 MB total and LFS keeps every version
   ever pushed.

2. VERIFICATION before anything is overwritten. Row counts and column sets are compared against
   the files already in parquet/. A publish that silently drops rows is worse than no publish,
   so a mismatch aborts instead of writing.

Usage:   python publish_parquets.py            # verify + write
         python publish_parquets.py --check    # verify only, touch nothing
"""
import duckdb, os, shutil, sys, time

SRC, DST = "parquet_rebuilt", "parquet"
FILES = ["oon_all_quarters.parquet", "qpa_all_quarters.parquet", "air_all_quarters.parquet"]
EXPECTED_MIN = {"oon_all_quarters.parquet": 8_233_903,      # verified against the 12 raw quarters
                "qpa_all_quarters.parquet": 8_338_286,
                "air_all_quarters.parquet":   104_383}

check_only = "--check" in sys.argv
con = duckdb.connect(); con.execute("SET memory_limit='2.5GB'")
q = lambda s: con.execute(s).fetchone()

print("Verifying rebuilt files against what is currently published\n")
print("%-28s %>0s" % ("file", ""))
ok = True
for f in FILES:
    src, dst = os.path.join(SRC, f), os.path.join(DST, f)
    if not os.path.exists(src):
        print("  %-28s MISSING in %s" % (f, SRC)); ok = False; continue
    n_src = q(f"SELECT count(*) FROM read_parquet('{src}')")[0]
    c_src = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{src}')").fetchall()}
    n_dst = c_dst = None
    if os.path.exists(dst):
        n_dst = q(f"SELECT count(*) FROM read_parquet('{dst}')")[0]
        c_dst = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{dst}')").fetchall()}
    exp = EXPECTED_MIN.get(f)
    bad = []
    if exp and n_src < exp:            bad.append("fewer rows than the verified baseline (%s < %s)" % (f"{n_src:,}", f"{exp:,}"))
    if n_dst is not None and n_src < n_dst: bad.append("fewer rows than the published file (%s < %s)" % (f"{n_src:,}", f"{n_dst:,}"))
    if c_dst and (c_dst - c_src):      bad.append("drops columns: %s" % sorted(c_dst - c_src))
    print("  %-28s %s rows" % (f, f"{n_src:,}"), end="")
    if c_dst and (c_src - c_dst): print("   (+%d new columns)" % len(c_src - c_dst), end="")
    print()
    for b in bad: print("      ABORT: " + b); ok = False

if not ok:
    sys.exit("\nVerification failed — nothing written.")
if check_only:
    sys.exit("\nVerification passed. Re-run without --check to publish.")

print("\nRecompressing to ZSTD and writing into %s/\n" % DST)
before = after = 0
for f in FILES:
    src, dst = os.path.join(SRC, f), os.path.join(DST, f)
    t = time.time()
    if os.path.exists(dst): before += os.path.getsize(dst)
    tmp = dst + ".tmp"
    con.execute(f"""COPY (SELECT * FROM read_parquet('{src}'))
        TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 250000)""")
    # only replace once the new file is written and readable
    assert q(f"SELECT count(*) FROM read_parquet('{tmp}')")[0] == q(f"SELECT count(*) FROM read_parquet('{src}')")[0]
    os.replace(tmp, dst)
    sz = os.path.getsize(dst); after += sz
    print("  %-28s %7.1f MB   [%.0fs]" % (f, sz/1048576, time.time()-t))
print("\n  total %.1f MB (was %.1f MB in the repo)" % (after/1048576, before/1048576))
print("\nNext:  git add parquet/ && git commit && git push")
