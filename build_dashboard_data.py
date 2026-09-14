"""
Build the pre-aggregated JSON payload powering the IDR Public Use File dashboard.
Re-run after adding a quarter:  python build_dashboard_data.py
Source: parquet/oon_all_quarters.parquet + parquet/qpa_all_quarters.parquet  (OON only; air ambulance excluded)

GRAIN: Dispute Line Item (DLI). Outcome uses `Offer Selected from Provider or Issuer`
(actual per-line outcome) rather than `Payment Determination Outcome` (dispute-level estimate).

TRIM RULE: offer-as-%-of-QPA multiples are kept only when 0 <= x <= 1000.
Drops ~0.05% of lines (pure data-entry artifacts, max observed 23,398,005x).
Applied ONLY to magnitude metrics. All count metrics use every line.
"""
import duckdb, json, datetime, os
import numpy as np

PQ_DIR = os.environ.get('IDR_PARQUET_DIR', 'parquet_rebuilt')
OON = f'{PQ_DIR}/oon_all_quarters.parquet'
QPA = f'{PQ_DIR}/qpa_all_quarters.parquet'
OUT = 'dashboard/data.json'
TRIM_LO, TRIM_HI = 0, 1000

con = duckdb.connect()
con.execute("SET memory_limit='3GB'; SET threads=4; SET preserve_insertion_order=false;")
Q = lambda s: con.execute(s).df()

con.execute(f"""
CREATE OR REPLACE VIEW base AS SELECT
  "Dispute Number" dispute, "DLI Number" dli, "Quarter" q,
  -- Line-level outcome, with a dispute-level fallback. "Offer Selected from Provider or
  -- Issuer" is the actual per-line result and is preferred wherever it exists, but it is
  -- blank on 354,245 lines (4.3%), spread evenly across all 12 quarters -- so it is a real
  -- gap in the source, not a parsing failure. On 354,130 of those (99.97%) the dispute-level
  -- "Payment Determination Outcome" IS populated, and so is Default Decision. Leaving them
  -- unclassified threw away a known outcome; the fallback recovers it. Only 115 lines end up
  -- with no outcome from either field.
  -- The fallback is dispute-level, so on a batched dispute it reports the dispute's overall
  -- result rather than that specific line's -- which is exactly why it is a fallback and not
  -- the primary. sel_src records which field each line came from.
  "Offer Selected from Provider or Issuer" sel_line,
  "Payment Determination Outcome" pdo,
  coalesce("Offer Selected from Provider or Issuer",
           "Payment Determination Outcome") sel,
  CASE WHEN "Offer Selected from Provider or Issuer" IS NOT NULL THEN 'line'
       WHEN "Payment Determination Outcome"          IS NOT NULL THEN 'dispute' END sel_src,
  CASE WHEN coalesce("Offer Selected from Provider or Issuer",
                     "Payment Determination Outcome") LIKE 'In Favor of Provider%' THEN 1
       WHEN coalesce("Offer Selected from Provider or Issuer",
                     "Payment Determination Outcome") LIKE 'In Favor of Plan%'     THEN 0 END prov_win,
  CASE WHEN "Default Decision"='Yes' THEN 1 ELSE 0 END is_default,
  "Default Decision" defdec, "Outcome_Bucket" bucket, "Carrier_Group" carrier,
  "Provider_Group" pgroup, "Provider_Category" pcat, "Health Plan Type" plantype,
  "Practice/Facility Size" psize, "Practice/Facility Specialty or Type" spec,
  "Location of Service" st, "Service Code" svc, "Type of Service Code" svctype,
  "Item or Service Description" descr, "Type of Dispute" dtype,
  "Dispute Line Item Type" dlitype, "Initiating Party" initparty,
  "Length of Time to Make Determination" det_days, "IDRE Compensation" idre_fee,
  "Certified IDR Entity" idre, "Date of Initiation" init_date,
  CASE WHEN "Provider/Facility Offer as % of QPA"   BETWEEN {TRIM_LO} AND {TRIM_HI}
       THEN "Provider/Facility Offer as % of QPA" END pm,
  CASE WHEN "Health Plan/Issuer Offer as % of QPA"  BETWEEN {TRIM_LO} AND {TRIM_HI}
       THEN "Health Plan/Issuer Offer as % of QPA" END plm,
  CASE WHEN "Prevailing Party Offer as % of QPA"    BETWEEN {TRIM_LO} AND {TRIM_HI}
       THEN "Prevailing Party Offer as % of QPA" END prm
FROM read_parquet('{OON}');
""")

D = {}
recs = lambda df: json.loads(df.to_json(orient='records'))

# ---------------- headline KPIs ----------------
D['kpi'] = recs(Q("""
SELECT count(*) lines, count(DISTINCT dispute) disputes,
  round(100.0*sum(prov_win)/nullif(count(prov_win),0),2)      prov_win_pct,
  round(100.0*sum(is_default)/count(*),2)                     default_pct,
  round(median(pm),2) med_prov_mult, round(median(plm),2) med_plan_mult,
  round(median(prm),2) med_prev_mult, round(median(det_days),1) med_days,
  round(median(idre_fee),2) med_idre_fee,
  round(100.0*sum(CASE WHEN plm BETWEEN 0.95 AND 1.05 THEN 1 ELSE 0 END)
        /nullif(count(plm),0),2) plan_at_qpa_pct,
  round(100.0*sum(CASE WHEN det_days>30 THEN 1 ELSE 0 END)/nullif(count(det_days),0),2) over_30d_pct
FROM base"""))[0]

# ---------------- dispute-level metrics (IDRE fee & determination time are DISPUTE-level
# fields per the data dictionary; aggregating them across line items double-counts batched
# disputes, so these are deduplicated to one row per Dispute Number) ----------------
con.execute("""CREATE OR REPLACE TABLE disp AS
SELECT dispute, any_value(idre_fee) fee, any_value(det_days) dd, any_value(q) q,
       any_value(carrier) carrier, max(is_default) is_default,
       count(*) lines, count(DISTINCT svc) codes,
       max(coalesce(prov_win,0)) prov_won,
       -- how many of the dispute's lines share the dispute's prevailing side; the IDRE fee
       -- is spread over these rather than over every line (see line_fees below)
       sum(CASE WHEN prov_win=1 THEN 1 ELSE 0 END) prov_win_lines
FROM base GROUP BY dispute;""")

