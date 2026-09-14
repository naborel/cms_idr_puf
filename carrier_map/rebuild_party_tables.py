"""
Regenerate the carrier and provider tables in dashboard/data.json from the normalised
crosswalks. Keeps the existing key names so the dashboard renderers keep working, and adds
the new columns (parent, business model, derived specialty, default rate, median ask).

Run:  python rebuild_party_tables.py <oon.parquet> <carrier_crosswalk.parquet>
                                     <provider_filer_crosswalk.parquet> <data.json>
"""
import duckdb, json, sys

OON, CW, PW, DJ = sys.argv[1:5]
con=duckdb.connect(); con.execute("SET memory_limit='2.5GB'")
con.execute(f"CREATE OR REPLACE VIEW cm AS SELECT * FROM read_parquet('{CW}')")
con.execute(f"CREATE OR REPLACE VIEW pf AS SELECT * FROM read_parquet('{PW}')")
con.execute(f"""CREATE OR REPLACE TABLE b AS SELECT
  "Dispute Number" disp, "Quarter" q, try_cast("Service Code" AS INT) sc,
  CASE WHEN "Default Decision"='Yes' THEN 1 ELSE 0 END isd,
  CASE WHEN coalesce("Offer Selected from Provider or Issuer","Payment Determination Outcome")
         LIKE 'In Favor of Provider%' THEN 1
       WHEN coalesce("Offer Selected from Provider or Issuer","Payment Determination Outcome")
         LIKE 'In Favor of Plan%' THEN 0 END pw,
  CASE WHEN "Provider/Facility Offer as % of QPA"  BETWEEN 0 AND 1000 THEN "Provider/Facility Offer as % of QPA" END pm,
  CASE WHEN "Health Plan/Issuer Offer as % of QPA" BETWEEN 0 AND 1000 THEN "Health Plan/Issuer Offer as % of QPA" END plm,
  CASE WHEN "Prevailing Party Offer as % of QPA"   BETWEEN 0 AND 1000 THEN "Prevailing Party Offer as % of QPA" END prm,
  "Health Plan Type" pt,
  lower(coalesce("Provider Email Domain",'')) pd,
  upper(coalesce("Health Plan/Issuer Name",'')) hn,
  lower(coalesce("Health Plan/Issuer Email Domain",'')) hd
FROM read_parquet('{OON}')""")
TOT=con.execute("SELECT count(*) FROM b").fetchone()[0]

# Specialty is DERIVED from each filer's own service-code mix rather than asserted by hand.
# The audit that motivated this found SpecialtyCare labelled a "physician group" while billing
# 86% neuromonitoring, and OrthoMed Staffing labelled likewise while billing 88% anesthesia.
con.execute("""CREATE OR REPLACE VIEW spec AS
SELECT f, CASE WHEN greatest(ed,rad,anes,ionm,lab)<35 THEN 'Mixed'
       WHEN ed  >=greatest(rad,anes,ionm,lab) THEN 'Emergency medicine'
       WHEN rad >=greatest(ed,anes,ionm,lab)  THEN 'Radiology'
       WHEN anes>=greatest(ed,rad,ionm,lab)   THEN 'Anesthesia'
       WHEN ionm>=greatest(ed,rad,anes,lab)   THEN 'Neuromonitoring'
       ELSE 'Lab & pathology' END specialty FROM (
  SELECT pf.filer_group f,
    100.0*sum(CASE WHEN sc BETWEEN 99281 AND 99292 THEN 1 ELSE 0 END)/count(*) ed,
    100.0*sum(CASE WHEN sc BETWEEN 70000 AND 79999 THEN 1 ELSE 0 END)/count(*) rad,
    100.0*sum(CASE WHEN sc BETWEEN 0 AND 1999 THEN 1 ELSE 0 END)/count(*) anes,
    100.0*sum(CASE WHEN sc IN (95938,95939,95940,95941,95955,95822) THEN 1 ELSE 0 END)/count(*) ionm,
    100.0*sum(CASE WHEN sc BETWEEN 80000 AND 89999 THEN 1 ELSE 0 END)/count(*) lab
  FROM b JOIN pf ON b.pd=pf.dom WHERE pf.filer_group IS NOT NULL GROUP BY 1)""")
