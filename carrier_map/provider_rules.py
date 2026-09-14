# -*- coding: utf-8 -*-
"""
Provider-side normalisation.

The provider side is NOT symmetrical with the carrier side, and the difference matters.

A carrier's identity is a small closed set -- 127 groups cover 99% of the file. Providers are
not: 19,396 distinct group names and 37,605 facility names are mostly genuinely different
practices, and collapsing them would destroy real information.

What IS a small closed set is the FILER -- the entity whose email domain appears, which is
usually a revenue-cycle vendor, an IDR specialist or a law firm rather than the practice
itself. halomd.com files under 725 distinct NPIs; mdcapitaladvisors.com under 1,215;
gottliebandgreenspan.com under 639. Those are not provider groups, they are IDR machines, and
they are the thing worth naming: they explain who is generating dispute volume.

So: filer_group + filer_type from the domain, and the practice left as-is (NPI + group name)
rather than forced into buckets it does not have.
"""
V="RCM / billing vendor"; I="IDR specialist"; L="Law firm"
G="Physician group"; R="Radiology group"; A="Anesthesia group"
N="Neuromonitoring (IONM)"; H="Hospital / health system"; E="Emergency dept operator"

FILER = {
 # ---- IDR specialists and revenue-cycle vendors: file for many unrelated practices ----
 "halomd.com":("HaloMD",I), "nosurprisebill.com":("No Surprise Bill",I),
 "idrnsa.com":("IDR NSA",I), "fam-llc.com":("F&A Management",V),
 "agshealth.com":("AGS Health",V), "radixhealth.io":("Radix Health",V),
 "mdcapitaladvisors.com":("MD Capital Advisors",V), "qmacsmso.com":("QMACS MSO",V),
 "erevenuebilling.com":("eRevenue",V), "zotecpartners.com":("Zotec Partners",V),
 "ventrahealth.com":("Ventra Health",V), "r1rcm.com":("R1 RCM",V),
 "logixhealth.com":("LogixHealth",V), "rightmedicalbilling.com":("Right Medical Billing",V),
 "aimbillingsolutions.com":("AIM Billing Solutions",V), "gryphonhc.com":("Gryphon Healthcare",V),
 "alldatahealth.com":("AllData Health",V),
 "omsmedbilling.com":("OrthoMed Staffing",A),  # same practice as orthomedstaffing.com
 "preferredbillingaz.com":("Preferred Billing AZ",V), "heightsrcm.com":("Heights RCM",V),
 "ftpbilling.com":("FTP Billing",V), "simplexmed.com":("Simplex Med",V),
 "collaborativeimaging.com":("Collaborative Imaging",R), "medhealthfinancial.com":("MedHealth Financial",V),
 "islandprofessionalbilling.com":("Island Professional Billing",V),
 "premierchoicebill.com":("Premier Choice Billing",V), "usrcm.net":("US RCM",V),
 "macservicesllc.com":("MAC Services",V), "karisbilling.us":("Karis Billing",V),
 "expresserbilling.com":("Express ER Billing",V), "mlsmedbill.com":("MLS Medical Billing",V),
 "prevailrcm.com":("Prevail RCM",V), "integrityrcmcorp.com":("Integrity RCM",V),
 "nsabilling.com":("NSA Billing",V), "sbsbilling.com":("SBS Billing",V),
 "prestigemedicalbill.com":("Prestige Medical Billing",V), "elitebillingllc.com":("East Coast Advanced Plastic Surgery",G),
 "wincherbilling.com":("Sun City Emergency Room",E), "medbill-assoc.com":("MedBill Associates",V),
 "njbrainspinebilling.com":("NJ Brain & Spine Billing",V),
 "vipmedicalmanagement.com":("VIP Medical Management",V), "onet-systems.com":("ONET Systems",V),
 "syntechhealth.com":("Sun City Emergency Room",E), "healthworksbetter.com":("HealthWorks",V),
 "civie.com":("Collaborative Imaging",R), "uickc.com":("United Imaging Consultants",V),
 "jphealth.net":("JP Health",V), "swiftstar.com":("Swift Star",V),
 # ---- law firms ----
 "callagylaw.com":("Callagy Law",L), "callagyrecovery.com":("Callagy Law",L),
 "gottliebandgreenspan.com":("Gottlieb & Greenspan",L), "halkovichlaw.com":("Halkovich Law",L),
 "afslaw.com":("ArentFox Schiff",L), "wolfepincavage.com":("Wolfe Pincavage",L),
 "glynnlegal.com":("Glynn Legal",L), "khcfirm.com":("KHC Firm",L),
 # ---- physician staffing / practice groups filing for themselves ----
 "teamhealth.com":("TeamHealth",G), "envisionhealth.com":("Envision Healthcare",G),
 "scp-health.com":("SCP Health",G), "scphealth.com":("SCP Health",G),
 "usacs.com":("US Acute Care Solutions",G), "apollomd.com":("ApolloMD",G),
 "vituity.com":("Vituity",G), "soundphysicians.com":("Sound Physicians",G),
 "pediatrix.com":("Pediatrix Medical Group",G), "usap.com":("US Anesthesia Partners",A),
 # audited against the service-code mix: 86.2% CPT 95938/95940 -> IONM, not a physician group
 "specialtycare.net":("SpecialtyCare",N),
 # 88.4% CPT 008xx -> anesthesia
 "orthomedstaffing.com":("OrthoMed Staffing",A),
 "roundtmc.com":("Round Table Physicians",G), "em-specialists.org":("EM Specialists",G),
 "ecp.net":("Illinois Emergency Medicine Specialists",G),
 "forthesurgeons.com":("East Coast Advanced Plastic Surgery",G),
 "assa-nj.com":("Atlantic Shore Surgical",G), "brownphysicians.org":("Brown Emergency Medicine",G),
 "longislandbrainandspine.com":("Long Island Brain & Spine",G),
 # ---- freestanding ER operators ----
 "totalcare.us":("TotalCare ER",E), "altushealthsystem.com":("Altus Community Healthcare",E),
 "neighborshealth.com":("Neighbors Health",E), "complete.care":("Complete Care",E),
 "memorialvillageer.com":("Memorial Village ER",E), "americaser.com":("America's ER",E),
 "bellaireer.com":("Bellaire ER",E), "victoriaemergency.com":("Victoria Emergency Partners",E),
 "clearchoiceer.com":("Clear Choice ER",E), "totalpointcare.com":("Total Point ER",E),
 "ascentemc.com":("Ascent Emergency",E), "legacyhealthllc.com":("Legacy ER",E),
 "ihcsaz.com":("Fountain Hills Medical Center",E),
 # ---- radiology ----
 "saparm.com":("Singleton Associates",R), "sonoranrm.com":("Sonoran Radiology",R),
 "mbbrm.com":("Mori, Bean & Brooks",R), "radpmg.com":("Houston Radiology Associated",R),
 "empireradrm.com":("Empire State Radiology",R), "iairm.com":("Imaging Associates of Indiana",R),
 "radalliancerm.com":("Radiology Alliance",R), "redrockrad.com":("Radiology Specialists",R),
 "smirm.com":("Specialists in Medical Imaging",R), "accessradrm.com":("Radiology Associates of Southwest",R),
 "racrm.com":("Radiology Associates of Canton",R), "midstateradrm.com":("Murfreesboro Radiology",R),
 # ---- anesthesia ----
 "anesthesiadynamics.com":("Anesthesia Dynamics",A), "summit-az.com":("Summit Anesthesia Partners",A),
 "provanesthesiology.com":("Providence Anesthesiology",A), "saguaroanesthesia.com":("Saguaro Anesthesia",A),
 "bergenanesthesiagroup.com":("Bergen Anesthesia",A), "magmemphis.com":("Medical Anesthesia Group",A),
 "mlanesthesia.com":("ML Anesthesia",A),
 # ---- intraoperative neuromonitoring: a distinct and fast-growing IDR category ----
 "nmaiom.com":("NMA IONM",N), "unitedionm.com":("United IONM",N), "epiomneuro.com":("EPIOM Neuro",N),
 "usneuro.net":("Advanced Neuro Solutions",N), "neurologiciom.com":("Neurologic IOM",N),
 "apexionm.com":("Apex IONM",N), "ansmonitoring.com":("Advanced Neuro Solutions",N),
 "pelmed.com":("Hudson Regional billing",V), "christushealth.org":("CHRISTUS Health",H),
 "neuroendomke.com":("Spine & Brain Institute of Wisconsin",N),
 # ---- hospitals and health systems ----
 "bmhcc.org":("Baptist Memorial Health",H), "primehealthcare.com":("Prime Healthcare",H),
 "hcahealthcare.com":("HCA Healthcare",H), "commonspirit.org":("CommonSpirit Health",H),
 "adventhealth.com":("AdventHealth",H), "wellstar.org":("Wellstar",H),
 "tenethealth.com":("Tenet Healthcare",H), "saintfrancis.com":("Saint Francis Health",H),
 "shands.ufl.edu":("UF Health Shands",H), "gbmc.org":("Greater Baltimore Medical Center",H),
 "texashealth.org":("Texas Health Resources",H), "stormontvail.org":("Stormont Vail Health",H),
 "natera.com":("Natera",G),
}
# free-mail domains are individual practitioners filing on their own behalf
PERSONAL = {"gmail.com","aol.com","yahoo.com","outlook.com","hotmail.com","icloud.com"}
