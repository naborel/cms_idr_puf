#!/usr/bin/env python3
"""
Enrich the CMS Federal IDR Public Use File parquets.

Adds real dollar amounts to the OON file and precomputed ratios to the QPA file,
so the two can be joined and analysed directly.

Usage:
    py3 enrich_puf.py --src <folder with oon_all_quarters.parquet / qpa_all_quarters.parquet>
                      --out <output folder>

Needs duckdb only.  Peak memory is capped at --mem (default 4GB); the work spills
to a temp database beside the output, so it runs on a laptop.
"""
import argparse, os, sys, duckdb

NS = lambda c: rf"regexp_replace({c},'\.0+$','')"                      # "99284.0" -> "99284"
NP = lambda c: rf"case when {c} is null then '~' else lpad(regexp_replace({c},'\.0+$',''),2,'0') end"
NPN = lambda c: rf"case when {c} is null then null else lpad(regexp_replace({c},'\.0+$',''),2,'0') end"

RATIOS = "q,sc,pos,sel,pp,hp,vp,qm"
AGG = """count(*) nq, count(distinct qpa) nqpa, count(distinct po) npo, count(distinct ho) nho,
 median(qpa) qpa_m, min(qpa) qpa_lo, max(qpa) qpa_hi, median(po) po_m, median(ho) ho_m,
 median(vo) vo_m, mode(round(medqpa,2)) med_m, count(distinct rg) nrg, mode(rg) rg_m,
 count(distinct round(medqpa,2)) nmed"""
SEL = "t.nq,t.nqpa,t.npo,t.nho,t.nrg,t.nmed,t.rg_m,t.med_m,t.qpa_m,t.po_m,t.ho_m,t.vo_m"

F_FULL = ('Quarter + Service Code + Place of Service Code + Offer Selected + Dispute Line Item Type'
          ' + Initiating Party + Certified IDR Entity + Provider Offer % + Plan Offer % +'
          ' Prevailing Offer % + QPA % of Median')
F_NOID = ('Quarter + Service Code + Place of Service Code + Offer Selected + Dispute Line Item Type'
          ' + Provider Offer % + Plan Offer % + Prevailing Offer % + QPA % of Median')
F_RAT  = ('Quarter + Service Code + Place of Service Code + Offer Selected + Provider Offer % +'
          ' Plan Offer % + Prevailing Offer % + QPA % of Median')