recs=lambda df: json.loads(df.to_json(orient='records'))
Q=lambda s: con.execute(s).df()

D=json.load(open(DJ, encoding='utf-8'))

D['provider_groups']=recs(Q(f"""
SELECT pf.filer_group pgroup, mode(pf.filer_type) pcat, any_value(s.specialty) specialty,
  count(*) lines, count(DISTINCT disp) disputes,
  round(100.0*count(*)/{TOT},2) share_pct,
  round(100.0*sum(pw)/nullif(count(pw),0),1) prov_win_pct,
  round(100.0*avg(isd),1) default_pct,
  round(median(pm),2) med_prov_mult, round(median(prm),2) med_prev_mult
FROM b JOIN pf ON b.pd=pf.dom LEFT JOIN spec s ON s.f=pf.filer_group
WHERE pf.filer_group IS NOT NULL GROUP BY 1 ORDER BY lines DESC LIMIT 25"""))

D['provider_categories']=recs(Q("""
SELECT pf.filer_type pcat, count(*) lines, count(DISTINCT pf.dom) filers,
  count(DISTINCT b.disp) disputes,
  round(100.0*sum(pw)/nullif(count(pw),0),1) prov_win_pct,
  round(100.0*avg(isd),1) default_pct, round(median(pm),2) med_prov_mult
FROM b JOIN pf ON b.pd=pf.dom WHERE pf.filer_group IS NOT NULL
GROUP BY 1 ORDER BY lines DESC"""))

D['carriers']=recs(Q(f"""
SELECT cm.carrier_group carrier, mode(cm.carrier_parent) parent, mode(cm.carrier_type) ctype,
  count(*) lines, count(DISTINCT disp) disputes, round(100.0*count(*)/{TOT},2) share_pct,
  round(100.0*sum(pw)/nullif(count(pw),0),1) prov_win_pct,
  round(100.0*avg(isd),1) default_pct,
  round(median(plm),2) med_plan_mult, round(median(prm),2) med_prev_mult,
  round(median(pm),2) med_prov_mult,
  round(100.0*sum(CASE WHEN plm BETWEEN 0.95 AND 1.05 THEN 1 ELSE 0 END)
        /nullif(count(plm),0),1) plan_at_qpa_pct
FROM b JOIN cm ON b.hn=cm.nm AND b.hd=cm.dom
WHERE cm.carrier_group IS NOT NULL AND cm.carrier_type<>'Employer / sponsor'
GROUP BY 1 ORDER BY lines DESC"""))

# who filed on behalf of whom -- the vendor layer, kept as its own table
D['submitters']=recs(Q(f"""
SELECT cm.submitter_group submitter, count(*) lines, round(100.0*count(*)/{TOT},2) share_pct,
  count(DISTINCT cm.carrier_group) carriers_served
FROM b JOIN cm ON b.hn=cm.nm AND b.hd=cm.dom
WHERE cm.submitter_group IS NOT NULL GROUP BY 1 ORDER BY lines DESC"""))


# Quarterly series for the trend charts. These were previously left on the old mapping AND
# emitted in alphabetical order, while the renderer took the first five rows it saw -- so the
# charts silently showed Aetna..Cigna and dropped UnitedHealthcare, the largest carrier in the
# file, off the end of the alphabet. Emitted volume-ranked here; the renderer now also picks
# its five from the volume-sorted table rather than from row order, so neither alone can
# reintroduce the bug.
TOPC=[r['carrier'] for r in D['carriers'][:8]]
TOPP=[r['pgroup']  for r in D['provider_groups'][:8]]
qlist=lambda xs: ",".join("'"+x.replace("'","''")+"'" for x in xs)

