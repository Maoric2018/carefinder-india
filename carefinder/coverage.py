"""District coverage for planners: where is well-documented care missing, and where is the need highest?

Joins three sources:
  * facility evidence (this package) -> where a service is credibly offered, with confidence,
  * India Post PIN directory          -> a centre point for every district,
  * NFHS-5 district health indicators -> how much each district needs the service.

A district counts as covered when a High-confidence facility for the service is within the service's travel scale
(the same distance scale the ranking uses). A gap means no strongly documented claim in this dataset, which is not
proof the service is absent.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import LABELS, CareFinder, confidence_label
from .geo import haversine_km, norm_city, norm_state, same_state
from .taxonomy import Service

HIGH = LABELS[0][0]
MEDIUM = LABELS[1][0]


@dataclass(frozen=True)
class Indicator:
    key: str
    prefixes: tuple[str, ...]  # NFHS-5 column name prefixes; several = average (e.g. women and men)
    label: str
    need_when: str  # "low" if a low value means more need (e.g. institutional births), else "high"


INDICATORS = {i.key: i for i in (
    Indicator("csection", ("births_delivered_by_csection_5y",), "Births delivered by C-section", "low"),
    Indicator("inst_birth", ("institutional_birth_5y",), "Births in a health facility", "low"),
    Indicator("anc4", ("mothers_who_had_at_least_4_anc_visits",), "Mothers with 4+ antenatal visits", "low"),
    Indicator("vaccinated", ("child_12_23m_fully_vaccinated_based_on_information_from_eit",),
              "Children 12-23 months fully vaccinated", "low"),
    Indicator("wasted", ("child_u5_who_are_wasted",), "Children under 5 who are wasted", "high"),
    Indicator("stunted", ("child_u5_who_are_stunted",), "Children under 5 who are stunted", "high"),
    Indicator("anaemia", ("all_w15_49_who_are_anaemic",), "Women 15-49 who are anaemic", "high"),
    Indicator("sugar", ("w15_plus_with_high_or_very_high", "m15_plus_with_high_or_very_high"),
              "Adults with high blood sugar (women and men)", "high"),
    Indicator("bp", ("w15_plus_with_high_bp", "m15_plus_with_high_bp"),
              "Adults with high blood pressure (women and men)", "high"),
    Indicator("cervical", ("women_age_30_49_years_ever_undergone_a_cervical",),
              "Women 30-49 ever screened for cervical cancer", "low"),
    Indicator("tobacco", ("m15_plus_who_use_any_kind_of_tobacco",), "Men 15+ who use tobacco", "high"),
    Indicator("insurance", ("hh_member_covered_health_insurance",), "Households with health insurance", "low"),
)}

# The NFHS-5 indicator that best signals need for each service (first = default).
SERVICE_NEED = {
    "c_section": ("csection", "inst_birth"), "maternity": ("inst_birth", "anc4"), "nicu": ("inst_birth", "anc4"),
    "ultrasound": ("anc4", "inst_birth"), "pediatrics": ("vaccinated", "wasted"), "blood_bank": ("anaemia", "inst_birth"),
    "dialysis": ("sugar", "bp"), "cardiac_surgery": ("bp", "sugar"), "cath_lab": ("bp", "sugar"),
    "eye_surgery": ("sugar", "insurance"), "oncology": ("cervical", "tobacco"), "dental": ("tobacco", "insurance"),
}
DEFAULT_NEED = ("insurance",)

# NFHS-5 uses Census-2011 names; India Post often uses newer or English ones.
DIRECTIONS = {"pashchim": "west", "paschim": "west", "purba": "east", "purbi": "east", "purab": "east",
              "uttar": "north", "dakshin": "south", "dakshina": "south", "madhya": "central"}
RENAMED = {
    "belgaum": "belagavi", "bijapur": "vijayapura", "gulbarga": "kalaburagi", "bellary": "ballari", "mysore": "mysuru",
    "shimoga": "shivamogga", "tumkur": "tumakuru", "chikmagalur": "chikkamagaluru", "bangalore": "bengaluru",
    "bangalore rural": "bengaluru rural", "gurgaon": "gurugram", "mewat": "nuh", "allahabad": "prayagraj",
    "faizabad": "ayodhya", "hoshangabad": "narmadapuram", "kabeerdham": "kabirdham", "baramula": "baramulla",
    "punch": "poonch", "badgam": "budgam", "kodarma": "koderma", "sant ravidas nagar bhadohi": "bhadohi",
    "jyotiba phule nagar": "amroha", "mahamaya nagar": "hathras", "kanshiram nagar": "kasganj",
    "y s r": "kadapa", "ysr": "kadapa", "sri potti sriramulu nellore": "nellore", "leh ladakh": "leh",
    "the dangs": "dangs", "dohad": "dahod", "panch mahals": "panchmahal", "sabar kantha": "sabarkantha",
    "banas kantha": "banaskantha", "mahesana": "mehsana", "kachchh": "kutch", "janjgir champa": "janjgir",
    "east nimar": "khandwa", "west nimar": "khargone", "marigaon": "morigaon", "ri bhoi": "ribhoi",
    "khordha": "khurda", "debagarh": "deogarh", "nabarangapur": "nabarangpur", "anugul": "angul",
    "baleshwar": "balasore", "subarnapur": "sonepur", "kendujhar": "keonjhar", "jagatsinghapur": "jagatsinghpur",
    "sahibzada ajit singh nagar": "mohali", "shahid bhagat singh nagar": "nawanshahr", "firozpur": "ferozepur",
    "barddhaman": "bardhaman", "haora": "howrah", "hugli": "hooghly", "maldah": "malda", "puruliya": "purulia",
    "darjiling": "darjeeling", "koch bihar": "cooch behar", "kancheepuram": "kanchipuram", "thoothukkudi": "tuticorin",
    "tiruvallur": "thiruvallur", "the nilgiris": "nilgiris", "viluppuram": "villupuram", "sivaganga": "sivagangai",
}


def _variants(name: str) -> list[str]:
    base = norm_city(re.sub(r"[()&]", " ", name or "")) or ""
    out = [base]
    words = base.split()
    translated = " ".join(DIRECTIONS.get(w, w) for w in words)
    out.append(translated)
    if words and words[0] in DIRECTIONS:  # "pashchim champaran" -> "champaran west"
        out.append(" ".join(words[1:] + [DIRECTIONS[words[0]]]))
    for v in list(out):
        if v in RENAMED:
            out.append(RENAMED[v])
    out.append(base.replace(" ", ""))
    return [v for i, v in enumerate(out) if v and v not in out[:i]]


def _col(df: pd.DataFrame, prefix: str) -> str | None:
    return next((c for c in df.columns if c.lower().startswith(prefix)), None)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype(str).str.replace(r"[^0-9.\-]", "", regex=True), errors="coerce")


def prepare_nfhs(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per district: district, state (normalized), and every indicator we know about (NaN if missing)."""
    dcol = _col(raw, "district") or raw.columns[0]
    scol = _col(raw, "state") or raw.columns[1]
    out = pd.DataFrame({
        "district": raw[dcol].astype(str).str.strip(),
        "state_label": raw[scol].astype(str).str.strip(),
    })
    out["state"] = [norm_state(s.replace("&", " and ")) for s in out["state_label"]]
    for ind in INDICATORS.values():
        cols = [c for c in (_col(raw, p) for p in ind.prefixes) if c]
        out[ind.key] = pd.concat([_num(raw[c]) for c in cols], axis=1).mean(axis=1) if cols else np.nan
    return out