# Dispute composition. A dispute number can cover several line items, and the shape of
# that grouping says something about the underlying claims:
#   Single Line                        -> one service line from one claim
#   Multi-Line, Same Service Code      -> same CPT/HCPCS repeated; a duplicate CPT is only
#                                         valid on one claim under narrow conditions, so these
#                                         are most likely separate claims/members batched together
#   Multi-Line, Different Service Codes-> several codes, most likely one claim filed as one dispute
# Must be computed after the full file is assembled -- a dispute can span read batches, so
# it cannot be derived during per-batch ingestion.
con.execute("""CREATE OR REPLACE VIEW dcomp AS SELECT *,
  CASE WHEN lines=1 THEN 'Single Line'
       WHEN codes=1 THEN 'Multi-Line, Same Service Code'
       ELSE 'Multi-Line, Different Service Codes' END shape,
  CAST(substr(q,1,4) AS INT) yr,
  CASE WHEN CAST(substr(q,1,4) AS INT) <= 2023 THEN 50 ELSE 115 END admin_rate,
  (is_default=1 AND prov_won=1) plan_defaulted,
  (is_default=1 AND prov_won=0) prov_defaulted
FROM disp;""")

D['dispute_composition'] = recs(Q("""
SELECT shape, count(*) disputes,
  round(100.0*count(*)/(SELECT count(*) FROM dcomp),2) pct_disputes,
  sum(lines) lines, round(100.0*sum(lines)/(SELECT sum(lines) FROM dcomp),2) pct_lines,
  round(avg(lines),2) avg_lines, max(lines) max_lines,
  round(100.0*avg(prov_won),2) prov_win_pct,
  round(100.0*avg(CASE WHEN is_default=1 THEN 1 ELSE 0 END),2) default_pct
FROM dcomp GROUP BY 1 ORDER BY disputes DESC"""))

# Fees. Administrative fee is per party per dispute and only paid by parties that submitted
# an offer, so a defaulting party pays none. Rate is year-correct: $50/party for CY2022-2023,
# $115/party from CY2024 (the $350 CY2023 rate was vacated in TMA III and reverted to $50).
# IDRE Compensation is the TOTAL certified-IDR-entity fee for the dispute; both parties pay it
# up front and the prevailing party is refunded, so it is ultimately borne by the loser.
D['fees'] = recs(Q("""
SELECT
  round(sum(CASE WHEN plan_defaulted THEN 0 ELSE admin_rate END)/1e6,1) plan_admin_musd,
  round(sum(CASE WHEN prov_won=1 THEN fee ELSE 0 END)/1e6,1)            plan_idre_musd,
  round((sum(CASE WHEN plan_defaulted THEN 0 ELSE admin_rate END)
        +sum(CASE WHEN prov_won=1 THEN fee ELSE 0 END))/1e6,1)          plan_total_musd,
  round(avg(CASE WHEN plan_defaulted THEN 0 ELSE admin_rate END)
       +avg(CASE WHEN prov_won=1 THEN fee ELSE 0 END),2)                plan_per_dispute,
  round((sum(CASE WHEN plan_defaulted THEN 0 ELSE admin_rate END)
        +sum(CASE WHEN prov_defaulted THEN 0 ELSE admin_rate END)
        +sum(fee))/1e6,1)                                               program_total_musd,
  sum(CASE WHEN plan_defaulted THEN 1 ELSE 0 END)                       plan_default_disputes,
  round(sum(CASE WHEN plan_defaulted THEN fee ELSE 0 END)/1e6,1)        plan_default_idre_musd
FROM dcomp"""))[0]

D['kpi_dispute'] = recs(Q("""
SELECT count(*) disputes, round(sum(fee)/1e6,1) idre_fees_musd,
  round(median(fee),2) med_fee, round(median(dd),1) med_days,
  round(quantile_cont(dd,0.25),0) p25_days, round(quantile_cont(dd,0.75),0) p75_days,
  round(quantile_cont(dd,0.90),0) p90_days,
  round(100.0*sum(CASE WHEN dd>30 THEN 1 ELSE 0 END)/nullif(count(dd),0),2) over_30d_pct
FROM disp"""))[0]

D['determination_days'] = recs(Q("""
SELECT CASE WHEN dd<=30 THEN '1-30 (statutory)' WHEN dd<=45 THEN '31-45'
            WHEN dd<=60 THEN '46-60' WHEN dd<=90 THEN '61-90'
            WHEN dd<=120 THEN '91-120' WHEN dd<=180 THEN '121-180'
            ELSE '180+' END bucket, count(*) disputes
FROM disp WHERE dd IS NOT NULL GROUP BY 1 ORDER BY min(dd)"""))

D['days_quarterly'] = recs(Q("""
SELECT q, round(median(dd),1) med_days, round(quantile_cont(dd,0.90),0) p90_days,
  round(100.0*sum(CASE WHEN dd>30 THEN 1 ELSE 0 END)/nullif(count(dd),0),2) over_30d_pct,
  count(*) disputes
FROM disp GROUP BY q ORDER BY q"""))

# ---------------- quarterly trend ----------------
D['quarterly'] = recs(Q("""
SELECT q, count(*) lines, count(DISTINCT dispute) disputes,
  round(100.0*sum(prov_win)/nullif(count(prov_win),0),2) prov_win_pct,
  round(100.0*sum(is_default)/count(*),2) default_pct,
  round(median(pm),2) med_prov_mult, round(median(plm),2) med_plan_mult,
  round(median(prm),2) med_prev_mult, round(median(det_days),1) med_days,
  round(100.0*sum(CASE WHEN prov_win IS NULL THEN 1 ELSE 0 END)/count(*),2) unresolved_pct
FROM base GROUP BY q ORDER BY q"""))

