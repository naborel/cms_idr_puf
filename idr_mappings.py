"""
IDR Domain Mapping
===================
Maps provider and carrier email domains to standardized group names.

Usage:
    from idr_mappings import apply_provider_map, apply_carrier_map

    oon = apply_provider_map(oon)   # adds Provider_Group, Provider_Category
    oon = apply_carrier_map(oon)    # adds Carrier_Group, Anthem_Flag
    air = apply_provider_map(air)
    air = apply_carrier_map(air)

Provider columns expected:
    'Provider Email Domain'

Carrier columns expected:
    'Health Plan/Issuer Email Domain'

Output columns added:
    Provider_Group      -- standardized provider group name (or raw domain if unmapped)
    Provider_Category   -- PE-Backed National / Physician-Owned Group /
                           Billing/Revenue Cycle / Law Firm /
                           Hospital System / Specialty Group / Unknown
    Carrier_Group       -- standardized carrier name (or raw domain if unmapped)
    Anthem_Flag         -- 'Anthem' if domain matches any Anthem pattern, else 'Other'

Category definitions:
    PE-Backed National     -- national physician staffing/management groups backed by private equity
    Physician-Owned Group  -- large national groups that are physician-owned, no PE
    Billing/Revenue Cycle  -- RCM, billing, coding, or IDR filing companies (not direct providers)
    Law Firm               -- law firms filing IDR disputes on behalf of providers
    Hospital System        -- health system entities
    Specialty Group        -- clinical specialty practices (anesthesia, radiology, neuromonitoring)
    Unknown                -- unmapped domain (raw domain value used as fallback)

Research notes on categorization decisions:
    F&A Management    : RCM firm serving freestanding ERs, moved from PE-Backed to Billing/RCM
    AGS Health        : RCM company acquired by Blackstone Aug 2025, function is RCM not clinical
    Vituity           : 100% physician-owned democratic partnership, no outside investors or PE
    Radix Health      : IDR optimization software/services, not a clinical provider
    Ventra Health     : RCM for hospital-based physicians (merger of Abeo, DuvaSawko, Gottlieb)
    Altus Health      : 27 freestanding ERs in TX, PE-backed, moved from Billing/RCM to PE-Backed
    OrthoMed Staffing : Anesthesia management group with 262 providers across 8 states
    summit-az.com     : Removed -- could not verify which IDR-filing entity this maps to
    US Revenue Cycle  : Name is self-evident, moved from Specialty Group to Billing/RCM
"""

import pandas as pd
import numpy as np
import re


# ── Provider domain map ───────────────────────────────────────────────────────