D['carrier_quarterly']=recs(Q(f"""
SELECT cm.carrier_group carrier, b.q, count(*) lines, count(DISTINCT b.disp) disputes,
  round(100.0*sum(pw)/nullif(count(pw),0),2) prov_win_pct,
  round(100.0*avg(isd),2) default_pct, round(median(plm),2) med_plan_mult
FROM b JOIN cm ON b.hn=cm.nm AND b.hd=cm.dom
WHERE cm.carrier_group IN ({qlist(TOPC)})
GROUP BY 1,2 ORDER BY (SELECT count(*) FROM b b2 JOIN cm c2 ON b2.hn=c2.nm AND b2.hd=c2.dom
                       WHERE c2.carrier_group=cm.carrier_group) DESC, b.q"""))

D['provider_quarterly']=recs(Q(f"""
SELECT pf.filer_group pgroup, b.q, count(*) lines, count(DISTINCT b.disp) disputes,
  round(100.0*sum(pw)/nullif(count(pw),0),2) prov_win_pct,
  round(100.0*avg(isd),2) default_pct, round(median(pm),2) med_prov_mult
FROM b JOIN pf ON b.pd=pf.dom
WHERE pf.filer_group IN ({qlist(TOPP)})
GROUP BY 1,2 ORDER BY (SELECT count(*) FROM b b3 JOIN pf p3 ON b3.pd=p3.dom
                       WHERE p3.filer_group=pf.filer_group) DESC, b.q"""))


# Year-over-year default rate for the top plans. The three quarterly line charts this replaces
# carried almost nothing: volume simply restated the overview's growth chart, and provider win
# rate sat in an 11-24 point band for four of the five plans. All the movement was in the
# default series -- Aetna 27.9% -> 3.6%, BCBS Texas 35.6% -> 16.1%, UnitedHealthcare 8.6% ->
# 9.9% -- and a 12-point spaghetti chart is the wrong way to show a start and an end.
D['carrier_yoy']=recs(Q("""
SELECT cm.carrier_group carrier,
  round(100.0*avg(CASE WHEN substr(b.q,1,4)='2024' THEN isd END),1) def_2024,
  round(100.0*avg(CASE WHEN substr(b.q,1,4)='2025' THEN isd END),1) def_2025,
  round(100.0*avg(CASE WHEN substr(b.q,1,4)='2024' THEN pw END),1) win_2024,
  round(100.0*avg(CASE WHEN substr(b.q,1,4)='2025' THEN pw END),1) win_2025,
  sum(CASE WHEN substr(b.q,1,4)='2025' THEN 1 ELSE 0 END) lines_2025
FROM b JOIN cm ON b.hn=cm.nm AND b.hd=cm.dom
WHERE cm.carrier_group IN (SELECT carrier FROM (SELECT cm2.carrier_group carrier, count(*) n
      FROM b b2 JOIN cm cm2 ON b2.hn=cm2.nm AND b2.hd=cm2.dom
      WHERE cm2.carrier_group IS NOT NULL AND cm2.carrier_type<>'Employer / sponsor'
      GROUP BY 1 ORDER BY n DESC LIMIT 10))
GROUP BY 1 HAVING count(*)>0 ORDER BY lines_2025 DESC"""))