# ---------------- outcome buckets ----------------
D['outcome_buckets'] = recs(Q("""
SELECT CASE WHEN prov_win IS NULL     THEN 'Other / Split'
            WHEN is_default=1 AND prov_win=1 THEN 'Default Provider Win'
            WHEN is_default=1                THEN 'Default Plan Win'
            WHEN prov_win=1                  THEN 'Contested Provider Win'
            ELSE 'Contested Plan Win' END bucket,
  count(*) lines, round(100.0*count(*)/(SELECT count(*) FROM base),2) pct
FROM base GROUP BY 1 ORDER BY lines DESC"""))

# ---------------- carriers ----------------
D['carriers'] = recs(Q("""
SELECT coalesce(carrier,'Unknown') carrier, count(*) lines, count(DISTINCT dispute) disputes,
  round(100.0*sum(prov_win)/nullif(count(prov_win),0),2) prov_win_pct,
  round(100.0*sum(is_default)/count(*),2) default_pct,
  round(median(plm),2) med_plan_mult, round(median(prm),2) med_prev_mult,
  round(median(pm),2) med_prov_mult,
  round(100.0*sum(CASE WHEN plm BETWEEN 0.95 AND 1.05 THEN 1 ELSE 0 END)
        /nullif(count(plm),0),2) plan_at_qpa_pct,
  round(100.0*count(*)/(SELECT count(*) FROM base),2) share_pct
FROM base GROUP BY 1 HAVING count(*)>=2000 ORDER BY lines DESC"""))

D['carrier_quarterly'] = recs(Q("""
WITH top AS (SELECT carrier FROM base WHERE carrier IS NOT NULL
             GROUP BY 1 ORDER BY count(*) DESC LIMIT 12)
SELECT b.carrier, b.q, count(*) lines,
  round(100.0*sum(b.prov_win)/nullif(count(b.prov_win),0),2) prov_win_pct,
  round(100.0*sum(b.is_default)/count(*),2) default_pct
FROM base b JOIN top ON top.carrier=b.carrier GROUP BY 1,2 ORDER BY 1,2"""))

# ---------------- service codes ----------------
D['service_codes'] = recs(Q("""
WITH d AS (SELECT svc, any_value(descr) descr FROM base WHERE descr IS NOT NULL GROUP BY svc)
SELECT b.svc code, coalesce(d.descr,'') descr, any_value(b.svctype) svctype,
  count(*) lines, round(100.0*sum(b.prov_win)/nullif(count(b.prov_win),0),2) prov_win_pct,
  round(median(b.pm),2) med_prov_mult, round(median(b.plm),2) med_plan_mult,
  round(median(b.prm),2) med_prev_mult
FROM base b LEFT JOIN d ON d.svc=b.svc
GROUP BY b.svc, d.descr HAVING count(*)>=500 ORDER BY lines DESC LIMIT 250"""))

# ---------------- geography ----------------
D['states'] = recs(Q("""
SELECT st, count(*) lines, count(DISTINCT dispute) disputes,
  round(100.0*sum(prov_win)/nullif(count(prov_win),0),2) prov_win_pct,
  round(100.0*sum(is_default)/count(*),2) default_pct,
  round(median(prm),2) med_prev_mult
FROM base WHERE st IS NOT NULL GROUP BY st ORDER BY lines DESC"""))

# ---------------- providers ----------------
D['provider_groups'] = recs(Q("""
SELECT coalesce(pgroup,'Unknown') pgroup, any_value(pcat) pcat, count(*) lines,
  round(100.0*sum(prov_win)/nullif(count(prov_win),0),2) prov_win_pct,
  round(median(pm),2) med_prov_mult, round(median(prm),2) med_prev_mult
FROM base GROUP BY 1 HAVING count(*)>=2000 ORDER BY lines DESC LIMIT 60"""))

D['provider_categories'] = recs(Q("""
SELECT coalesce(pcat,'Unknown') pcat, count(*) lines,
  round(100.0*sum(prov_win)/nullif(count(prov_win),0),2) prov_win_pct,
  round(median(pm),2) med_prov_mult
FROM base GROUP BY 1 ORDER BY lines DESC"""))

# ---------------- segments ----------------
for key, col in [('plan_types','plantype'), ('practice_sizes','psize'),
                 ('specialties','spec'), ('dispute_types','dtype'),
                 ('dli_types','dlitype'), ('initiating_parties','initparty')]:
    lim = 'LIMIT 25' if key == 'specialties' else ''
    D[key] = recs(Q(f"""
    SELECT coalesce({col},'Unknown') seg, count(*) lines,
      round(100.0*sum(prov_win)/nullif(count(prov_win),0),2) prov_win_pct,
      round(100.0*sum(is_default)/count(*),2) default_pct,
      round(median(prm),2) med_prev_mult
    FROM base GROUP BY 1 ORDER BY lines DESC {lim}"""))

# ---------------- offer-multiple histogram (the anchoring story) ----------------
BINS = [(0,.5),(.5,.75),(.75,.95),(.95,1.05),(1.05,1.25),(1.25,1.5),(1.5,2),
        (2,3),(3,5),(5,10),(10,25),(25,1000)]
rows = []
for lo, hi in BINS:
    r = Q(f"""SELECT
      sum(CASE WHEN pm  >= {lo} AND pm  < {hi} THEN 1 ELSE 0 END) prov,
      sum(CASE WHEN plm >= {lo} AND plm < {hi} THEN 1 ELSE 0 END) plan_n,
      sum(CASE WHEN prm >= {lo} AND prm < {hi} THEN 1 ELSE 0 END) prev FROM base""").iloc[0]
    lbl = f"{lo:g}–{hi:g}x" if hi < 1000 else "25x+"
    rows.append({'bin': lbl, 'lo': lo, 'hi': hi,
                 'prov': int(r.prov), 'plan': int(r.plan_n), 'prev': int(r.prev)})
D['offer_histogram'] = rows