DOMAIN_MAP = {
    # PE-Backed National
    # Large, PE-backed or PE-originated national physician staffing/management groups
    "halomd.com":               ("HaloMD",                          "PE-Backed National"),
    "teamhealth.com":           ("TeamHealth",                      "PE-Backed National"),
    "envisionhealth.com":       ("Envision Healthcare",             "PE-Backed National"),
    "scp-health.com":           ("SCP Health",                      "PE-Backed National"),
    "scphealth.com":            ("SCP Health",                      "PE-Backed National"),
    "totalcare.us":             ("TotalCare",  "PE-Backed National"),
    "usap.com":                 ("US Anesthesia Partners",          "PE-Backed National"),
    "usacs.com":                ("US Acute Care Solutions",         "PE-Backed National"),
    "apollomd.com":             ("Apollo MD",                       "PE-Backed National"),
    "soundphysicians.com":      ("Sound Physicians",                "PE-Backed National"),
    "altushealthsystem.com":    ("Altus Community Healthcare",      "PE-Backed National"),  # 27 freestanding ERs in TX, PE-backed at exit
    # Physician-Owned Group
    # National/large groups that are physician-owned, not PE-backed
    "vituity.com":              ("Vituity",                         "Physician-Owned Group"),  # 100% physician-owned democratic partnership, no outside investors
    # Billing / Revenue Cycle
    # Companies whose primary function is RCM, billing, coding, or IDR filing on behalf of providers
    "fam-llc.com":              ("F&A Management",                  "Billing/Revenue Cycle"),  # RCM firm serving freestanding ERs in TX
    "agshealth.com":            ("AGS Health",                      "Billing/Revenue Cycle"),  # RCM company (Blackstone-acquired Aug 2025)
    "ventrahealth.com":         ("Ventra Health",                   "Billing/Revenue Cycle"),  # RCM for hospital-based physicians (merger of Abeo, DuvaSawko, Gottlieb)
    "radixhealth.io":           ("Radix Health",                    "Billing/Revenue Cycle"),  # IDR optimization software/services, not a clinical provider
    "saparm.com":               ("Singleton Associates",            "Billing/Revenue Cycle"),
    "roundtmc.com":             ("Roundtable Medical Consultants",  "Billing/Revenue Cycle"),
    "logixhealth.com":          ("LogixHealth",                     "Billing/Revenue Cycle"),
    "r1rcm.com":                ("R1 RCM",                          "Billing/Revenue Cycle"),
    "zotecpartners.com":        ("Zotec Partners",                  "Billing/Revenue Cycle"),
    "gryphonhc.com":            ("Gryphon Healthcare",              "Billing/Revenue Cycle"),
    "qmacsmso.com":             ("QMACS MSO",                       "Billing/Revenue Cycle"),
    "mdcapitaladvisors.com":    ("MD Capital Advisors",             "Billing/Revenue Cycle"),
    "nosurprisebill.com":       ("NoSurpriseBill.com",              "Billing/Revenue Cycle"),
    "alldatahealth.com":        ("AllData Health",                  "Billing/Revenue Cycle"),
    "rightmedicalbilling.com":  ("Right Medical Billing",           "Billing/Revenue Cycle"),
    "erevenuebilling.com":      ("eRevenue / Exceptional Health Care","Billing/Revenue Cycle"),
    "usrcm.net":                ("US Revenue Cycle Mgmt",           "Billing/Revenue Cycle"),
    # Law Firms
    "callagylaw.com":           ("Callagy Law",                     "Law Firm"),
    "callagyrecovery.com":      ("Callagy Law",                     "Law Firm"),
    "gottliebandgreenspan.com": ("Gottlieb & Greenspan",            "Law Firm"),
    "halkovichlaw.com":         ("Halkovich Law",                   "Law Firm"),
    "afslaw.com":               ("AFS Law",                         "Law Firm"),
    "glynnlegal.com":           ("Glynn Legal",                     "Law Firm"),
    # Hospital Systems
    "primehealthcare.com":      ("Prime Healthcare",                "Hospital System"),
    "bmhcc.org":                ("Baptist Memorial Health",         "Hospital System"),
    "hcahealthcare.com":        ("HCA Healthcare",                  "Hospital System"),
    "commonspirit.org":         ("CommonSpirit Health",             "Hospital System"),
    "adventhealth.com":         ("AdventHealth",                    "Hospital System"),
    "wellstar.org":             ("WellStar Health",                 "Hospital System"),
    "tenethealth.com":          ("Tenet Healthcare",                "Hospital System"),
    "saintfrancis.com":         ("Saint Francis Health",            "Hospital System"),
    # Specialty Groups
    # Clinical specialty practices (anesthesia, radiology, neuromonitoring, etc.)
    "sonoranrm.com":            ("Sonoran Radiology",               "Specialty Group"),
    "mbbrm.com":                ("Mori Bean & Brooks",              "Specialty Group"),
    "empireradrm.com":          ("Empire State Radiology",          "Specialty Group"),
    "radpmg.com":               ("Houston Radiology Associates",    "Specialty Group"),
    "iairm.com":                ("Imaging Associates of Indiana",   "Specialty Group"),
    "specialtycare.net":        ("SpecialtyCare",                   "Specialty Group"),
    "orthomedstaffing.com":     ("OrthoMed Anesthesia",             "Specialty Group"),  # anesthesia management, 262 providers across 8 states
    "nmaiom.com":               ("NMA Intraoperative Monitoring",   "Specialty Group"),
    "unitedionm.com":           ("United IONM",                     "Specialty Group"),
    "pediatrix.com":            ("Pediatrix Medical Group",         "Specialty Group"),
    "anesthesiadynamics.com":   ("Anesthesia Dynamics",             "Specialty Group"),
}

# Lookup series (built once at import time for performance)
_DOMAIN_MAP_NAMES = {k: v[0] for k, v in DOMAIN_MAP.items()}
_DOMAIN_MAP_CATS  = {k: v[1] for k, v in DOMAIN_MAP.items()}


# ── Carrier domain map ────────────────────────────────────────────────────────

CARRIER_MAP = {
    "uhc.com":              "UnitedHealthcare",
    "unitedhealthcare.com": "UnitedHealthcare",
    "umr.com":              "UnitedHealthcare",
    "clearhs.com":          "ClearHealth Strategies",
    "clearhealthcloud.com": "ClearHealth Strategies",
    "aetna.com":            "Aetna",
    "aetnahealth.com":      "Aetna",
    "anthem.com":           "Anthem",
    "elevance.com":         "Anthem",
    "bcbstx.com":           "BCBS Texas",
    "hcsc.net":             "BCBS Texas",
    "cigna.com":            "Cigna",
    "evernorth.com":        "Cigna",
    "multiplan.com":        "MultiPlan/Claritev",
    "claritev.com":         "MultiPlan/Claritev",
    "bcbsfl.com":           "Florida Blue",
    "floridablue.com":      "Florida Blue",
    "bcbsil.com":           "BCBS Illinois",
    "bcbst.com":            "BCBS Tennessee",
    "bcbsaz.com":           "BCBS Arizona",
    "azblue.com":           "BCBS Arizona",
    "humana.com":           "Humana",
    "zelis.com":            "Zelis",
    "centene.com":          "Centene",
    "highmark.com":         "Highmark",
    "horizonblue.com":      "Horizon BCBS NJ",
    "bcbsnc.com":           "BCBS NC",
    "bcbssc.com":           "BCBS SC",
    "premera.com":          "Premera",
    "geha.com":             "GEHA",
    "ibx.com":              "Independence Blue Cross",
    "lablue.com":           "BCBS Louisiana",
    "bcbsm.com":            "BCBS Michigan",
    "carefirst.com":        "CareFirst BCBS",
    "bcbsok.com":           "BCBS Oklahoma",
    "bcbsks.com":           "BCBS Kansas",
    "kaiserpermanente.org": "Kaiser Permanente",
    "bcbsmn.com":           "BCBS Minnesota",
    "bcbswny.com":          "BCBS Western NY",
    "excellusbcbs.com":     "Excellus BCBS",
    "medmutual.com":        "Medical Mutual",
    "bcbs.com":             "BCBS (other)",
}