def place_districts(nfhs: pd.DataFrame, finder: CareFinder) -> pd.DataFrame:
    """Adds lat/lon and how each district was placed: India Post district centre, a fuzzy name match, or a city."""
    pin_dir = finder.pin_dir
    gaz = finder.gazetteer
    lats, lons, how = [], [], []
    for name, state in zip(nfhs["district"], nfhs["state"]):
        found = None
        variants = _variants(name)
        if pin_dir is not None:
            pool = {d: p for d, places in pin_dir.districts.items() for p in places if same_state(p.state, state)}
            for v in variants:
                if v in pool:
                    found = (pool[v], "India Post district")
                    break
            if found is None and pool:
                best = max(((difflib.SequenceMatcher(None, v, d).ratio(), d) for v in variants for d in pool),
                           default=(0, None))
                if best[0] >= 0.82:
                    found = (pool[best[1]], f"India Post district (≈ {best[1].title()})")
        if found is None:
            for v in variants:
                cands = [p for p in gaz.by_city.get(v, []) if same_state(p.state, state)]
                if cands:
                    found = (max(cands, key=lambda p: p.n), "city centre (facility addresses)")
                    break
        lats.append(found[0].lat if found else None)
        lons.append(found[0].lon if found else None)
        how.append(found[1] if found else "not placed")
    return nfhs.assign(lat=lats, lon=lons, placed_by=how)