# ---------------- QPA-file derived multiples ----------------
# The OON parquet has NO offer-as-%-of-QPA values for 2024Q3-Q4: all five percent-family
# columns are 0% populated across 1.61M lines, while controls on the same coercion path
# (Length of Time, IDRE Compensation) are 100% populated in those quarters -- so this is an
# ingestion/source gap for those columns, not a parsing failure. Cause not yet confirmed
# against raw CMS files (2024 raw files are not retained in the repo).
# The QPA file still carries the dollar amounts, so multiples are recomputed there to fill
# the gap and to independently validate the OON-reported percentages (they agree within
# 0.1-0.2x in all ten other quarters).
D['qpa_quarterly'] = recs(Q(f"""
WITH r AS (SELECT "Quarter" q,
  CASE WHEN "Provider/Facility Offer"/"QPA"  BETWEEN {TRIM_LO} AND {TRIM_HI} THEN "Provider/Facility Offer"/"QPA" END pm,
  CASE WHEN "Health Plan/Issuer Offer"/"QPA" BETWEEN {TRIM_LO} AND {TRIM_HI} THEN "Health Plan/Issuer Offer"/"QPA" END plm,
  CASE WHEN "Prevailing Offer"/"QPA"         BETWEEN {TRIM_LO} AND {TRIM_HI} THEN "Prevailing Offer"/"QPA" END prm,
  "QPA" qpa, "Prevailing Offer" prev_usd, "Health Plan/Issuer Offer" plan_usd
FROM read_parquet('{QPA}') WHERE "QPA" IS NOT NULL AND "QPA">0)
SELECT q, count(*) n, round(median(pm),2) med_prov_mult, round(median(plm),2) med_plan_mult,
  round(median(prm),2) med_prev_mult, round(median(qpa),2) med_qpa_usd,
  round(median(prev_usd),2) med_prev_usd, round(median(plan_usd),2) med_plan_usd,
  round(100.0*sum(CASE WHEN plm BETWEEN 0.95 AND 1.05 THEN 1 ELSE 0 END)/nullif(count(plm),0),2) plan_at_qpa_pct
FROM r GROUP BY q ORDER BY q"""))

# field availability map, so the UI can annotate gaps honestly
D['field_coverage'] = recs(Q("""
SELECT "Quarter" q,
 round(100.0*sum(CASE WHEN "Provider/Facility Offer as % of QPA" IS NOT NULL THEN 1 ELSE 0 END)/count(*),1) offer_mult_pct,
 round(100.0*sum(CASE WHEN "Certified IDR Entity" IS NOT NULL THEN 1 ELSE 0 END)/count(*),1) idre_pct,
 round(100.0*sum(CASE WHEN "Date of Initiation" IS NOT NULL THEN 1 ELSE 0 END)/count(*),1) initdate_pct,
 round(100.0*sum(CASE WHEN "Offer Selected from Provider or Issuer" IS NULL THEN 1 ELSE 0 END)/count(*),2) unresolved_pct
FROM read_parquet('""" + OON + """') GROUP BY 1 ORDER BY 1"""))

D['timing_stats'] = recs(Q("""
SELECT round(quantile_cont(dd,0.25),0) p25, round(median(dd),0) p50,
       round(quantile_cont(dd,0.75),0) p75, round(quantile_cont(dd,0.90),0) p90,
       max(dd) mx FROM disp WHERE dd IS NOT NULL"""))[0]

# ---------------- IDR entities (2025Q3+ only) ----------------
D['idre_entities'] = recs(Q("""
SELECT idre, count(*) lines, count(DISTINCT dispute) disputes,
  round(100.0*sum(prov_win)/nullif(count(prov_win),0),2) prov_win_pct,
  round(100.0*sum(is_default)/count(*),2) default_pct,
  round(median(idre_fee),0) med_fee, round(median(det_days),0) med_days
FROM base WHERE idre IS NOT NULL GROUP BY 1 HAVING count(*)>=1000 ORDER BY lines DESC"""))

# ---------------- rate table for the estimator (QPA file, service-code grain) ----------------
D['rate_table'] = recs(Q(f"""
SELECT "Service Code" code, count(*) n,
  round(median("QPA"),2) qpa,
  round(median(CASE WHEN "Provider/Facility Offer"/"QPA"  BETWEEN {TRIM_LO} AND {TRIM_HI}
               THEN "Provider/Facility Offer"/"QPA"  END),3) prov_mult,
  round(median(CASE WHEN "Health Plan/Issuer Offer"/"QPA" BETWEEN {TRIM_LO} AND {TRIM_HI}
               THEN "Health Plan/Issuer Offer"/"QPA" END),3) plan_mult,
  round(median(CASE WHEN "Prevailing Offer"/"QPA"         BETWEEN {TRIM_LO} AND {TRIM_HI}
               THEN "Prevailing Offer"/"QPA"         END),3) prev_mult
FROM read_parquet('{QPA}')
WHERE "QPA" IS NOT NULL AND "QPA">0 GROUP BY 1 HAVING count(*)>=25 ORDER BY n DESC"""))

# state-level prevailing-offer multiplier vs national median (for estimator geo adjustment)
D['state_factors'] = recs(Q("""
WITH nat AS (SELECT median(prm) m FROM base)
SELECT st, round(median(prm)/(SELECT m FROM nat),3) factor, count(*) lines
FROM base WHERE st IS NOT NULL AND prm IS NOT NULL
GROUP BY st HAVING count(*)>=500 ORDER BY lines DESC"""))

D['ratios'] = {'lines_per_dispute': round(D['kpi']['lines']/D['kpi']['disputes'], 3)}

# ── Payment inflation ────────────────────────────────────────────────────────
# What the program cost plans in AWARDS, on top of fees. Baseline is the QPA -- the plan's
# own median contracted rate, and the statutory benchmark. Inflation = Prevailing Offer - QPA.
#
# The QPA is a CONSERVATIVE baseline: where CMS also publishes Initial Payment Amount
# (2025Q3+ only), the initial payment runs at ~0.89x the QPA and 15% of initial payments are
# $0 outright denials, so measuring against actual initial payments yields ~5% MORE inflation
# in aggregate (16% more at the median). Using the QPA understates the cost.
#
# Same 0-1000x trim as every other magnitude metric. Untrimmed, 2,115 lines (0.03%) carry
# $2.78B of apparent inflation -- a single line reaches $263M -- so a raw sum is meaningless.
con.execute("""CREATE OR REPLACE VIEW infl AS
SELECT "QPA" q, "Prevailing Offer" p, "Prevailing Offer"/nullif("QPA",0) mult,
       "Initial Payment Amount" ipa, "Quarter" qtr,
       "Offer Selected from Provider or Issuer" sel
FROM read_parquet('""" + QPA + """')
WHERE "QPA">0 AND "Prevailing Offer" IS NOT NULL;""")