F_CELL = 'Quarter + Service Code + Location of Service + QPA % of Median'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--src', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--mem', default='4GB')
    a = ap.parse_args()
    OON = os.path.join(a.src, 'oon_all_quarters.parquet')
    QPA = os.path.join(a.src, 'qpa_all_quarters.parquet')
    for p in (OON, QPA):
        if not os.path.exists(p):
            sys.exit(f'missing {p}')
    os.makedirs(a.out, exist_ok=True)
    work = os.path.join(a.out, '_enrich_work.duckdb')
    if os.path.exists(work):
        os.remove(work)
    c = duckdb.connect(work)
    c.execute(f"set memory_limit='{a.mem}'")
    c.execute("set preserve_insertion_order=false")
    c.execute("""create or replace macro rgstates(r) as
        str_split(regexp_extract(r,'([A-Z]{2}(?:-[A-Z]{2})*)$',1),'-')""")
    say = lambda s: print(s, flush=True)

    # ---- 1. the median QPA, CMS's own partition: service code x quarter x region, within quarter
    say('1/8  median QPA per service code x quarter x region')
    c.execute(f"""create table med as
        select "Quarter" q, {NS('"Service Code"')} sc, "Geographical Region" rg,
               quantile_cont("QPA",0.5) m, count(*) n
        from '{QPA}'
        where "QPA" is not null and "Geographical Region" is not null
        group by 1,2,3""")

    # ---- 2. QPA-side fingerprintable lines (contested, all four dollars present)
    say('2/8  QPA-side fingerprints')
    c.execute(f"""create table qf as
        select x."Quarter" q, {NS('x."Service Code"')} sc, {NP('x."Place of Service Code"')} pos,
          coalesce(x."Offer Selected from Provider or Issuer",'~') sel,
          coalesce(x."Dispute Line Item Type",'~') dd, coalesce(x."Initiating Party",'~') ip,
          coalesce(x."Certified IDR Entity",'~') idre, x."Geographical Region" rg,
          x."QPA" qpa, x."Provider/Facility Offer" po, x."Health Plan/Issuer Offer" ho,
          x."Prevailing Offer" vo, m.m medqpa,
          round(x."Provider/Facility Offer"/x."QPA",2) pp,
          round(x."Health Plan/Issuer Offer"/x."QPA",2) hp,
          round(x."Prevailing Offer"/x."QPA",2) vp,
          round(x."QPA"/m.m,2) qm
        from '{QPA}' x
        join med m on m.q=x."Quarter" and m.sc={NS('x."Service Code"')} and m.rg=x."Geographical Region"
        where x."QPA">0 and x."Provider/Facility Offer" is not null
          and x."Health Plan/Issuer Offer" is not null and x."Prevailing Offer" is not null
          and x."Default Decision"='No'""")

    # ---- 3. OON-side match keys
    say('3/8  OON-side keys')
    c.execute(f"""create table ok as
        select file_row_number frn, "Quarter" q, {NS('"Service Code"')} sc,
          {NP('"Place of Service Code"')} pos, "Location of Service" los,
          coalesce("Offer Selected from Provider or Issuer",'~') sel,
          coalesce("Dispute Line Item Type",'~') dd, coalesce("Initiating Party",'~') ip,
          coalesce("Certified IDR Entity",'~') idre,
          "Provider/Facility Offer as % of QPA" pp, "Health Plan/Issuer Offer as % of QPA" hp,
          "Prevailing Party Offer as % of QPA" vp, "QPA as Percent of Median QPA" qm
        from read_parquet('{OON}', file_row_number=true)""")
    c.execute(f"create table t1 as select {RATIOS},dd,ip,idre, {AGG} from qf group by {RATIOS},dd,ip,idre")
    c.execute(f"create table t2 as select {RATIOS},dd, {AGG} from qf group by {RATIOS},dd")
    c.execute(f"create table t3 as select {RATIOS}, {AGG} from qf where dd='~' group by {RATIOS}")
    c.execute(f"create table m1 as select {RATIOS},dd,ip,idre, count(*) n from ok where qm is not null group by {RATIOS},dd,ip,idre")
    c.execute(f"create table m2 as select {RATIOS},dd, count(*) n from ok where qm is not null group by {RATIOS},dd")

    # ---- 4. cell lookup: (quarter, code, state, published ratio) -> which dollars are possible
    say('4/8  cell lookup table')
    c.execute(f"""create table qv as
        select x."Quarter" q, {NS('x."Service Code"')} sc, x."Geographical Region" rg,
               round(x."QPA"/m.m,2) qm, x."QPA" qpa, m.m medq, count(*) n
        from '{QPA}' x
        join med m on m.q=x."Quarter" and m.sc={NS('x."Service Code"')} and m.rg=x."Geographical Region"
        where x."QPA">0 group by 1,2,3,4,5,6""")
    c.execute("""create table lk as
        with e as (select q,sc,qm,qpa,medq,rg,n, unnest(rgstates(rg)) st from qv)
        select q,sc,st,qm, count(distinct qpa) nvals, count(distinct rg) nregions, sum(n) nlines,
               arg_max(qpa,n) qpa_dom, arg_max(medq,n) medq_dom, arg_max(rg,n) rg_dom,
               min(qpa) qpa_lo, max(qpa) qpa_hi
        from e where st<>'' group by 1,2,3,4""")

    # ---- 5. fingerprint match, most specific field set first
    say('5/8  fingerprint match')
    J = lambda ks: " and ".join(f"t.{k}=o.{k}" for k in ks.split())
    j1, j2, j3 = J("q sc pos sel pp hp vp qm dd ip idre"), J("q sc pos sel pp hp vp qm dd"), J(RATIOS.replace(',', ' '))
    c.execute(f"create table fp as select o.frn,1 tier,{SEL},m.n oon_n from ok o join t1 t on {j1} join m1 m on {j1.replace('t.','m.')}")
    c.execute(f"""insert into fp select o.frn,2,{SEL},m.n from ok o join t2 t on {j2}
        join m2 m on {j2.replace('t.','m.')} left join fp f on f.frn=o.frn where f.frn is null""")
    c.execute(f"""insert into fp select o.frn,3,{SEL},null from ok o join t3 t on {j3}
        left join fp f on f.frn=o.frn where f.frn is null""")

    # ---- 6. assign region, median and dollars; record exactly which fields were used
    say('6/8  assignment')
    c.execute(f"""create table asg as
    with j as (
      select o.*, f.tier,f.nq,f.nqpa,f.npo,f.nho,f.nrg,f.nmed,f.rg_m,f.med_m,f.qpa_m,f.po_m,f.ho_m,f.vo_m,f.oon_n,
             k.nvals,k.qpa_dom,k.medq_dom,k.rg_dom,k.qpa_lo,k.qpa_hi,k.nlines
      from ok o left join fp f on f.frn=o.frn
      left join lk k on k.q=o.q and k.sc=o.sc and k.st=o.los and k.qm=o.qm),
    f0 as (select *, (tier is not null and nmed=1) fp_ok2 from j),
    s as (select *, fp_ok2 as fp_ok,
      case when fp_ok2 then rg_m when nvals is not null then rg_dom end rg_f,
      case when fp_ok2 then med_m when nvals is not null then medq_dom end medq_f,
      case when tier is not null and nqpa=1 then qpa_m
           when nvals=1 then qpa_dom
           when nvals is not null and (qpa_hi-qpa_lo)/nullif(qpa_lo,0)<=0.02 then qpa_dom
           when fp_ok2 then qm*med_m end qpa_f,
      case when tier is not null and nqpa=1 then 'Matched line (exact)'
           when nvals=1 then 'Cell lookup (exact)'
           when nvals is not null and (qpa_hi-qpa_lo)/nullif(qpa_lo,0)<=0.02 then 'Cell lookup (within 2%)'
           when fp_ok2 then 'Derived from median ratio (within 1%)' end qpa_src
      from f0)
    select frn, rg_f as rg, round(medq_f,2) as medq, round(qpa_f,2) as qpa,
      round(case when npo=1 then po_m else pp*qpa_f end,2) as po,
      round(case when nho=1 then ho_m else hp*qpa_f end,2) as ho,
      round(case when sel like 'In Favor of Provider%' then (case when npo=1 then po_m else pp*qpa_f end)
           when sel like 'In Favor of Plan%'     then (case when nho=1 then ho_m else hp*qpa_f end)
           else vp*qpa_f end,2) as vo,
      round(qpa_f-medq_f,2) as qpa_vs_med,
      round((case when sel like 'In Favor of Provider%' then (case when npo=1 then po_m else pp*qpa_f end)
           when sel like 'In Favor of Plan%'     then (case when nho=1 then ho_m else hp*qpa_f end)
           else vp*qpa_f end)-qpa_f,2) as award_over, qpa_src,
      case when fp_ok and tier=1 then 'Fingerprint, full'
           when fp_ok and tier=2 then 'Fingerprint, no party/IDRE'
           when fp_ok and tier=3 then 'Fingerprint, ratios only'
           when nvals is not null then 'Cell lookup'
           when tier is not null then 'Fingerprint, median not determinable' end as mth,
      case when fp_ok then 'Fingerprint cell'
           when nvals is not null then 'Cell lookup (highest-volume region)' end as med_src,
      case when qpa_f is null and qm is null then 'QPA as Percent of Median QPA not published - nothing to match on'
           when qpa_f is null and tier is not null and nmed>1 then 'Fingerprint group spans '||nmed::varchar||' different medians - not determinable'
           when qpa_f is null and nvals>1 then 'Cell lookup found '||nvals::varchar||' candidate dollars too far apart to choose'
           when qpa_f is null then 'No match on any field set'
           when fp_ok and nqpa=1 then 'Dollar and median both from fingerprint: '||
             (case when tier=1 then '{F_FULL}' when tier=2 then '{F_NOID}' else '{F_RAT}' end)
           when tier is not null and nqpa=1 then 'Dollar from fingerprint ('||
             (case when tier=1 then '{F_FULL}' when tier=2 then '{F_NOID}' else '{F_RAT}' end)||
             '); median and region from cell lookup ({F_CELL}) because the fingerprint group spans '||
             nmed::varchar||' medians'
           when fp_ok then 'Median from fingerprint ('||
             (case when tier=1 then '{F_FULL}' when tier=2 then '{F_NOID}' else '{F_RAT}' end)||
             '); dollar derived as QPA % of Median x median'
           else 'Dollar, median and region all from cell lookup: {F_CELL}' end as diag,
      case when tier is not null and nq=1 and oon_n=1 then 'Exact 1:1'
           when tier is not null then 'Fingerprint group'
           when nvals is not null then 'Cell lookup' end as mtyp,
      case when qpa_f is null or medq_f is null then null
           when abs(round(qpa_f/medq_f,2)-qm)<=0.01 then 'Consistent'
           else 'CHECK - ratio does not reconcile' end as rchk,
      nq, oon_n, nrg, nmed, nvals, nlines,
      case when qm is null then 'No published median ratio'
           when qpa_f is null then 'Unresolved' else 'Assigned' end as dst
    from s""")

    # ---- 7. write the enriched OON file
    say('7/8  writing enriched OON parquet')
    oon_out = os.path.join(a.out, 'oon_all_quarters_enriched.parquet')
    c.execute(f"""copy (
      select o.* exclude (file_row_number),
        f.rg "Geographical Region (linked)", f.medq "Median QPA ($)", f.qpa "QPA ($)",
        f.po "Provider/Facility Offer ($)", f.ho "Health Plan/Issuer Offer ($)",
        f.vo "Prevailing Offer ($)", f.qpa_vs_med "QPA vs Median QPA ($)",
        f.award_over "Award over QPA ($)", f.qpa_src "Dollar Source",
        f.med_src "Median Source", f.mth "Match Method", f.mtyp "Match Type",
        f.diag "Match Diagnostic", f.rchk "Ratio Check",
        f.nq "QPA Lines in Match", f.oon_n "OON Lines in Match", f.nrg "Regions in Match",
        f.nmed "Medians in Match", f.nvals "Candidate Dollars in Cell",
        f.nlines "QPA Lines in Cell", f.dst "Dollar Status"
      from read_parquet('{OON}', file_row_number=true) o join asg f on f.frn=o.file_row_number
    ) to '{oon_out}' (format parquet, compression zstd)""")

    # ---- 8. write the enriched QPA file
    say('8/8  writing enriched QPA parquet')
    qpa_out = os.path.join(a.out, 'qpa_all_quarters_enriched.parquet')
    c.execute(f"""copy (
      select x.*,
        {NS('x."Service Code"')} "Service Code (normalized)",
        {NPN('x."Place of Service Code"')} "Place of Service Code (normalized)",
        round(m.m,2) "Median QPA ($)",
        round(x."QPA"/m.m,2) "QPA as Percent of Median QPA (calculated)",
        round(x."Provider/Facility Offer"/nullif(x."QPA",0),2) "Provider/Facility Offer as % of QPA (calculated)",
        round(x."Health Plan/Issuer Offer"/nullif(x."QPA",0),2) "Health Plan/Issuer Offer as % of QPA (calculated)",
        round(x."Prevailing Offer"/nullif(x."QPA",0),2) "Prevailing Party Offer as % of QPA (calculated)",
        round(x."QPA"-m.m,2) "QPA vs Median QPA ($)",
        round(x."Prevailing Offer"-x."QPA",2) "Award over QPA ($)",
        case when m.m is null then 'No median (region not published)'
             when x."QPA" is null then 'No QPA dollar published' else 'Complete' end "Metric Status",
        case when m.m is null or x."QPA" is null or x."Provider/Facility Offer" is null
               or x."Health Plan/Issuer Offer" is null or x."Prevailing Offer" is null
               or x."Default Decision"<>'No' then null
          else concat_ws('|', x."Quarter", {NS('x."Service Code"')}, {NP('x."Place of Service Code"')},
            coalesce(x."Offer Selected from Provider or Issuer",'~'),
            coalesce(x."Dispute Line Item Type",'~'),
            round(x."Provider/Facility Offer"/x."QPA",2)::varchar,
            round(x."Health Plan/Issuer Offer"/x."QPA",2)::varchar,
            round(x."Prevailing Offer"/x."QPA",2)::varchar,
            round(x."QPA"/m.m,2)::varchar) end "Fingerprint",
        m.n "Lines in Median Cell"
      from '{QPA}' x
      left join med m on m.q=x."Quarter" and m.sc={NS('x."Service Code"')} and m.rg=x."Geographical Region"
    ) to '{qpa_out}' (format parquet, compression zstd)""")

    for lbl, p, src in (('OON', oon_out, OON), ('QPA', qpa_out, QPA)):
        n = c.sql(f"select count(*) from '{p}'").fetchone()[0]
        n0 = c.sql(f"select count(*) from '{src}'").fetchone()[0]
        flag = 'OK' if n == n0 else '*** ROW COUNT MISMATCH ***'
        say(f'  {lbl}: {n:,} rows (source {n0:,}) {flag}  {os.path.getsize(p)/1e6:.0f} MB')
    say('\nAssignment summary:')
    print(c.sql(f"""select "Dollar Status" status, count(*) oon_lines,
        round(100.0*count(*)/sum(count(*)) over (),2) pct
        from '{oon_out}' group by 1 order by 2 desc""").df().to_string(index=False))
    c.close()
    os.remove(work)


if __name__ == '__main__':
    main()
