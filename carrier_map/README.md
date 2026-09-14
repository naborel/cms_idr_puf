# Carrier & provider normalisation for the CMS IDR public use files

## What this is

Two crosswalks that turn the free-text payer/provider fields into something you can filter on.

| File | Rows | Join key |
|---|---|---|
| `carrier_crosswalk.parquet` / `.csv` | 30,168 | `UPPER(TRIM("Health Plan/Issuer Name"))` + `LOWER("Health Plan/Issuer Email Domain")` |
| `provider_filer_crosswalk.parquet` / `.csv` | 849 | `LOWER("Provider Email Domain")` |

`carrier_rules.py`, `provider_rules.py` and `apply_map.py` regenerate them from the parquet.

```sql
SELECT b.*, c.carrier_group, c.carrier_parent, c.carrier_type, c.submitter_group
FROM oon b
LEFT JOIN carrier_crosswalk c
  ON  upper(coalesce(b."Health Plan/Issuer Name",''))          = c.nm
  AND lower(coalesce(b."Health Plan/Issuer Email Domain",''))  = c.dom
```

## Coverage

| | Result |
|---|---|
| carrier_group resolved | **99.06%** of 8,233,903 lines |
| — from the plan name | 92.26% |
| — from the domain (name too generic) | 6.10% |
| vendor desk, payer genuinely not in the record | 0.19% |
| unresolved | 0.76% |
| provider filer resolved | **99.24%**, 133 domains |

`carrier_group` collapses to **127 values**, from 1,715 bare email domains.

## The thing that matters: two fields, not one

Neither the name nor the domain is trustworthy alone, and the file proves it:

- `multiplan.com` is 64% Cigna but also carries Kaiser, Arkansas BCBS and Horizon.
- `clearhs.com` is 78% UMR **and** Meritain — UnitedHealthcare and Aetna under one domain.
- `bcbsil.com` is 55% Blue Cross plans of **Texas and Oklahoma**, not Illinois. HCSC runs all
  five of its plans off shared infrastructure.
- `bcbstx.com` *is* genuinely BCBS Texas — every name variant resolves to Texas.

So there are two independent fields:

- **`submitter_group`** — who handled the dispute, from the email domain.
- **`carrier_group`** — whose money is at stake, from the plan name, falling back to the domain
  only where a single plan owns it. **This is the field to filter on.**

## What this corrects

`Carrier_Group` in the current parquet treated repricing vendors as carriers. Re-resolved:

| Carrier | Old | New | Change |
|---|---|---|---|
| **Cigna** | 481,206 | **1,100,865** | **+619,659** |
| **UnitedHealthcare** | 1,864,204 | **2,316,010** | **+451,806** |
| MultiPlan/Claritev | 806,879 | 0 (now a submitter) | −806,879 |
| ClearHealth Strategies | 553,397 | 0 (now a submitter) | −553,397 |
| BCBS Illinois | 117,820 | 10,195 | −107,625 |
| Horizon BCBS NJ | 17,925 | 80,714 | +62,789 |
| BCBS Texas | 1,422,454 | 1,484,409 | +61,955 |
| Kaiser Permanente | 101 | 59,351 | +59,250 |
| Aetna | 1,382,691 | 1,434,974 | +52,283 |

Where the vendor-filed volume actually belongs:

| Submitter | True carrier | Lines |
|---|---|---|
| MultiPlan / Claritev | Cigna | 566,050 |
| ClearHealth Strategies | UnitedHealthcare | 460,356 |
| MultiPlan / Claritev | Horizon BCBS NJ | 63,300 |
| MultiPlan / Claritev | Kaiser Permanente | 56,571 |
| Zelis | Cigna | 50,954 |
| ClearHealth Strategies | Aetna | 47,999 |

**Cigna's dispute volume was understated by 2.3×.** BCBS Illinois was overstated 11× by disputes
that belong to Texas and Oklahoma.

## Categories

`carrier_type`: Carrier · Blues licensee · TPA / ASO · Provider-sponsored · Union / Taft-Hartley ·
Government · Employer / sponsor

| Type | Lines | Share | Groups |
|---|---|---|---|
| Carrier | 5,639,929 | 68.50% | 40 |
| Blues licensee | 2,339,391 | 28.41% | 38 |
| TPA / ASO | 66,894 | 0.81% | 23 |
| Employer / sponsor | 57,330 | 0.70% | 1 |
| Provider-sponsored | 44,552 | 0.54% | 22 |

## Honest edges

- **`Plan sponsor named (carrier not identified)`** (57,330 lines). A name matching no carrier
  rule arriving on a repricing vendor's domain is the self-funded **employer** — JPMorgan Chase,
  Southwest Airlines, USAA, a school district. The carrier is genuinely absent from the record.
  Saying so beats a null, but do not read these as a carrier.
- **`BCBS — HCSC (state not identified)`** (10,310 lines). Generic "BCBS" on `bcbsil.com`. HCSC
  could be any of five states; guessing Illinois would put the wrong carrier behind a filter.
- **Vendor desk** (15,463 lines). "CHS IDR DEPT." and similar — a vendor's own IDR mailbox with
  no payer named.
- **Unresolved** (0.76%). Long tail of typos and one-off plans; safe to bucket as Other.

## Provider side — deliberately not symmetrical

A carrier's identity is a small closed set. A provider's is not: 19,396 group names and 37,605
facility names are mostly genuinely different practices, and collapsing them destroys real
information. What *is* a small closed set is the **filer** — usually a revenue-cycle vendor, an
IDR specialist or a law firm rather than the practice. `halomd.com` files under 725 distinct
NPIs; `mdcapitaladvisors.com` under 1,215; `gottliebandgreenspan.com` under 639.

So the provider crosswalk names the filer and leaves the practice as NPI + group name.

| Filer type | Lines | Share | NPIs |
|---|---|---|---|
| Physician group | 1,972,683 | 23.96% | 11,788 |
| RCM / billing vendor | 1,782,650 | 21.65% | 4,052 |
| Radiology group | 1,527,448 | 18.55% | 156 |
| IDR specialist | 1,094,131 | 13.29% | 784 |
| Hospital / health system | 749,345 | 9.10% | 840 |
| Emergency dept operator | 554,884 | 6.74% | 251 |
| Law firm | 226,895 | 2.76% | 2,233 |
| Anesthesia group | 152,829 | 1.86% | 184 |
| Neuromonitoring (IONM) | 74,386 | 0.90% | 194 |

Top filers: HaloMD 1,067,504 (12.96%) · Singleton Associates 802,057 · TeamHealth 787,572 ·
F&A Management 597,768 · Envision Healthcare 418,293 · Prime Healthcare 353,720.

**HaloMD is the provider-side MultiPlan** — an IDR specialist filing under 725 NPIs, the single
largest source of dispute volume in the file at 13%.

## Not yet applied to the dashboard

The dashboard's Carriers page still reads the old `Carrier_Group`, so it currently shows
MultiPlan as a carrier at ~10% share and understates Cigna by more than half. Re-running
`build_dashboard_data.py` against the crosswalk is a separate step.