D['inflation'] = recs(Q(f"""
SELECT count(*) lines_measured,
  round(sum(p-q)/1e9,2) total_busd,
  round(median(p-q),2) med_per_line,
  round(sum(CASE WHEN sel LIKE 'In Favor of Provider%' THEN p-q ELSE 0 END)/1e9,2) provider_win_busd,
  round(sum(CASE WHEN sel LIKE 'In Favor of Plan%' THEN p-q ELSE 0 END)/1e9,2) plan_win_busd,
  round(median(CASE WHEN sel LIKE 'In Favor of Provider%' THEN p-q END),2) med_per_line_prov_win,
  round(100.0*count(*)/(SELECT count(*) FROM read_parquet('{QPA}')),1) coverage_pct
FROM infl WHERE mult BETWEEN {TRIM_LO} AND {TRIM_HI}"""))[0]

D['inflation_quarterly'] = recs(Q(f"""
SELECT qtr q, count(*) lines, round(sum(p-q)/1e6,1) infl_musd, round(median(p-q),2) med_per_line
FROM infl WHERE mult BETWEEN {TRIM_LO} AND {TRIM_HI} GROUP BY 1 ORDER BY 1"""))

# The carrier-default case, isolated: lines where the plan's side never submitted an offer.
# Fees are the IDRE fees plans still bore on those disputes (no admin fee is paid by a
# defaulting party). Inflation is measured directly in the QPA file, which carries its own
# Default Decision and Offer Selected columns.
_d1 = recs(Q("""SELECT count(*) lines, count(DISTINCT dispute) disputes
FROM base WHERE is_default=1 AND prov_win=1"""))[0]
_d2 = recs(Q(f"""
WITH r AS (SELECT "QPA" q,"Prevailing Offer" p,"Prevailing Offer"/nullif("QPA",0) mult,
  "Default Decision" dd,"Offer Selected from Provider or Issuer" sel
 FROM read_parquet('{QPA}') WHERE "QPA">0 AND "Prevailing Offer" IS NOT NULL)
SELECT count(*) lines_measured, round(sum(p-q)/1e9,2) inflation_busd,
  round(median(p-q),2) med_per_line
FROM r WHERE mult BETWEEN {TRIM_LO} AND {TRIM_HI}
  AND dd='Yes' AND sel LIKE 'In Favor of Provider%'"""))[0]
D['defaults'] = {**_d1, **_d2, 'fees_musd': D['fees']['plan_default_idre_musd']}

# combined cost to plans: awards above benchmark + fees borne
D['inflation']['fees_busd'] = round(D['fees']['plan_total_musd']/1000, 2)
D['inflation']['total_cost_busd'] = round(D['inflation']['total_busd'] + D['fees']['plan_total_musd']/1000, 2)

# ── Plan mix ─────────────────────────────────────────────────────────────────
# "No Plan/Issuer Response" is NOT missing data to be imputed. It is the label CMS
# applies when the plan side never responded, and it carries a 65.5% default rate
# against 16.4% for self-insured. Imputing it into the funded buckets would move the
# worst-performing lines into them on an assumption. It is reported as its own category.
D['plan_mix'] = recs(Q("""
SELECT coalesce(plantype,'Unknown') seg, count(*) lines,
  round(100.0*count(*)/(SELECT count(*) FROM base),2) pct,
  round(100.0*sum(is_default)/count(*),1) default_pct,
  round(100.0*sum(prov_win)/nullif(count(prov_win),0),1) prov_win_pct
FROM base GROUP BY 1 ORDER BY lines DESC"""))

# ── State exposure ───────────────────────────────────────────────────────────
# Estimated overpayment uses MEDIAN benchmarks per service code, applied to each OON
# line and summed by the OON file's own `Location of Service` (a clean 2-letter code).
#
# It deliberately does NOT derive state from the QPA file's Geographical Region. That
# field is an MSA string, and assigning a multi-state MSA to its primary state is badly
# wrong: nearly all New Jersey volume sits in "New York-Newark-Jersey City, NY-NJ-PA",
# which stripped NJ to 2,196 measurable lines (0.01x its actual volume) and inflated NY.
# Summing raw per-line gaps by state is also unusable -- NY's total was carried by a
# handful of six-figure lines (one at $1.13M on a $1,574 QPA).
#
# Median benchmarks are immune to both. National total by this method is $8.1B against
# $10.68B for the direct sum: medians ignore the right tail, so this is the conservative
# figure of the two.
con.execute(f"""CREATE OR REPLACE TABLE rt_svc AS
SELECT "Service Code" svc, count(*) n, median("QPA") qpa,
  median(CASE WHEN "Prevailing Offer"/"QPA" BETWEEN {TRIM_LO} AND {TRIM_HI}
              THEN "Prevailing Offer"/"QPA" END) prev_mult
FROM read_parquet('{QPA}') WHERE "QPA" IS NOT NULL AND "QPA">0
GROUP BY 1 HAVING count(*)>=25;""")
_g = Q("SELECT median(qpa) gq, median(prev_mult) gm FROM rt_svc").iloc[0]

D['state_exposure'] = recs(Q(f"""
SELECT b.st, count(*) lines, count(DISTINCT b.dispute) disputes,
  round(100.0*sum(b.prov_win)/nullif(count(b.prov_win),0),1) prov_win_pct,
  round(100.0*sum(b.is_default)/count(*),1) default_pct,
  round(sum(coalesce(rt.qpa,{_g.gq})*(coalesce(rt.prev_mult,{_g.gm})-1))/1e6,1) est_overpay_musd
FROM base b LEFT JOIN rt_svc rt ON rt.svc=b.svc
WHERE b.st IS NOT NULL GROUP BY 1 ORDER BY lines DESC"""))

