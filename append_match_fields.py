#!/usr/bin/env python3
"""
Append the recovered QPA / offer dollars onto the published OON parquet.

Reads  parquet/oon_all_quarters.parquet      (unchanged, from the repo)
       idr_match_ladder.parquet              (this handoff)
Writes parquet_rebuilt/oon_all_quarters.parquet

Then run the repo's own guard before publishing:
    python publish_parquets.py --check
    python publish_parquets.py

The join key is (Dispute Number, DLI Number, Quarter), verified unique across all
8,233,903 OON rows. (Dispute Number, DLI Number) alone is NOT unique -- 8,430 pairs
appear twice because a line republished in a later quarter keeps its identifiers.

Needs duckdb:  python -m pip install duckdb
"""
import os, sys, duckdb

SRC   = "parquet/oon_all_quarters.parquet"
MATCH = sys.argv[1] if len(sys.argv) > 1 else "idr_match_ladder.parquet"
DST   = "parquet_rebuilt/oon_all_quarters.parquet"

for p in (SRC, MATCH):
    if not os.path.exists(p):
        sys.exit("missing: %s  (run this from the repo root)" % p)
os.makedirs("parquet_rebuilt", exist_ok=True)

c = duckdb.connect()
c.execute("set memory_limit='4GB'; set preserve_insertion_order=false")

base = [r[0] for r in c.execute("describe select * from read_parquet('%s')" % SRC).fetchall()]
new  = ["Match Rung","Match Rung Name","Ratios Used","Candidates in Tie","Dollar Match Type",
        "QPA ($)","Median QPA ($)","Provider/Facility Offer ($)","Health Plan/Issuer Offer ($)",
        "Prevailing Offer ($)","Median Tied","Provider Offer Tied","Plan Offer Tied"]

clash = [x for x in new if x in base]
if clash:
    sys.exit("ABORT: these column names already exist in %s:\n  %s\n"
             "Rename or drop them first -- two columns with one name is worse than none."
             % (SRC, "\n  ".join(clash)))

n_src = c.execute("select count(*) from read_parquet('%s')" % SRC).fetchone()[0]
print("source rows      %s" % format(n_src, ","))

# the key must be unique on the source, or the join would multiply rows
d = c.execute('select count(distinct ("Dispute Number","DLI Number","Quarter")) '
              "from read_parquet('%s')" % SRC).fetchone()[0]
if d != n_src:
    sys.exit("ABORT: (Dispute Number, DLI Number, Quarter) is not unique on the source "
             "(%s distinct vs %s rows). The join would duplicate rows." % (format(d,','), format(n_src,',')))
print("key unique       yes")

sel = ", ".join('m."%s"' % x for x in new)
c.execute("""copy (
  select o.*, %s, (m."QPA ($)" is not null) as "Dollars Matched"
  from read_parquet('%s') o
  left join read_parquet('%s') m
    on  m."Dispute Number" = o."Dispute Number"
    and m."DLI Number"     = o."DLI Number"
    and m."Quarter"        = o."Quarter"
) to '%s' (format parquet, compression zstd)""" % (sel, SRC, MATCH, DST))

n_dst = c.execute("select count(*) from read_parquet('%s')" % DST).fetchone()[0]
n_hit = c.execute("""select count(*) from read_parquet('%s') where "Dollars Matched" """ % DST).fetchone()[0]

print("written rows     %s" % format(n_dst, ","))
print("dollars attached %s  (%.1f%%)" % (format(n_hit, ","), 100.0*n_hit/n_dst))
print("columns          %d -> %d" % (len(base), len(base)+len(new)+1))
print("size             %.1f MB" % (os.path.getsize(DST)/1e6))

if n_dst != n_src:
    sys.exit("\nABORT: row count changed (%s -> %s). Do not publish this." % (format(n_src,','), format(n_dst,',')))
print("\nrow count preserved. Next:  python publish_parquets.py --check")
print("\n*** Before you commit: delete %s from the repo folder. ***" % MATCH)
print("    It is a 132 MB *.parquet, so `git add -A` would push it into LFS as well,")
print("    and it is only an input to this script -- it does not belong in the repo.")
