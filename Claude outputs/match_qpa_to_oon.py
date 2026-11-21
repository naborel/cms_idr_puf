#!/usr/bin/env python3
"""
Link the CMS QPA file back to dispute numbers in the OON file.

CMS strips Dispute Number and DLI Number from the QPA file, so the dollars it carries
(QPA, provider offer, plan offer, prevailing offer) cannot be joined to anything. This
recovers the join by fingerprinting each line on quantities both files express.

    py3 match_qpa_to_oon.py                      # Dallas
    py3 match_qpa_to_oon.py --region chicago
    py3 match_qpa_to_oon.py --region ''          # nationwide (slow, lots of memory)

KNOWN LIMIT — the output is contested determinations only. The fingerprint needs BOTH
offers, and on a default the missing party never submitted one. ~87% of default lines
are dropped. Do not compute default rates or provider win rates from the result.
"""
import argparse, duckdb, sys

ap = argparse.ArgumentParser()
ap.add_argument("--region", default="dallas", help="substring matched against Geographical Region")
ap.add_argument("--oon", default="parquet/oon_all_quarters.parquet")
ap.add_argument("--qpa", default="parquet/qpa_all_quarters.parquet")
ap.add_argument("--air", default="parquet/air_all_quarters.parquet")
ap.add_argument("--out", default="qpa_oon_linked.parquet")
A = ap.parse_args()