D['overpay_method'] = recs(Q(f"""
SELECT count(*) lines,
  round(100.0*sum(CASE WHEN rt.svc IS NOT NULL THEN 1 ELSE 0 END)/count(*),1) svc_matched_pct,
  round(sum(coalesce(rt.qpa,{_g.gq})*(coalesce(rt.prev_mult,{_g.gm})-1))/1e9,2) est_busd,
  round({_g.gq},2) global_median_qpa, round({_g.gm},2) global_median_mult
FROM base b LEFT JOIN rt_svc rt ON rt.svc=b.svc"""))[0]

# Reconcile state dollars to the published headline. The median-benchmark method is the
# only one that can be split by state reliably, but it totals $8.1B against the headline
# $10.68B direct-sum figure. Using it for each state's SHARE and applying that share to the
# headline keeps the state table adding up to the number shown everywhere else, while the
# allocation itself still rests on outlier-immune medians.
_tot_est = sum(r['est_overpay_musd'] or 0 for r in D['state_exposure'])
_headline_musd = D['inflation']['total_busd']*1000
for _r in D['state_exposure']:
    _sh = (_r['est_overpay_musd'] or 0)/_tot_est if _tot_est else 0
    _r['share_pct'] = round(100*_sh, 2)
    _r['overpay_musd'] = round(_sh*_headline_musd, 1)

# ── Per-carrier and per-provider quarterly series ────────────────────────────
D['carrier_quarterly'] = recs(Q("""
WITH top AS (SELECT carrier FROM base WHERE carrier IS NOT NULL
             GROUP BY 1 ORDER BY count(*) DESC LIMIT 8)
SELECT b.carrier, b.q, count(*) lines, count(DISTINCT b.dispute) disputes,
  round(100.0*sum(b.prov_win)/nullif(count(b.prov_win),0),2) prov_win_pct,
  round(100.0*sum(b.is_default)/count(*),2) default_pct
FROM base b JOIN top ON top.carrier=b.carrier GROUP BY 1,2 ORDER BY 1,2"""))

D['provider_quarterly'] = recs(Q("""
WITH top AS (SELECT pgroup FROM base WHERE pgroup IS NOT NULL AND pgroup<>'Unknown'
             GROUP BY 1 ORDER BY count(*) DESC LIMIT 8)
SELECT b.pgroup, b.q, count(*) lines, count(DISTINCT b.dispute) disputes,
  round(100.0*sum(b.prov_win)/nullif(count(b.prov_win),0),2) prov_win_pct,
  round(100.0*sum(b.is_default)/count(*),2) default_pct
FROM base b JOIN top ON top.pgroup=b.pgroup GROUP BY 1,2 ORDER BY 1,2"""))

# ── Fine-grained offer distribution, for a density curve ─────────────────────
# 0.2x buckets to 12x plus a tail bucket; enough resolution to show the spike at 1.0x.
D['offer_density'] = recs(Q(f"""
WITH b AS (SELECT generate_series*0.2 AS lo FROM generate_series(0,59))
SELECT round(b.lo,1) lo, round(b.lo+0.2,1) hi,
  (SELECT count(*) FROM base WHERE pm  >= b.lo AND pm  < b.lo+0.2) prov,
  (SELECT count(*) FROM base WHERE plm >= b.lo AND plm < b.lo+0.2) plan_n,
  (SELECT count(*) FROM base WHERE prm >= b.lo AND prm < b.lo+0.2) prev
FROM b ORDER BY lo"""))

# ── Contested-only offer distributions (mirrors the Anthem analysis) ─────────
# "Contested" excludes defaults: a defaulted line has no competing offer, so including
# them would blur the very comparison the chart exists to make.
con.execute("""CREATE OR REPLACE VIEW cont AS
SELECT pm, plm, prm FROM base WHERE is_default=0;""")

# ── Offer densities ──────────────────────────────────────────────────────────
# Kernel density rather than a raw histogram, with three corrections that materially
# change the shape of the curves:
#
# 1. ZERO FILTER. 253,551 contested plan offers (4.8%) are recorded as exactly $0, and a
#    further 10,824 fall below 0.05x QPA. A $0 offer is not a valid IDR submission -- the
#    statute requires each party to submit a number -- so these are almost certainly blanks
#    and denials coded as zero rather than real offers. Left in, they form an atom at the
#    origin which the kernel then smears in both directions, producing a spurious spike and
#    a jagged left edge on every curve. Everything below KDE_LO is dropped.
# 2. BOUNDARY REFLECTION. An offer cannot be negative, so the support is [0, inf). A plain
#    KDE leaks mass across zero and biases the left edge downward. The estimator below is
#    the standard reflection estimator -- equivalent to running the KDE on the data
#    concatenated with its mirror image about zero and doubling the result:
#        f(x) = 1/(n*h) * SUM_i [ phi((x-xi)/h) + phi((x+xi)/h) ]
# 3. ROBUST BANDWIDTH, SHARED ACROSS SERIES. Scott's rule is unusable here: it scales
#    with the standard deviation, which the tail inflates to 33.7 for provider offers and
#    yields h = 1.53 -- wide enough to erase every feature in the distribution. Silverman's
#    robust variant, 0.9 * min(sd, IQR/1.349) * n^(-1/5), uses the IQR instead and lands at
#    0.177 / 0.161 / 0.014 for provider / prevailing / plan.
#
#    All three curves are then drawn with the WIDEST of those, not with their own. The three
#    ridges exist to be read against each other, and bandwidth is what sets apparent
#    roughness -- give the plan series its own 0.014 and it renders as a near-vertical
#    blade next to two smoothly-drawn neighbours, and the eye reads that contrast as a
#    property of the data rather than of the estimator. One bandwidth for all three makes
#    the comparison honest. It over-smooths the plan series relative to its own optimum;
#    that cost is paid knowingly, and the concentration it blurs is reported exactly in the
#    IQR beside the curve and in the "within +/-5% of QPA" figure on the overview.
#
# The 5.3M values never enter Python: DuckDB returns a 0.01-wide histogram and the kernel
# is convolved over the bin centres, which is accurate to O((binwidth/h)^2) -- under 2% at
# the narrowest bandwidth in play.
KDE_LO, KDE_HI, KDE_BIN = 0.05, 15.0, 0.01
KDE_XMAX, KDE_STEP, KDE_HMIN = 12.0, 0.05, 0.08

