# -*- coding: utf-8 -*-
"""
Carrier normalisation for the CMS IDR public use files.

TWO FIELDS, because one is not enough:

  submitter_group  -- who actually handled the dispute, from the email domain. A repricing
                      vendor (MultiPlan/Claritev, Zelis, ClearHealth) files under its own
                      domain on behalf of many payers.
  carrier_group    -- the payer whose money is at stake, from the plan NAME, falling back to
                      the domain. This is the field a client should filter on.

Neither field alone is trustworthy, and the evidence is in the data:
  * multiplan.com  is 64% Cigna but also carries Kaiser, Arkansas BCBS and Horizon.
  * clearhs.com    is 78% UMR *and* Meritain -- UnitedHealthcare and Aetna under one domain.
  * bcbsil.com     is 55% Blue Cross plans of TEXAS and OKLAHOMA, not Illinois (HCSC runs
                   all five plans off shared infrastructure).
  * bcbstx.com     IS genuinely BCBS Texas -- every name variant resolves to Texas.

Rules are ordered; first match wins. Order is load-bearing: "MULTIPLAN ON BEHALF OF CIGNA"
must hit the Cigna rule, and "BCBS FEDERAL EMPLOYEE PROGRAM" must not be captured by a
generic BCBS rule.
"""
import re

def norm(s):
    if s is None: return ""
    s = str(s).upper()
    s = s.replace("&", " AND ")
    s = re.sub(r"REDACTED", " ", s)
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\b(INC|LLC|LLP|LP|CORP|CORPORATION|COMPANY|CO|THE|GROUP|PLAN|PLANS|"
               r"HEALTHCARE|HEALTH CARE|INSURANCE|ASSURANCE|LIFE|OF|AND)\b", " ", s)
    return re.sub(r"\s+", " ", s).strip()

# (pattern, carrier_group, carrier_parent, carrier_type)
# matched against the RAW uppercased name (not norm()) so word boundaries survive
C = "Carrier"; B = "Blues licensee"; T = "TPA / ASO"; V = "Repricing vendor"
P = "Provider-sponsored"; U = "Union / Taft-Hartley"; G = "Government"

# (plan, parent, STATE-WORD, ABBR). Patterns are generated so that every spelling a filer
# might use resolves: "BCBSTX", "BCBS TX", "BCBS OF TEXAS", "BLUE CROSS AND BLUE SHIELD OF
# TEXAS", "BLUE SHIELD OF TEXAS". Hand-writing these was the source of most first-pass misses
# -- "BCBS OF TENNESSEE" failed a rule that required the words BLUE CROSS.
BLUES = [
 ("BCBS Texas","HCSC","TEXAS","TX"),          ("BCBS Oklahoma","HCSC","OKLAHOMA","OK"),
 ("BCBS New Mexico","HCSC","NEW MEXICO","NM"),("BCBS Illinois","HCSC","ILLINOIS","IL"),
 ("BCBS Montana","HCSC","MONTANA","MT"),      ("Florida Blue","GuideWell","FLORIDA","FL"),
 ("BCBS Tennessee","Independent","TENNESSEE","TN"),
 ("BCBS Arizona","Independent","ARIZONA","AZ"),
 ("BCBS North Carolina","Independent","NORTH CAROLINA","NC"),
 ("BCBS Louisiana","Elevance","LOUISIANA","LA"),
 ("BCBS Kansas City","Independent","KANSAS CITY",None),
 ("BCBS Kansas","Independent","KANSAS","KS"), ("BCBS Michigan","Independent","MICHIGAN","MI"),
 ("BCBS Minnesota","Independent","MINNESOTA","MN"),
 ("BCBS Alabama","Independent","ALABAMA","AL"),
 ("BCBS Mississippi","Independent","MISSISSIPPI","MS"),
 ("BCBS South Carolina","Independent","SOUTH CAROLINA","SC"),
 ("BCBS Rhode Island","Independent","RHODE ISLAND","RI"),
 ("BCBS Massachusetts","Independent","MASSACHUSETTS","MA"),
 ("BCBS Nebraska","Independent","NEBRASKA","NE"),
 ("Blue Cross of Idaho","Independent","IDAHO","ID"),
 ("Arkansas BCBS","Independent","ARKANSAS","AR"),
 ("BCBS Vermont","Independent","VERMONT","VT"),
 ("BCBS Wyoming","Independent","WYOMING","WY"),
 ("BCBS North Dakota","Independent","NORTH DAKOTA","ND"),
 ("BCBS South Dakota","Independent","SOUTH DAKOTA","SD"),
]
def _blues_rules():
    out=[]
    for plan,parent,state,abbr in BLUES:
        alts=[r"BLUE ?CROSS.{0,40}"+state, r"BLUE ?SHIELD.{0,40}"+state,
              r"\bBCBS\b.{0,12}"+state,
              state+r".{0,20}BLUE ?CROSS", state+r".{0,20}BLUE ?SHIELD"]
        if abbr:
            alts += [r"\bBCBS"+abbr+r"\b", r"\bBCBS\b.{0,12}\b"+abbr+r"\b",
                     r"BLUE ?CROSS.{0,25}\b"+abbr+r"\b"]
        out.append(("|".join(alts), plan, parent, "Blues licensee"))
    return out
