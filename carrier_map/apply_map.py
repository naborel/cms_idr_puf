import duckdb, re, sys
sys.path.insert(0,'/home/claude/map')
import carrier_rules as R

con=duckdb.connect(); con.execute("SET memory_limit='2.5GB'")
OON='/mnt/user-data/uploads/cms_idr_puf/parquet_rebuilt/oon_all_quarters.parquet'
pairs=con.execute(f"""SELECT upper(coalesce("Health Plan/Issuer Name",'')) nm,
  lower(coalesce("Health Plan/Issuer Email Domain",'')) dom, count(*) n
FROM read_parquet('{OON}') GROUP BY 1,2""").fetchall()

CR=[(re.compile(p),g,par,t) for p,g,par,t in R.CARRIER_RULES]
XR=[(re.compile(p),g,par,t) for p,g,par,t in R.EXTRA_NAME_RULES]
DR=[(re.compile(p),g,t) for p,g,t in R.DOMAIN_RULES]
VENDORS={'MultiPlan / Claritev','ClearHealth Strategies','Zelis','Other repricing vendor'}

def resolve(nm,dom):
    for rx,g,par,t in XR:                      # explicit overrides first
        if rx.search(nm): return (g,par,t,'name-override') if g else (None,None,None,'vendor-desk')
    for rx,g,par,t in CR:                      # then the plan name
        if rx.search(nm): return g,par,t,'name'
    if dom in R.DOMAIN_CARRIER:                # then a domain a single plan owns
        g,par,t=R.DOMAIN_CARRIER[dom]; return g,par,t,'domain'
    for rx,g,t in DR:                          # then a carrier-owned domain
        if rx.search(dom) and g not in VENDORS and g!='Blues plan': return g,g,t,'domain'
    # A name that matches no carrier rule, arriving on a repricing vendor's domain, is
    # almost always the SELF-FUNDED EMPLOYER (JPMorgan Chase, Southwest Airlines, a school
    # district). The carrier genuinely is not in the record; saying so beats a null.
    for rx,g,t in DR:
        if rx.search(dom) and g in VENDORS:
            return "Plan sponsor named (carrier not identified)","Unknown","Employer / sponsor","sponsor"
    return None,None,None,None
def submitter(dom):
    for rx,g,t in DR:
        if rx.search(dom): return g,t
    return ('Other / direct', 'Unclassified') if dom else (None,None)

rows=[]
for nm,dom,n in pairs:
    cg,cp,ct,src=resolve(nm,dom); sg,st=submitter(dom)
    rows.append((nm,dom,n,cg,cp,ct,src,sg,st))
con.execute("""CREATE OR REPLACE TABLE m(nm VARCHAR,dom VARCHAR,n BIGINT,carrier_group VARCHAR,
  carrier_parent VARCHAR,carrier_type VARCHAR,src VARCHAR,submitter_group VARCHAR,submitter_type VARCHAR)""")
con.executemany("INSERT INTO m VALUES (?,?,?,?,?,?,?,?,?)", rows)
con.execute("COPY m TO '/home/claude/map/pairs.parquet' (FORMAT PARQUET)")

tot=con.execute("SELECT sum(n) FROM m").fetchone()[0]
r=con.execute("""SELECT sum(CASE WHEN carrier_group IS NOT NULL THEN n ELSE 0 END),
  sum(CASE WHEN src='name' OR src='name-override' THEN n ELSE 0 END),
  sum(CASE WHEN src='domain' THEN n ELSE 0 END),
  sum(CASE WHEN src='vendor-desk' THEN n ELSE 0 END) FROM m""").fetchone()
print("COVERAGE on {:,} lines".format(tot))
print("  carrier_group resolved : {:>9,}  ({:.2f}%)".format(r[0],100*r[0]/tot))
print("     - from the plan name: {:.2f}%".format(100*r[1]/tot))
print("     - from the domain   : {:.2f}%".format(100*r[2]/tot))
print("  vendor desk, payer not identifiable: {:,} ({:.2f}%)".format(r[3],100*r[3]/tot))
print("  UNRESOLVED             : {:>9,}  ({:.2f}%)".format(tot-r[0]-r[3],100*(tot-r[0]-r[3])/tot))
print("\nTop UNRESOLVED remaining:")
for x in con.execute("""SELECT nm,dom,sum(n) v FROM m WHERE carrier_group IS NULL AND src IS NULL
  GROUP BY 1,2 ORDER BY v DESC LIMIT 22""").fetchall():
    print("   %-44s %-26s %8d"%(x[0][:44],x[1][:26],x[2]))