_centers = np.arange(0, KDE_HI, KDE_BIN) + KDE_BIN/2
_grid    = np.round(np.arange(0, KDE_XMAX + KDE_STEP/2, KDE_STEP), 4)

def _bandwidth(col):
    """Silverman's robust rule for one column."""
    st = Q(f"""SELECT count({col}) n, stddev_samp({col}) sd,
                 quantile_cont({col},0.25) p25, quantile_cont({col},0.75) p75
               FROM cont WHERE {col} >= {KDE_LO}""").iloc[0]
    n, sd, iqr = int(st['n']), float(st['sd']), float(st['p75'] - st['p25'])
    return max(0.9 * min(sd, iqr/1.349) * n ** (-0.2), KDE_HMIN), n

_h_own = {c: _bandwidth(c) for c in ('pm', 'plm', 'prm')}
KDE_H  = max(h for h, _ in _h_own.values())

def _density(col):
    """Reflection-corrected KDE for one offer column, returned as % of that series'
    offers per 0.15x band (the same unit the previous histogram used)."""
    h, n = KDE_H, _h_own[col][1]

    hist = Q(f"""SELECT CAST(floor({col}/{KDE_BIN}) AS INT) b, count(*) c
                 FROM cont WHERE {col} >= {KDE_LO} AND {col} < {KDE_HI}
                 GROUP BY 1 ORDER BY 1""")
    c = np.zeros(len(_centers))
    c[hist['b'].to_numpy()] = hist['c'].to_numpy()

    z1 = (_grid[:, None] - _centers[None, :]) / h
    z2 = (_grid[:, None] + _centers[None, :]) / h      # the mirrored half
    kern = np.exp(-0.5*z1*z1) + np.exp(-0.5*z2*z2)
    dens = (kern * c[None, :]).sum(axis=1) / (n * h * np.sqrt(2*np.pi))
    return dens * 0.15 * 100.0, h, n

_pm, _h_pm, _n_pm = _density('pm')
_pl, _h_pl, _n_pl = _density('plm')
_pv, _h_pv, _n_pv = _density('prm')
assert _h_pm == _h_pl == _h_pv == KDE_H
D['offer_kde'] = [{'x': float(x), 'prov': round(float(a),4),
                   'plan_n': round(float(b),4), 'prev': round(float(cc),4)}
                  for x, a, b, cc in zip(_grid, _pm, _pl, _pv)]

# Quantiles are recomputed over the same filtered population the curves describe, so the
# summary box under each ridge and the ridge itself refer to one and the same set of lines.
D['offer_iqr'] = recs(Q(f"""
SELECT 'Plan offer' AS series, count(plm) n, round(quantile_cont(plm,0.25),2) p25,
       round(median(plm),2) med, round(quantile_cont(plm,0.75),2) p75
  FROM cont WHERE plm >= {KDE_LO}
UNION ALL SELECT 'Provider offer', count(pm), round(quantile_cont(pm,0.25),2),
       round(median(pm),2), round(quantile_cont(pm,0.75),2)
  FROM cont WHERE pm >= {KDE_LO}
UNION ALL SELECT 'Prevailing offer', count(prm), round(quantile_cont(prm,0.25),2),
       round(median(prm),2), round(quantile_cont(prm,0.75),2)
  FROM cont WHERE prm >= {KDE_LO}"""))

D['offer_kde_meta'] = {
  'lo_cut': KDE_LO, 'grid_step': KDE_STEP, 'reflected': True,
  'bandwidth_rule': ("0.9 * min(sd, IQR/1.349) * n^(-1/5), floored at %.2f; the widest "
                     "of the three is then shared by all three so the curves are "
                     "comparably smoothed" % KDE_HMIN),
  'bandwidth': round(KDE_H, 4),
  'bandwidth_own': {'Provider offer': round(_h_own['pm'][0],4),
                    'Plan offer': round(_h_own['plm'][0],4),
                    'Prevailing offer': round(_h_own['prm'][0],4)},
  'unit': 'percent of the series\' offers per 0.15x band',
  'dropped_below_cut': recs(Q(f"""
    SELECT 'Provider offer' AS series, sum(CASE WHEN pm  < {KDE_LO} THEN 1 ELSE 0 END) dropped,
           sum(CASE WHEN pm=0  THEN 1 ELSE 0 END) exact_zero, count(pm) total FROM cont
    UNION ALL SELECT 'Plan offer', sum(CASE WHEN plm < {KDE_LO} THEN 1 ELSE 0 END),
           sum(CASE WHEN plm=0 THEN 1 ELSE 0 END), count(plm) FROM cont
    UNION ALL SELECT 'Prevailing offer', sum(CASE WHEN prm < {KDE_LO} THEN 1 ELSE 0 END),
           sum(CASE WHEN prm=0 THEN 1 ELSE 0 END), count(prm) FROM cont""")),
}


# prevailing-award brackets, contested only
D['prevailing_brackets'] = recs(Q("""
WITH t AS (SELECT count(prm) n FROM cont)
SELECT bucket, cnt, round(100.0*cnt/(SELECT n FROM t),2) pct, ord FROM (
  SELECT '<1×' bucket, count(*) cnt, 1 ord FROM cont WHERE prm<1
  UNION ALL SELECT '1–2×', count(*), 2 FROM cont WHERE prm>=1 AND prm<2
  UNION ALL SELECT '2–5×', count(*), 3 FROM cont WHERE prm>=2 AND prm<5
  UNION ALL SELECT '5–10×', count(*), 4 FROM cont WHERE prm>=5 AND prm<10
  UNION ALL SELECT '10–20×', count(*), 5 FROM cont WHERE prm>=10 AND prm<20
  UNION ALL SELECT '20–50×', count(*), 6 FROM cont WHERE prm>=20 AND prm<50
  UNION ALL SELECT '50×+', count(*), 7 FROM cont WHERE prm>=50
) ORDER BY ord"""))