_BLUES_RULES=_blues_rules()

CARRIER_RULES = [
 # ---- Blues plans, generated from a state table (see BLUES below) ----
 *_BLUES_RULES,
 # ---- named Blues plans (no state word in the brand) ----
 (r"\bHORIZON\b",                               "Horizon BCBS NJ","Independent",B),
 (r"\bCAREFIRST\b",                             "CareFirst","Independent",B),
 (r"\bHIGHMARK\b",                              "Highmark","Highmark",B),
 (r"\bPREMERA\b",                               "Premera Blue Cross","Independent",B),
 (r"\bREGENCE\b",                               "Regence","Cambia",B),
 (r"\bEXCELLUS\b",                              "Excellus BCBS","Lifetime",B),
 (r"CAPITAL BLUE|\bCAPBLUECROSS\b|BCBS CAPITAL","Capital BlueCross","Independent",B),
 (r"INDEPENDENCE (BLUE|BC)\b|\bIBX\b",          "Independence Blue Cross","Independence",B),
 (r"BLUE SHIELD.{0,20}\bCA\b|BLUESHIELDCA|BLUE SHIELD PPO|BLUE SHIELD.{0,20}CALIFORNIA",
                                                 "Blue Shield of California","Independent",B),
 (r"\bWELLMARK\b",                              "Wellmark BCBS","Independent",B),
 (r"FEDERAL EMPLOYEE PROGRAM|\bFEP\b|\bBLUECARD\b|BLUE CARD",
                                                 "BCBS Federal Employee Program","BCBSA",B),
 (r"\bANTHEM\b|\bEMPIRE ?BLUE\b|\bWELLPOINT\b|\bELEVANCE\b|\bAMERIGROUP\b",
                                                                 "Anthem / Elevance","Elevance",C),
 (r"\bEMPIRE\b",                                                 "Anthem / Elevance","Elevance",C),
 (r"FEDERAL EMPLOYEE PROGRAM|\bFEP\b",                           "BCBS Federal Employee Program","BCBSA",B),
 # ---- national carriers ----
 (r"\bUMR\b|UNITED MEDICAL RESOURCES|\bUHC\b|UNITED ?HEALTH ?CARE|UNITEDHEALTHCARE|"
  r"\bOPTUM\b|GOLDEN RULE|\bOXFORD\b|\bSUREST\b|ALL ?SAVERS|\bUHP\b|UNITED HEALTHCARE",
                                                                 "UnitedHealthcare","UnitedHealth Group",C),
 (r"\bMERITAIN\b|\bMERITIAN\b|\bAETNA\b|\bCOFINITY\b|\bALLIED BENEFIT SYSTEMS\b",
                                                                 "Aetna","CVS Health",C),
 (r"\bCIGNA\b|\bEVERNORTH\b|GREAT ?WEST",                        "Cigna","Cigna",C),
 (r"\bCENTENE\b|\bAMBETTER\b|FIDELIS|HEALTH ?NET|\bWELLCARE\b|SUPERIOR HEALTHPLAN",
                                                                 "Centene","Centene",C),
 (r"\bHUMANA\b",                                                 "Humana","Humana",C),
 (r"\bKAISER\b|\bKP\.ORG\b|KAISER PERMANENTE|KAISER FOUNDATION", "Kaiser Permanente","Kaiser",C),
 (r"\bMOLINA\b",                                                 "Molina Healthcare","Molina",C),
 (r"\bOSCAR\b",                                                  "Oscar Health","Oscar",C),
 (r"\bGEHA\b",                                                   "GEHA","GEHA",C),
 (r"EMBLEM ?HEALTH",                                             "EmblemHealth","Emblem",C),
 (r"HARVARD PILGRIM|POINT32|TUFTS HEALTH",                       "Point32Health","Point32",C),
 (r"\bMEDICA\b",                                                 "Medica","Medica",C),
 (r"MEDICAL MUTUAL|MEDMUTUAL",                                   "Medical Mutual","Independent",C),
 (r"\bCARESOURCE\b",                                             "CareSource","CareSource",C),
 (r"PRIORITY HEALTH",                                            "Priority Health","Corewell",C),
 (r"\bMODA\b|ODS HEALTH",                                        "Moda Health","Moda",C),
 (r"HEALTHPARTNERS|HEALTH PARTNERS",                             "HealthPartners","HealthPartners",C),
 (r"PACIFICSOURCE",                                              "PacificSource","PacificSource",C),
 (r"INDEPENDENT HEALTH",                                         "Independent Health","Independent",C),
 (r"\bMVP\b",                                                    "MVP Health Care","MVP",C),
 (r"\bCDPHP\b|CAPITAL DISTRICT",                                 "CDPHP","CDPHP",C),
 (r"\bTRUSTMARK\b",                                              "Trustmark","Trustmark",C),
 (r"\bWELLFLEET\b",                                              "Wellfleet","Wellfleet",C),
 (r"\bCURATIVE\b",                                               "Curative","Curative",C),
 (r"\bCENTIVO\b",                                                "Centivo","Centivo",C),
 (r"\bGRAVIE\b",                                                 "Gravie","Gravie",C),
 (r"\bSANA\b",                                                   "Sana Benefits","Sana",C),
 (r"BRIGHT HEALTH",                                              "Bright Health","Bright",C),
 (r"FRIDAY HEALTH",                                              "Friday Health Plans","Friday",C),
 (r"NIPPON LIFE",                                                "Nippon Life Benefits","Nippon",C),
 (r"PHILADELPHIA AMERICAN|NEW ERA LIFE",                         "New Era Life","New Era",C),
 (r"FREEDOM LIFE|US HEALTH ?GROUP|MANHATTAN LIFE",               "USHEALTH / Freedom Life","USHEALTH",C),
 # ---- provider-sponsored plans ----
 (r"BAYLOR SCOTT|\bBSW\b",                                       "Baylor Scott & White","BSW",P),
 (r"\bUPMC\b",                                                   "UPMC Health Plan","UPMC",P),
 (r"\bSENTARA\b|OPTIMA HEALTH",                                  "Sentara Health Plans","Sentara",P),
 (r"\bASCENSION\b",                                              "Ascension Personalized Care","Ascension",P),
 (r"\bCHRISTUS\b",                                               "CHRISTUS Health Plan","CHRISTUS",P),
 (r"\bAVERA\b",                                                  "Avera Health Plans","Avera",P),
 (r"PRESBYTERIAN",                                               "Presbyterian Health Plan","Presbyterian",P),
 (r"SELECT ?HEALTH|INTERMOUNTAIN",                               "SelectHealth","Intermountain",P),
 (r"\bGEISINGER\b",                                              "Geisinger Health Plan","Geisinger",P),
 (r"JOHNS HOPKINS",                                              "Johns Hopkins Health Plans","JHU",P),
 (r"\bSHARP\b",                                                  "Sharp Health Plan","Sharp",P),
 (r"HEALTH ALLIANCE",                                            "Health Alliance","Carle",P),
 (r"\bAULTCARE\b",                                               "AultCare","Aultman",P),
 (r"\bVIVA HEALTH\b",                                            "VIVA Health","UAB",P),
 (r"CAPITAL HEALTH PLAN",                                        "Capital Health Plan","Independent",P),
 (r"HEALTH FIRST|HEALTHFIRST",                                   "Health First","Health First",P),
 (r"\bHAP\b|HEALTH ALLIANCE PLAN",                               "HAP","Henry Ford",P),
 (r"COMMUNITY HEALTH CHOICE",                                    "Community Health Choice","Independent",P),
 (r"KELSEY ?SEYBOLD",                                            "Kelsey-Seybold","Kelsey",P),
 # ---- spelling variants seen in the file; filers type these by hand ----
 (r"MASSACHUSETT",                               "BCBS Massachusetts","Independent",B),
 (r"TENNESE|TENNESSE(?!E)",                      "BCBS Tennessee","Independent",B),
 (r"BLUE CROSS.{0,20}NEW JERSEY|\bBCBSNJ\b",     "Horizon BCBS NJ","Independent",B),
 (r"\bTUFTS\b",                                 "Point32Health","Point32",C),
 (r"CARE ?SOURCE",                               "CareSource","CareSource",C),
 # ---- additional TPAs and regional plans ----
 (r"BOON.?CHAPMAN",                              "Boon-Chapman","Boon-Chapman",T),
 (r"\bAUXIANT\b",                               "Auxiant","Auxiant",T),
 (r"\bAITHER\b",                                "Aither Health","Aither",T),
 (r"ASSURED BENEFIT",                            "Assured Benefits Administrators","ABA",T),
 (r"\bHEALTHEZ\b|HEALTH ?EZ",                    "HealthEZ","HealthEZ",T),
 (r"HEALTH OPTIONS",                             "Health Options","Independent",C),
 (r"NETWORK HEALTH",                             "Network Health","Network Health",C),
 (r"\bTHE HEALTH PLAN\b|HEALTHPLAN ORG",         "The Health Plan","THP",C),
 (r"\bNALC\b|LETTER CARRIERS",                   "NALC Health Benefit Plan","NALC",U),
 (r"ADVENTIST",                                  "Adventist Health","Adventist",P),
 (r"\bSISCO\b|\bIMSM\b|\bBRMS\b|\bPAI\b|\bSIHO\b|\bEBA\b|LOOMIS|CONSOCIATE|"
  r"KEY BENEFIT|PINNACLE CLAIMS|JP FARLEY|J P FARLEY|SUMMIT ADMIN|MERCHANTS BENEFIT|"
  r"UNIFIED GROUP|TOTAL PLAN|CUSTOM DESIGN|GROUP BENEFIT SERVICES|AMERICAN PLAN ADMIN|"
  r"PROFESSIONAL BENEFIT ADMIN|SOUTHWEST SERVICE ADMIN|INTERNATIONAL BENEFITS ADMIN",
                                                 "Independent TPA (small)","Various",T),
 (r"GOVERNMENT EMPLOYEES HEALTH ASSOC",          "GEHA","GEHA",C),
 (r"\bEMBLEM\b|\bGHI\b",                        "EmblemHealth","Emblem",C),
 (r"90 ?DEGREE",                                 "90 Degree Benefits","90 Degree",T),
 (r"LUMINARE",                                   "Luminare Health","Trustmark",T),
 (r"LUCENT HEALTH",                              "Lucent Health","Lucent",T),
 (r"HEALTH PLANS INC",                           "Health Plans Inc","HPI",T),
 (r"INSURANCE MANAGEMENT SERVICES|\bIMS\b",      "Insurance Management Services","IMS",T),
 (r"COMMUNITY CARE\b",                           "CommunityCare OK","Independent",C),
 (r"PROVIDENCE HEALTH",                          "Providence Health Plan","Providence",P),
 (r"TEXAS CHILDREN",                             "Texas Children's Health Plan","TCH",P),
 (r"\bAMERIBEN\b",                              "AmeriBen","AmeriBen",T),
 (r"BOON ?CHAPMAN",                              "Boon-Chapman","Boon-Chapman",T),
 (r"ALLIED BENEFIT",                             "Allied Benefit Systems","Allied",T),
 (r"HEALTHSCOPE",                                "HealthScope Benefits","HealthScope",T),
 (r"HEALTHCOMP|HEALTH COMP",                     "HealthComp","HealthComp",T),
 (r"HEALTHSMART",                                "HealthSmart","HealthSmart",T),
 (r"\bMAGNACARE\b",                             "MagnaCare","Brighton",T),
 (r"ZENITH AMERICAN",                            "Zenith American","Zenith",T),
 (r"MARPAI",                                     "Marpai Health","Marpai",T),
 (r"PERSONIFY",                                  "Personify Health","Personify",T),
 (r"\bMEDCOST\b",                               "MedCost","MedCost",T),
 (r"\bQUALCHOICE\b",                            "QualChoice","QualChoice",C),
 (r"\bAMERIHEALTH\b",                           "AmeriHealth","AmeriHealth",C),
 (r"\bEMI HEALTH\b",                            "EMI Health","EMI",C),
 (r"NIPPON",                                     "Nippon Life Benefits","Nippon",C),
 # ---- unions / Taft-Hartley ----
 (r"\b1199\b|SEIU|\bUFCW\b|\b32BJ\b|UNITE HERE|TAFT HARTLEY|NATIONAL BENEFIT FUND",
                                                                 "Union / Taft-Hartley fund","Union",U),
 (r"WESTERN GROWERS",                                            "Western Growers Trust","WGAT",U),
 # ---- government ----
 (r"\bTRICARE\b|\bVA\b COMMUNITY CARE|MEDICAID|\bHSD\b|OMES|MUNICIPAL HEALTH",
                                                                 "Government / public program","Government",G),
]