con = duckdb.connect()
con.execute("SET memory_limit='3GB'; SET threads=4; SET preserve_insertion_order=false;")
say = lambda *a: print(*a, flush=True)
rule = lambda t: say("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)

# ─────────────────────────────────────────────────────────────────────────────
rule("STEP 1  Do the two files even describe the same rows?")
# If QPA == OON + AIR in every quarter, the files are the same population with the
# identifiers removed -- so each QPA row has exactly one partner and this is a
# deanonymisation, not a statistical merge. If this check fails, stop: everything
# downstream assumes a 1:1 population.
chk = con.execute(f"""
WITH a AS (SELECT Quarter q,count(*) n FROM read_parquet('{A.qpa}') GROUP BY 1),
     b AS (SELECT Quarter q,count(*) n FROM read_parquet('{A.oon}') GROUP BY 1),
     c AS (SELECT Quarter q,count(*) n FROM read_parquet('{A.air}') GROUP BY 1)
SELECT a.q, a.n qpa, b.n+c.n oon_plus_air, a.n-(b.n+c.n) diff
FROM a JOIN b USING(q) JOIN c USING(q) ORDER BY 1""").df()
say(chk.to_string(index=False))
if chk["diff"].abs().sum() != 0:
    sys.exit("\nABORT: the populations do not correspond; the fingerprint logic is invalid here.")
say("\n-> every quarter balances. Same rows, identifiers stripped.")

# ─────────────────────────────────────────────────────────────────────────────
rule("STEP 2  What is OON's 'QPA as Percent of Median QPA' a percent OF?")
# OON carries this column but CMS never documents the denominator. Recovering it turns an
# OON-only column into a coordinate computable on BOTH sides -- effectively the QPA dollar,
# scaled. Test candidate groupings by comparing value-frequency multisets: the populations
# are identical, so the right grouping reproduces OON's distribution almost exactly.
for label, grp in [
    ("service code",                 '"Service Code"'),
    ("code + quarter",               '"Service Code",Quarter'),
    ("code + quarter + region",      '"Service Code",Quarter,"Geographical Region"'),
    ("code + region",                '"Service Code","Geographical Region"'),
]:
    con.execute(f"""CREATE OR REPLACE TEMP TABLE cand AS
      SELECT round("QPA"/nullif(median("QPA") OVER (PARTITION BY {grp}),0),2) qm
      FROM read_parquet('{A.qpa}') WHERE "QPA">0""")
    r = con.execute(f"""
      WITH a AS (SELECT qm,count(*) n FROM cand WHERE qm IS NOT NULL GROUP BY 1),
           b AS (SELECT round("QPA as Percent of Median QPA",2) qm,count(*) n
                 FROM read_parquet('{A.oon}')
                 WHERE "QPA as Percent of Median QPA" IS NOT NULL GROUP BY 1)
      SELECT sum(least(coalesce(a.n,0),coalesce(b.n,0)))*1.0
             / least((SELECT sum(n) FROM a),(SELECT sum(n) FROM b))
      FROM a FULL JOIN b USING (qm)""").fetchone()[0]
    say(f"  {label:<26} multiset overlap {100*r:6.2f}%")
say("\n-> code + quarter + region. That is the partition used below.")

# ─────────────────────────────────────────────────────────────────────────────
rule("STEP 3  Build the fingerprint on the QPA side (from dollars)")
# Round to 2dp because that is the precision the OON file stores -- matching at full
# double precision would never hit.
where_region = f"""AND "Geographical Region" ILIKE '%{A.region}%'""" if A.region else ""
con.execute(f"""CREATE OR REPLACE TABLE q_side AS
SELECT * FROM (
  SELECT Quarter q, "Service Code" sc, "Place of Service Code" pos,
         "Default Decision" dd, "Dispute Line Item Type" dlit,
         "Offer Selected from Provider or Issuer" sel,
         "Geographical Region" region, "QPA" qpa,
         "Provider/Facility Offer" prov_usd, "Health Plan/Issuer Offer" plan_usd,
         "Prevailing Offer" prev_usd,
         "Initiating Party" init_party, "Certified IDR Entity" idre,     -- holdouts
         round("Provider/Facility Offer" /nullif("QPA",0),2) pp,
         round("Health Plan/Issuer Offer"/nullif("QPA",0),2) hp,
         round("Prevailing Offer"       /nullif("QPA",0),2) vp,
         round("QPA"/nullif(median("QPA") OVER (
               PARTITION BY "Service Code",Quarter,"Geographical Region"),0),2) qm
  FROM read_parquet('{A.qpa}')
  WHERE 1=1 {where_region})
WHERE qpa > 0 AND pp IS NOT NULL AND hp IS NOT NULL AND qm IS NOT NULL""")
tot = con.execute(f"""SELECT count(*) FROM read_parquet('{A.qpa}')
                      WHERE 1=1 {where_region}""").fetchone()[0]
fp = con.execute("SELECT count(*) FROM q_side").fetchone()[0]
say(f"  region lines in the QPA file   {tot:>9,}")
say(f"  fingerprintable                {fp:>9,}  ({100*fp/tot:.1f}%)")
say(f"  dropped: no QPA, or an offer missing (mostly defaults -- see the docstring)")

# ─────────────────────────────────────────────────────────────────────────────
rule("STEP 4  Build the same fingerprint on the OON side (already ratios)")
con.execute(f"""CREATE OR REPLACE TABLE o_side AS SELECT
  "Dispute Number" disp, "DLI Number" dli, Quarter q, "Service Code" sc,
  "Place of Service Code" pos, "Default Decision" dd,
  "Dispute Line Item Type" dlit, "Offer Selected from Provider or Issuer" sel,
  "Location of Service" st, "Carrier_Group" carrier, "Provider_Group" filer,
  "Initiating Party" init_party, "Certified IDR Entity" idre,            -- holdouts
  "Provider/Facility Offer as % of QPA"  pp,
  "Health Plan/Issuer Offer as % of QPA" hp,
  "Prevailing Party Offer as % of QPA"   vp,
  "QPA as Percent of Median QPA"         qm
FROM read_parquet('{A.oon}')
WHERE "Provider/Facility Offer as % of QPA"  IS NOT NULL
  AND "Health Plan/Issuer Offer as % of QPA" IS NOT NULL
  AND "QPA as Percent of Median QPA"         IS NOT NULL""")
say(f"  OON lines carrying a full fingerprint  "
    f"{con.execute('SELECT count(*) FROM o_side').fetchone()[0]:>9,}")
say("  note: the OON side is NOT filtered by region -- it has no MSA column, only a state.")

# ─────────────────────────────────────────────────────────────────────────────
rule("STEP 5  Group both sides and compare cardinality")
# Row-level uniqueness is low: batched disputes repeat identical lines. That is fine.
# What matters is whether a fingerprint's QPA-side count equals its OON-side count
# (a "closed set") and whether the QPA dollar is constant inside it -- if so, every OON
# row in the group takes that dollar no matter which row pairs with which.
KEY = ["q","sc","pos","pp","hp","vp","qm","dd","dlit","sel"]
K = ",".join(KEY)
con.execute(f"""CREATE OR REPLACE TABLE qg AS
  SELECT {K}, count(*) n_qpa, min(qpa) qmin, max(qpa) qmax, any_value(qpa) qpa
  FROM q_side GROUP BY ALL""")
con.execute(f"CREATE OR REPLACE TABLE og AS SELECT {K}, count(*) n_oon FROM o_side GROUP BY ALL")
con.execute(f"""CREATE OR REPLACE TABLE matched AS
  SELECT qg.*, og.n_oon FROM qg LEFT JOIN og USING ({K})""")
say(con.execute(f"""SELECT
   CASE WHEN n_oon IS NULL                     THEN '4. no OON row with this fingerprint'
        WHEN n_qpa=1 AND n_oon=1               THEN '1. exact 1:1'
        WHEN n_qpa=n_oon                       THEN '2. closed group (counts equal)'
        ELSE                                        '3. ambiguous (counts differ)' END outcome,
   sum(n_qpa) lines, round(100.0*sum(n_qpa)/{fp},2) pct_of_fingerprintable
 FROM matched GROUP BY 1 ORDER BY 1""").df().to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
rule("STEP 6  Validate on fields deliberately kept OUT of the key")
# Initiating Party and Certified IDR Entity exist in both files and were not matched on.
# If the linkage were coincidence they would agree at the base rate (the modal IDRE is
# ~39% of lines), not at 100%.
con.execute(f"""CREATE OR REPLACE TABLE pairs AS
WITH a AS (SELECT {K}, any_value(init_party) ip_q, any_value(idre) idre_q, any_value(qpa) qpa
           FROM q_side GROUP BY ALL HAVING count(*)=1),
     b AS (SELECT {K}, any_value(init_party) ip_o, any_value(idre) idre_o,
                  any_value(disp) disp, any_value(dli) dli
           FROM o_side GROUP BY ALL HAVING count(*)=1)
SELECT * FROM a JOIN b USING ({K})""")
say(con.execute("""SELECT count(*) one_to_one,
  round(100.0*sum(CASE WHEN ip_q=ip_o THEN 1 ELSE 0 END)
       /nullif(sum(CASE WHEN ip_q IS NOT NULL AND ip_o IS NOT NULL THEN 1 ELSE 0 END),0),2) init_party_agree,
  round(100.0*sum(CASE WHEN idre_q=idre_o THEN 1 ELSE 0 END)
       /nullif(sum(CASE WHEN idre_q IS NOT NULL AND idre_o IS NOT NULL THEN 1 ELSE 0 END),0),2) idre_agree
FROM pairs""").df().to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
rule("STEP 7  Attach the dollars and write the result")
# Keep only closed sets carrying a single QPA dollar. The dollar is then correct for every
# OON row in the group regardless of the permutation; the carrier is read off the OON row
# itself and is never inferred.
con.execute(f"""CREATE OR REPLACE TABLE linked AS
SELECT o.disp, o.dli, o.q, o.sc, o.pos, o.st, o.carrier, o.filer, o.dd, o.sel,
       m.qpa                      AS qpa_usd,
       round(o.pp*m.qpa,2)        AS provider_offer_usd,
       round(o.hp*m.qpa,2)        AS plan_offer_usd,
       round(o.vp*m.qpa,2)        AS prevailing_usd,
       round((o.vp-1)*m.qpa,2)    AS inflation_usd,
       CASE WHEN m.n_qpa=1 THEN 'exact 1:1' ELSE 'closed group' END AS match_type,
       m.n_qpa AS group_size
FROM o_side o JOIN matched m USING ({K})
WHERE m.n_oon = m.n_qpa AND abs(m.qmax-m.qmin) < 0.005""")
n = con.execute("SELECT count(*) FROM linked").fetchone()[0]
say(f"  linked lines with a known QPA dollar  {n:,}  ({100*n/tot:.1f}% of all region lines)")
say(con.execute("SELECT match_type, count(*) lines FROM linked GROUP BY 1 ORDER BY 2 DESC").df().to_string(index=False))
con.execute(f"COPY linked TO '{A.out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
say(f"\n  wrote {A.out}")
say("\n  REMINDER: contested determinations only. No default or win-rate stats from this.")