def facility_confidence(finder: CareFinder, service: Service) -> pd.DataFrame:
    """Every facility with a direct mention of the service and a usable location, with its confidence."""
    rows = []
    for rec, ev in zip(finder._records, finder.evidence_for(service)):
        if not ev.has_core or rec["loc_lat"] is None:
            continue
        trust = math.prod(m for m, _ in finder.trust_factors(rec, service, ev))
        conf = ev.score * trust
        rows.append({"name": rec["name"] or "(unnamed facility)", "city": rec["city"], "state": rec["state_n"],
                     "lat": float(rec["loc_lat"]), "lon": float(rec["loc_lon"]), "confidence": round(conf, 3),
                     "label": confidence_label(conf), "dup_group": rec["dup_group"]})
    df = pd.DataFrame(rows)
    return df.sort_values("confidence", ascending=False).drop_duplicates("dup_group") if len(df) else df


def coverage(districts: pd.DataFrame, facilities: pd.DataFrame, service: Service, need: str) -> pd.DataFrame:
    """Per district: nearest High-confidence facility, counts within the travel scale, status and need."""
    ind = INDICATORS[need]
    scale = service.travel_km
    out = districts.copy()
    out["need_value"] = out[need]
    high = facilities[facilities["confidence"] >= HIGH] if len(facilities) else facilities
    med = facilities[(facilities["confidence"] >= MEDIUM) & (facilities["confidence"] < HIGH)] if len(facilities) else facilities
    near_name, near_km, n_high, n_med = [], [], [], []
    for lat, lon in zip(out["lat"], out["lon"]):
        if lat is None or (isinstance(lat, float) and math.isnan(lat)):
            near_name.append(None), near_km.append(np.nan), n_high.append(0), n_med.append(0)
            continue
        if len(high):
            d = haversine_km(high["lat"].to_numpy(), high["lon"].to_numpy(), lat, lon)
            j = int(np.argmin(d))
            near_name.append(high["name"].iloc[j])
            near_km.append(round(float(d[j]), 1))
            n_high.append(int((d <= scale).sum()))
        else:
            near_name.append(None), near_km.append(np.nan), n_high.append(0)
        if len(med):
            dm = haversine_km(med["lat"].to_numpy(), med["lon"].to_numpy(), lat, lon)
            n_med.append(int((dm <= scale).sum()))
        else:
            n_med.append(0)
    out["nearest_high"] = near_name
    out["nearest_high_km"] = near_km
    out["high_within"] = n_high
    out["medium_within"] = n_med
    out["status"] = np.select(
        [out["lat"].isna(), out["high_within"] > 0, out["medium_within"] > 0],
        ["not placed", "covered", "weak evidence only"], default="gap")
    # Need percentile across all districts in the table: 1 = most need.
    sign = -1 if ind.need_when == "low" else 1
    out["need_pct"] = (sign * out["need_value"]).rank(pct=True)
    order = {"gap": 0, "weak evidence only": 1, "covered": 2, "not placed": 3}
    out["priority"] = out["status"].map(order)
    return out.sort_values(["priority", "need_pct", "nearest_high_km"], ascending=[True, False, False]).reset_index(drop=True)


def audit_summary(finder: CareFinder) -> dict:
    """What the data checks found across every record (shown to planners as 'what we checked')."""
    f = finder.facilities
    issue = f["location_issue"].fillna("")
    return {
        "records": len(f),
        "location_fixed": int((issue == "coords_fixed").sum()),
        "location_conflict": int((issue == "coords_conflict").sum()),
        "address_inconsistent": int((issue == "address_inconsistent").sum()),
        "merged": int(f["merge_reasons"].map(bool).sum()),
        "corrupted": int(f["corrupted"].fillna(False).astype(bool).sum()),
        "duplicates": int((f["dup_count"] > 0).sum()),
        "no_sources": int(f["source_urls"].map(lambda s: not s).sum()),
    }