D['extremes'] = recs(Q("""
WITH t AS (SELECT count(prm) n FROM cont)
SELECT (SELECT n FROM t) contested_n,
  sum(CASE WHEN prm>=5 THEN 1 ELSE 0 END) above5,
  round(100.0*sum(CASE WHEN prm>=5 THEN 1 ELSE 0 END)/(SELECT n FROM t),1) above5_pct,
  sum(CASE WHEN prm>=20 THEN 1 ELSE 0 END) above20,
  round(100.0*sum(CASE WHEN prm>=20 THEN 1 ELSE 0 END)/(SELECT n FROM t),1) above20_pct,
  sum(CASE WHEN prm>=50 THEN 1 ELSE 0 END) above50,
  round(100.0*sum(CASE WHEN prm>=50 THEN 1 ELSE 0 END)/(SELECT n FROM t),1) above50_pct
FROM cont"""))[0]

# ── Line-level outcome reconciliation — ties to the headline KPIs ────────────
# Outcome matrix. Line-level outcome classification, with the dispute-level fee fields
# allocated pro-rata across each dispute's line items so the rows sum back to the headline
# fee totals exactly. Fees shown are the portion borne by the PLAN: the administrative fee
# is paid by every party that submitted an offer (so a defaulting plan pays none), and the
# IDRE fee is ultimately borne by the losing party (refunded to the prevailing one).
# Both fee fields are dispute-level and have to be pushed down to line grain, but they do not
# distribute the same way, and treating them alike produced two figures that could not be true:
# IDRE fees appearing on rows where the plan WON.
#
# The cause was a grain mismatch. Spreading a dispute's IDRE fee across all of its lines means
# that on a batched dispute with mixed outcomes, the lines the plan won still picked up a share
# of a fee the plan only owes because it lost the other lines. The fee is real, but it does not
# belong on those rows.
#
#   ADMIN FEE  -- one charge per party per dispute, owed by anyone who submitted an offer and
#                 entirely independent of who won. It spreads evenly over every line of the
#                 dispute. A plan that defaulted submitted nothing and owes none.
#   IDRE FEE   -- one charge per dispute, paid up front by both sides and refunded to the
#                 prevailing party, so it is ultimately borne by the loser. The plan bears it
#                 only where the provider prevailed, and it is spread over just those lines.
#                 prov_won=1 guarantees prov_win_lines >= 1, so no dispute's fee is lost and the
#                 column still foots to the headline total exactly.
con.execute("""CREATE OR REPLACE VIEW line_fees AS
SELECT b.dispute, b.sel, b.prov_win, b.is_default, b.prm,
  (CASE WHEN d.plan_defaulted THEN 0 ELSE d.admin_rate END)/d.lines   plan_admin,
  (CASE WHEN d.prov_won=1 AND b.prov_win=1
        THEN d.fee/d.prov_win_lines ELSE 0 END)                       plan_idre
FROM base b JOIN dcomp d USING (dispute);""")

D['outcome_matrix'] = recs(Q("""
SELECT CASE
    WHEN is_default=1 AND prov_win=1 THEN 'Default — carrier never responded'
    WHEN is_default=1 AND prov_win=0 THEN 'Default — provider never responded'
    WHEN is_default=1                THEN 'Default — outcome not recorded'
    WHEN prov_win=1                  THEN 'Contested — provider offer chosen'
    WHEN prov_win=0                  THEN 'Contested — carrier offer chosen'
    ELSE 'Contested — outcome not recorded' END outcome,
  CASE WHEN is_default=1 THEN 'Default' ELSE 'Contested' END grp,
  CASE WHEN prov_win IS NULL THEN 'Unrecorded'
       WHEN prov_win=1       THEN 'Provider' ELSE 'Plan' END side,
  count(*) lines, count(DISTINCT dispute) disputes,
  round(100.0*count(*)/(SELECT count(*) FROM base),2) pct_all,
  round(median(prm),2) med_award_mult,
  round(sum(plan_admin)/1e6,2) admin_musd,
  round(sum(plan_idre)/1e6,2)  idre_musd
FROM line_fees GROUP BY 1,2,3 ORDER BY lines DESC"""))

# Group-level medians for the subtotal bands. A median of the row medians would be wrong,
# so each side is recomputed over its own pooled lines.
D['outcome_sides'] = recs(Q("""
SELECT CASE WHEN prov_win IS NULL THEN 'Unrecorded'
            WHEN prov_win=1        THEN 'Provider' ELSE 'Plan' END side,
  count(*) lines, round(median(prm),2) med_award_mult
FROM line_fees GROUP BY 1"""))

D['outcome_source'] = recs(Q("""
SELECT coalesce(sel_src,'none') src, count(*) lines,
  round(100.0*count(*)/(SELECT count(*) FROM base),2) pct
FROM base GROUP BY 1 ORDER BY lines DESC"""))

D['meta'] = {
    'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
    'quarters': [r['q'] for r in D['quarterly']],
    'source': 'CMS Federal IDR Public Use Files (OON Emergency & Non-Emergency)',
    'grain': 'Dispute Line Item (DLI)',
    'outcome_field': 'Offer Selected from Provider or Issuer, falling back to Payment Determination Outcome where blank',
    'trim_rule': f'offer multiples retained when {TRIM_LO} <= x <= {TRIM_HI}; count metrics untrimmed',
    'air_excluded': True,
    'parquet_source': PQ_DIR,
    'data_gaps': [
      'Certified IDR Entity and Date of Initiation exist only from 2025Q3 forward.',
      'Lines with no offer selected rise from 1.9% (2024Q1) to 7.2% (2025Q4).',
      'Offer-multiple coverage runs 77-88% per quarter; the remainder are CMS suppression '
      'markers (NR / N/R / ^ / + / *), not missing data.',
    ],
    'rebuild_note': (
      'Rebuilt from raw CMS files. 2024Q3-Q4 percent columns were previously 100% null '
      'because CMS ships them as percent-formatted text ("1,014%") in the May-2025 xlsx '
      'releases and the loader coerced them to NaN. Now parsed per value and rescaled; '
      '1.6M line items recovered. All other quarters reproduce the prior values exactly.'
    ),

}

os.makedirs('dashboard', exist_ok=True)
with open(OUT, 'w') as f:
    json.dump(D, f, separators=(',', ':'))
print(f"wrote {OUT}  ({os.path.getsize(OUT)/1024:.0f} KB)")
for k, v in D.items():
    print(f"  {k}: {len(v) if isinstance(v,list) else 'obj'}")
