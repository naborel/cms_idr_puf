#!/usr/bin/env python3
"""
Add two columns to the provider filer crosswalk:

  filer_parent -- the organisation that actually owns the filer. Radiology Partners files
                  under each affiliated practice's own name and NPIs, so the practices appear
                  as five separate mid-sized filers instead of one very large one.

  filer_class  -- what the filer IS economically, replacing the clinical labels (Radiology
                  group, Anesthesia group, Emergency dept operator) that only repeated what
                  the Specialty column already says. Five values:

                    PE / For-Profit   investor-owned groups and the firms whose product is
                                      the dispute itself
                    Billing / RCM     revenue-cycle vendors filing on a practice's behalf
                    Law Firm
                    Hospital System   health systems, non-profit and investor-owned alike
                    Physician-Owned   practices still owned by the clinicians in them

Ownership is sourced, not assumed -- see SOURCES below. Anything without evidence of investor
ownership stays Physician-Owned; the conservative direction for a client-facing file.
"""
import sys, pyarrow.parquet as pq, pyarrow as pa, pandas as pd

SOURCES = {
 "TeamHealth":            "Blackstone — Private Equity Stakeholder Project",
 "Envision Healthcare":   "KKR, then creditor-owned after the 2023 Chapter 11 — PESP",
 "Radiology Partners":    "PE-backed — PESP; Aetna v. Radiology Partners cites 'its private equity owners'",
 "US Anesthesia Partners":"Welsh, Carson, Anderson & Stowe",
 "SCP Health":            "Onex — Onex's own portfolio listing",
 "SpecialtyCare":         "Kohlberg & Company (sold 2021, still investor-owned)",
 "HaloMD":                "Founder-led, NOT PE-backed per PESP; classed here for business model, not ownership",
 "US Acute Care Solutions":"Physician owners bought out Welsh Carson in 2021 — physician-owned",
 "Vituity":               "Physician-owned partnership",
}

# Radiology Partners practices, each confirmed on radpartners.com or the practice's own site.
RADPARTNERS = {
 "Singleton Associates":          "radpartners.com press release, Apr 2025 (Cigna agreement)",
 "Sonoran Radiology":             "radpartners.com press release, May 2023 (BCBS Arizona)",
 "Mori, Bean & Brooks":           "mbb.radpartners.com",
 "Imaging Associates of Indiana": "iai-wir.com — 'a Radiology Partners practice'",
 "Radiology Alliance":            "radpartners.com press release, Sep 2023 (BCBS Tennessee)",
}

# Investor-owned, or a firm whose product is the arbitration rather than the care.
PE_FORPROFIT = {
 "HaloMD","TeamHealth","Envision Healthcare","SCP Health","US Anesthesia Partners",
 "SpecialtyCare","Sound Physicians","ApolloMD","OrthoMed Staffing","TotalCare ER",
 "Altus Community Healthcare","Complete Care","Memorial Village ER","NMA IONM",
 "Radiology Partners",
}
HOSPITAL = {"Prime Healthcare","Baptist Memorial Health","HCA Healthcare","CommonSpirit Health",
            "AdventHealth"}

def classify(group, ftype):
    if group in PE_FORPROFIT:                      return "PE / For-Profit"
    if group in HOSPITAL or ftype == "Hospital / health system": return "Hospital System"
    if ftype == "Law firm":                        return "Law Firm"
    if ftype == "RCM / billing vendor":            return "Billing / RCM"
    if ftype == "IDR specialist":                  return "PE / For-Profit"
    if ftype == "Individual":                      return "Individual"
    return "Physician-Owned"

def main(path, out):
    t = pq.read_table(path).to_pandas()
    t["filer_parent"] = t["filer_group"].map(lambda g: "Radiology Partners" if g in RADPARTNERS else g)
    # an affiliate inherits its parent's class, so the five RP practices read as PE / For-Profit
    t["filer_class"]  = [classify(p, ft) for p, ft in zip(t["filer_parent"], t["filer_type"])]
    pq.write_table(pa.Table.from_pandas(t, preserve_index=False), out, compression="zstd")

    g = t.groupby("filer_class")["n"].agg(["sum","count"]).sort_values("sum", ascending=False)
    print("filer_class:")
    for k, r in g.iterrows(): print("  %-18s %10s lines  %4d domains" % (k, f"{int(r['sum']):,}", r["count"]))
    rp = t[t.filer_parent == "Radiology Partners"]
    print("\nRadiology Partners rollup: %s lines across %d practices" %
          (f"{int(rp.n.sum()):,}", rp.filer_group.nunique()))
    for grp, n in rp.groupby("filer_group")["n"].sum().sort_values(ascending=False).items():
        print("   %-34s %10s   %s" % (grp, f"{int(n):,}", RADPARTNERS.get(grp,"")))
    print("\nwrote", out)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