# Self-funded vs fully insured, per carrier: does a carrier behave differently when the loss
# is its own money rather than its client's?
#
# THE UNLABELLED BUCKET. "No Plan/Issuer Response" is itself a value of Health Plan Type --
# 723,189 lines holding 473,703 defaults. Simply dropping them understates the self-funded
# default rate, because those lines are overwhelmingly non-responses and the self-funded book
# is the larger one. They are therefore ALLOCATED, not excluded.
#
# Allocation rule: each carrier's unlabelled lines (and its unlabelled defaults) are split
# between its two books in proportion to that carrier's OWN observed self-funded : fully-insured
# ratio. Per-carrier rather than one global share, because the unlabelled share swings from 2.8%
# of UnitedHealthcare's volume to 30.4% of Florida Blue's, and the book mix itself ranges from
# 93% self-funded (Aetna) to 69% (Anthem) -- a single flat percentage would misallocate both.
#
# Two things make this defensible rather than convenient:
#   1. It is the CONSERVATIVE direction. The unlabelled pool is 65.5% default; handing most of
#      it to the larger self-funded book pushes the self-funded rate up and NARROWS the gap.
#      The allocation works against the finding, and the finding survives it 5 of 5.
#   2. It cannot be done better from this file. Plan type is effectively dispute-level -- only
#      13 of 252,676 disputes containing an unlabelled line also contain a typed one -- so there
#      is no within-dispute imputation available.
# Both the measured and allocated figures are emitted, and the dashboard shows both.
con.execute("""CREATE OR REPLACE VIEW ptb AS SELECT *,
  CASE WHEN pt LIKE 'Either partially or fully self-insured%' THEN 'SF'
       WHEN pt = 'Fully insured private group health plan'    THEN 'FI'
       WHEN pt = 'No Plan/Issuer Response'                    THEN 'NPR' END book
FROM b""")

def _bytype(col, key):
    raw = Q(f"""SELECT cm.{col} g,
        sum(CASE WHEN p.book='SF'  THEN 1 ELSE 0 END) sfn,
        sum(CASE WHEN p.book='SF'  THEN p.isd ELSE 0 END) sfd,
        100.0*sum(CASE WHEN p.book='SF' THEN p.pw END)/nullif(count(CASE WHEN p.book='SF' THEN p.pw END),0) sfw,
        sum(CASE WHEN p.book='FI'  THEN 1 ELSE 0 END) fin,
        sum(CASE WHEN p.book='FI'  THEN p.isd ELSE 0 END) fid,
        100.0*sum(CASE WHEN p.book='FI' THEN p.pw END)/nullif(count(CASE WHEN p.book='FI' THEN p.pw END),0) fiw,
        sum(CASE WHEN p.book='NPR' THEN 1 ELSE 0 END) nn,
        sum(CASE WHEN p.book='NPR' THEN p.isd ELSE 0 END) nd
      FROM ptb p JOIN cm ON p.hn=cm.nm AND p.hd=cm.dom
      WHERE cm.{col} IS NOT NULL AND cm.carrier_type<>'Employer / sponsor'
      GROUP BY 1 HAVING sfn>20000 AND fin>5000 ORDER BY sfn DESC LIMIT 5""")
    out=[]
    for r in raw.itertuples():
        share = r.sfn/(r.sfn+r.fin)
        out.append({key: r.g,
            'sf_lines': int(r.sfn), 'fi_lines': int(r.fin), 'unlabelled_lines': int(r.nn),
            'sf_default': round(100*r.sfd/r.sfn,1), 'fi_default': round(100*r.fid/r.fin,1),
            'sf_default_adj': round(100*(r.sfd+share*r.nd)/(r.sfn+share*r.nn),1),
            'fi_default_adj': round(100*(r.fid+(1-share)*r.nd)/(r.fin+(1-share)*r.nn),1),
            'sf_win': None if r.sfw is None else round(r.sfw,1),
            'fi_win': None if r.fiw is None else round(r.fiw,1),
            'sf_share_of_book': round(100*share,1)})
    return out

D['book_by_plan']   = _bytype('carrier_group','carrier')
D['book_by_parent'] = _bytype('carrier_parent','parent')

json.dump(D, open(DJ,'w',encoding='utf-8'))
print("quarterly series rebuilt: carriers {} / filers {}".format(len(TOPC),len(TOPP)))

print("data.json updated: {} carriers, {} filers, {} categories, {} submitters".format(
  len(D['carriers']),len(D['provider_groups']),len(D['provider_categories']),len(D['submitters'])))