# submitter (email-domain) rules -- who actually filed. Ordered; first match wins.
DOMAIN_RULES = [
 (r"^(multiplan|mutliplan|mulitplan|multipan|multiplan\.co|dataisight|claritev|idr)\.",
                                                      "MultiPlan / Claritev",V),
 (r"^(clearhs|clearhealthcloud|clearhealth)\.",       "ClearHealth Strategies",V),
 (r"^zelis\.",                                        "Zelis",V),
 (r"^(wellrithms|expionhealth|elapservices|6degreeshealth|occunet|payerscompass|"
  r"rialtic|penstock|healthgram|vitorihealth|logixhealth|greenlightcm)\.",
                                                      "Other repricing vendor",V),
 (r"^(uhc|umr|uhcsr|optum|golden|myuhc)\.",           "UnitedHealthcare",C),
 (r"^aetna\.|^meritain\.|^meritian\.",                "Aetna",C),
 (r"^cigna\.|^evernorth\.",                           "Cigna",C),
 (r"^anthem\.|^elevancehealth\.|^empireblue\.|^wellpoint\.|^amerigroup\.", "Anthem / Elevance",C),
 (r"^bcbs|^blue|^azblue\.|^lablue\.|^ibx|^carefirst\.|^highmark\.|^regence\.|^premera\.|"
  r"^excellus\.|^capbluecross\.|^nebraskablue\.|^arkbluecross\.|^bcidaho\.|^horizonblue\.",
                                                      "Blues plan",B),
 (r"^centene\.|^fideliscare\.|^healthnet\.",          "Centene",C),
 (r"^humana\.", "Humana",C), (r"^kp\.org|^kaiser",    "Kaiser Permanente",C),
 (r"^molinahealthcare\.",                             "Molina Healthcare",C),
 (r"^hioscar\.",                                      "Oscar Health",C),
]