# ── Anthem regex patterns ─────────────────────────────────────────────────────
# Applied after the direct CARRIER_MAP lookup to catch Anthem-affiliated domains
# that may not be in the map (typos, subsidiaries, regional brands, TPAs)

ANTHEM_PATTERNS = [
    # Core Anthem / Elevance
    r'anthem',
    r'elevance',
    # Subsidiaries / brands
    r'amerigroup',
    r'carelon',
    r'caremore',
    r'unicare',
    r'wellpoint',
    r'healthkeepers',
    r'empireblue',
    # BCBS entities owned by Anthem
    r'bcbsga',
    # Affiliated / TPA
    r'ameriben',
]

_ANTHEM_REGEX = '|'.join(ANTHEM_PATTERNS)


# ── Mapping functions ─────────────────────────────────────────────────────────

def apply_provider_map(df, domain_col='Provider Email Domain'):
    """
    Add Provider_Group and Provider_Category columns based on email domain.
    Unmapped domains retain the raw domain value in Provider_Group
    and 'Unknown' in Provider_Category.
    """
    domain_clean = (
        df[domain_col]
        .astype(str)
        .str.lower()
        .str.strip()
    )

    df['Provider_Group']    = domain_clean.map(_DOMAIN_MAP_NAMES).fillna(domain_clean)
    df['Provider_Category'] = domain_clean.map(_DOMAIN_MAP_CATS).fillna('Unknown')

    return df


def apply_carrier_map(df, domain_col='Health Plan/Issuer Email Domain'):
    """
    Add Carrier_Group and Anthem_Flag columns based on email domain.

    Carrier_Group: direct lookup from CARRIER_MAP; unmapped domains retain
                   the raw domain value.
    Anthem_Flag:   'Anthem' if domain matches any ANTHEM_PATTERNS regex,
                   else 'Other'. Applied independently of Carrier_Group so
                   it catches Anthem-affiliated domains not in CARRIER_MAP.
    """
    domain_clean = (
        df[domain_col]
        .astype(str)
        .str.lower()
        .str.strip()
    )

    # Direct carrier lookup
    df['Carrier_Group'] = domain_clean.map(CARRIER_MAP).fillna(domain_clean)

    # Anthem flag via regex (catches subsidiaries, typos, regional brands)
    df['Anthem_Flag'] = np.where(
        domain_clean.str.contains(_ANTHEM_REGEX, regex=True, na=False),
        'Anthem',
        'Other'
    )

    return df


def apply_all_maps(df,
                   provider_col='Provider Email Domain',
                   carrier_col='Health Plan/Issuer Email Domain'):
    """Convenience function — apply both maps in one call."""
    df = apply_provider_map(df, domain_col=provider_col)
    df = apply_carrier_map(df, domain_col=carrier_col)
    return df


# ── Outcome bucket ────────────────────────────────────────────────────────────

def add_outcome_bucket(df,
                       outcome_col='Payment Determination Outcome',
                       default_col='Default Decision'):
    """
    Add Outcome_Bucket column with four mutually exclusive categories:
        Contested Provider Win
        Contested Plan Win
        Default Provider Win
        Default Plan Win
        Other / Split

    Requires both 'Payment Determination Outcome' and 'Default Decision' columns.
    """
    is_default  = df[default_col] == 'Yes'
    is_prov_win = df[outcome_col].str.contains('Provider', na=False)
    is_plan_win = df[outcome_col].str.contains('Plan|Issuer', na=False)

    conditions = [
        (~is_default) & is_prov_win,
        (~is_default) & is_plan_win,
        is_default    & is_prov_win,
        is_default    & is_plan_win,
    ]
    choices = [
        'Contested Provider Win',
        'Contested Plan Win',
        'Default Provider Win',
        'Default Plan Win',
    ]

    import numpy as np
    df['Outcome_Bucket'] = np.select(conditions, choices, default='Other / Split')

    return df