# When the plan name is generic ("BCBS", "BLUECROSS BLUESHIELD") the domain still identifies
# the plan -- but only for domains a single plan actually owns. bcbsil.com is deliberately NOT
# here: HCSC runs Texas, Oklahoma, New Mexico, Illinois and Montana off it, and 55% of the
# generic names on that domain are Texas or Oklahoma plans, so guessing "Illinois" would put
# the wrong carrier on a filter.
DOMAIN_CARRIER = {
 "bcbstx.com":("BCBS Texas","HCSC","Blues licensee"),
 "bcbsok.com":("BCBS Oklahoma","HCSC","Blues licensee"),
 "bcbsnm.com":("BCBS New Mexico","HCSC","Blues licensee"),
 "azblue.com":("BCBS Arizona","Independent","Blues licensee"),
 "bcbsfl.com":("Florida Blue","GuideWell","Blues licensee"),
 "bcbst.com":("BCBS Tennessee","Independent","Blues licensee"),
 "bcbsnc.com":("BCBS North Carolina","Independent","Blues licensee"),
 "lablue.com":("BCBS Louisiana","Elevance","Blues licensee"),
 "bcbsla.com":("BCBS Louisiana","Elevance","Blues licensee"),
 "bcbsks.com":("BCBS Kansas","Independent","Blues licensee"),
 "bcbsm.com":("BCBS Michigan","Independent","Blues licensee"),
 "bluekc.com":("BCBS Kansas City","Independent","Blues licensee"),
 "bcbssc.com":("BCBS South Carolina","Independent","Blues licensee"),
 "bcbsri.org":("BCBS Rhode Island","Independent","Blues licensee"),
 "bcbsma.com":("BCBS Massachusetts","Independent","Blues licensee"),
 "bcbsal.org":("BCBS Alabama","Independent","Blues licensee"),
 "bcbsms.com":("BCBS Mississippi","Independent","Blues licensee"),
 "bluecrossmn.com":("BCBS Minnesota","Independent","Blues licensee"),
 "nebraskablue.com":("BCBS Nebraska","Independent","Blues licensee"),
 "bcidaho.com":("Blue Cross of Idaho","Independent","Blues licensee"),
 "arkbluecross.com":("Arkansas BCBS","Independent","Blues licensee"),
 "blueshieldca.com":("Blue Shield of California","Independent","Blues licensee"),
 "horizonblue.com":("Horizon BCBS NJ","Independent","Blues licensee"),
 "carefirst.com":("CareFirst","Independent","Blues licensee"),
 "highmark.com":("Highmark","Highmark","Blues licensee"),
 "premera.com":("Premera Blue Cross","Independent","Blues licensee"),
 "regence.com":("Regence","Cambia","Blues licensee"),
 "excellus.com":("Excellus BCBS","Lifetime","Blues licensee"),
 "capbluecross.com":("Capital BlueCross","Independent","Blues licensee"),
 "ibx.com":("Independence Blue Cross","Independence","Blues licensee"),
 "ibxtpa.com":("Independence Blue Cross","Independence","Blues licensee"),
 "empireblue.com":("Anthem / Elevance","Elevance","Carrier"),
 "elevancehealth.com":("Anthem / Elevance","Elevance","Carrier"),
 # HCSC shared infrastructure -- the plan genuinely cannot be identified from a generic name
 "bcbsil.com":("BCBS \u2014 HCSC (state not identified)","HCSC","Blues licensee"),
}

# TPAs and administrators that are wholly-owned by, or file exclusively for, a named carrier
EXTRA_NAME_RULES = [
 (r"HEALTH ADVANTAGE|HMO PARTNERS",       "Arkansas BCBS","Independent","Blues licensee"),
 (r"\bALLEGIANCE\b",                     "Cigna","Cigna","TPA / ASO"),
 (r"\bWEB ?TPA\b",                       "WebTPA","WebTPA","TPA / ASO"),
 (r"CHS IDR|CLEARHEALTH|CLEAR HEALTH",    None,None,None),   # vendor desk, payer unknowable
]
