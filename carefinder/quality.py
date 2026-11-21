"""Record-level trust checks.

Location: a facility has up to three location signals (its coordinates, its city, its PIN code). We let
them vote: coordinates that agree with the city or the PIN are trusted; coordinates that disagree with
both are replaced by the address when the city and PIN agree with each other; otherwise the location is
marked unresolved. Also: merged records (claims that describe other facilities), corrupted rows whose
columns are shifted, coordinates shared by many facilities (city-centre placeholders), duplicates.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .evidence import _sentences
from .geo import (KNOWN_STATES, PIN_REGIONS, Gazetteer, PinDirectory, fix_coordinates, haversine_km, norm_city,
                  norm_state, pin_matches_state, same_state)
from .names import other_facility, own_website, tokens
from .taxonomy import normalize

AGREE_MIN_KM = 25            # two location signals "agree" if within max(this, 3 x the place's spread)
MIN_CITY_POINTS = 3          # need this many facilities before trusting a city's centre
SHARED_COORD_MIN = 3         # this many differently-named facilities on one point = placeholder geocode
BREADTH_CLAIMS = 40          # informational only
KNOWN_FACILITY_TYPES = {"hospital", "clinic", "dentist", "doctor", "farmacy", "pharmacy", "ngo", "facility"}


def _classify(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bdent", t):
        return "dental"
    if re.search(r"hospital|medical college|nursing home|institute of medical|aiims|sanatorium", t):
        return "hospital"
    if re.search(r"pharmac|farmac|chemist|medical store|drug store|\bmedicos?\b", t):
        return "pharmacy"
    if re.search(r"diagnost|imaging|scan centre|scan center|\blab\b|laborator|patholog", t):
        return "diagnostic"
    if re.search(r"clinic|dispensary|health cent|\bphc\b|\bchc\b|doctor|practice", t):
        return "clinic"
    return None


def facility_kind(facility_type: str | None, name: str | None) -> str:
    for text in (facility_type, name):
        if text:
            kind = _classify(text)
            if kind:
                return kind
    return "unknown"


def _completeness(row) -> float:
    checks = [
        row["coord_status"] in ("ok", "swapped"), bool(row["postcode"]), row["capacity"] is not None,
        row["num_doctors"] is not None, row["year_established"] is not None, bool(row["equipment"]),
        bool(row["procedure"]), bool(row["source_urls"]),
    ]
    return round(sum(checks) / len(checks), 2)


def _nan_to_none(v):
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v


def _km(a_lat, a_lon, b_lat, b_lon) -> float:
    return float(haversine_km(a_lat, a_lon, b_lat, b_lon))


def assess(df: pd.DataFrame, pin_dir: PinDirectory | None = None) -> tuple[pd.DataFrame, Gazetteer]:
    """Add trust columns to a standardized frame and build the gazetteer from trustworthy points."""
    df = df.copy()
    for c in ("capacity", "num_doctors", "year_established", "lat", "lon"):
        df[c] = df[c].astype(object).map(_nan_to_none)
    pins = pin_dir.pins if pin_dir is not None else {}
    pin_admin = pin_dir.pin_admin if pin_dir is not None else {}
    valid_states = set(KNOWN_STATES)
    for a in pin_admin.values():
        valid_states.update(a["states"])

    # States: the state column is often a city or junk ("Br", "Mumbai"); fall back to the PIN's state.
    given_state = df["state"].map(norm_state)
    df["state_given_valid"] = given_state.isin(valid_states)

    def resolve_state(s, pin):
        if s in valid_states:
            return s
        states = pin_admin.get(pin, {}).get("states", ())
        return states[0] if len(states) == 1 else None

    df["state_n"] = [resolve_state(s, p) for s, p in zip(given_state, df["postcode"])]
    df["city_n"] = df["city"].map(norm_city)
    df["district_n"] = [norm_city(d) or next(iter(pin_admin.get(p, {}).get("districts", ())), None)
                        for d, p in zip(df["district"], df["postcode"])]
    fixed = [fix_coordinates(a, b) for a, b in zip(df["lat"], df["lon"])]
    df["lat"] = [f[0] for f in fixed]
    df["lon"] = [f[1] for f in fixed]
    df["coord_status"] = [f[2] for f in fixed]
    df["kind"] = [facility_kind(t, n) for t, n in zip(df["facility_type"], df["name"])]

    # Rows whose columns are shifted (a latitude in facilityTypeId, a specialty list in organization_type...).
    def misaligned(org, ftype):
        if org and normalize(org) not in ("facility", "ngo", "organization"):
            return True
        return bool(ftype) and normalize(ftype) not in KNOWN_FACILITY_TYPES

    df["corrupted"] = [misaligned(o, t) for o, t in zip(df["organization_type"], df["facility_type"])]

    # Coordinates shared by several differently-named facilities are a city-centre placeholder, not a location.
    has_coords = df["coord_status"].isin(["ok", "swapped"])
    key = pd.Series([f"{a:.4f},{b:.4f}" if ok else None for a, b, ok in zip(df["lat"], df["lon"], has_coords)],
                    index=df.index)
    names_per_point = df.assign(_k=key, _n=df["name"].fillna("").str.lower()).groupby("_k")["_n"].nunique()
    df["coord_shared_n"] = [int(names_per_point.get(k, 1)) - 1 if k else 0 for k in key]

    def points(mask):
        p = df.loc[mask, ["lat", "lon", "city_n", "state_n", "postcode", "district_n"]]
        return p.rename(columns={"city_n": "city", "state_n": "state", "district_n": "district"}).astype(
            {"lat": float, "lon": float})

    first_pass = Gazetteer(points(has_coords))

    # ---- location vote: coordinates vs city vs PIN -------------------------------------------------
    out = {k: [] for k in ("loc_lat", "loc_lon", "loc_quality", "location_issue", "location_detail", "km_from_city")}
    for row in df.itertuples():
        city_c = first_pass.city_center(row.city_n, row.state_n)
        if city_c is not None and city_c.n < MIN_CITY_POINTS:
            city_c = None
        pin_c = pins.get(row.postcode) if row.postcode else None
        issue, detail = None, ""
        d_city = None

        if row.coord_status in ("ok", "swapped"):
            refs = []
            if city_c is not None:
                d_city = _km(row.lat, row.lon, city_c.lat, city_c.lon)
                refs.append(("city", row.city, d_city, d_city <= max(AGREE_MIN_KM, 3 * city_c.spread_km)))
            if pin_c is not None:
                d_pin = _km(row.lat, row.lon, pin_c.lat, pin_c.lon)
                refs.append(("PIN", row.postcode, d_pin, d_pin <= max(AGREE_MIN_KM, 3 * pin_c.spread_km)))
            agree = [r for r in refs if r[3]]
            disagree = [r for r in refs if not r[3]]
            lat, lon = row.lat, row.lon
            quality = "shared coordinates" if row.coord_shared_n + 1 >= SHARED_COORD_MIN else "exact"
            if not refs:
                quality = "unverified coordinates" if quality == "exact" else quality
            elif agree and disagree:
                issue = "address_inconsistent"
                r = disagree[0]
                detail = (f"its {r[0]} ({r[1]}) is {r[2]:.0f} km from where its coordinates and "
                          f"{agree[0][0]} place it")
            elif not agree:
                both = city_c is not None and pin_c is not None
                if both and _km(city_c.lat, city_c.lon, pin_c.lat, pin_c.lon) <= max(
                        AGREE_MIN_KM, 3 * max(city_c.spread_km, pin_c.spread_km)):
                    issue = "coords_fixed"
                    detail = f"coordinates were {d_city:.0f} km from both its city and its PIN, so we used its address"
                    lat, lon, quality = pin_c.lat, pin_c.lon, "PIN area"
                elif not both:
                    r = refs[0]
                    issue = "coords_conflict"
                    detail = f"coordinates are {r[2]:.0f} km from its {r[0]} ({r[1]}) and nothing else to check against"
                    ref = city_c if city_c is not None else pin_c
                    lat, lon, quality = ref.lat, ref.lon, ("city centre" if city_c is not None else "PIN area")
                else:
                    issue = "coords_conflict"
                    detail = (f"its coordinates, city ({row.city}) and PIN ({row.postcode}) all point to different "
                              "places")
                    quality = "conflicting coordinates"
        else:
            place, quality = pin_c, "PIN area"
            if place is None:
                place, quality = city_c or first_pass.city_center(row.city_n, row.state_n), "city centre"
            if place is None and row.district_n and pin_dir is not None and row.district_n in pin_dir.districts:
                place, quality = pin_dir.districts[row.district_n][0], "district centre"
            lat, lon = (place.lat, place.lon) if place is not None else (None, None)
            if place is None:
                quality = "unknown"
        out["loc_lat"].append(lat)
        out["loc_lon"].append(lon)
        out["loc_quality"].append(quality)
        out["location_issue"].append(issue)
        out["location_detail"].append(detail)
        out["km_from_city"].append(round(d_city, 1) if d_city is not None else None)
    for k, v in out.items():
        df[k] = v
    df["coords_conflict"] = df["location_issue"].isin(["coords_fixed", "coords_conflict"])
    df["conflict_detail"] = df["location_detail"]

    trusted = has_coords & df["location_issue"].isna() & (df["loc_quality"] == "exact")
    gaz = Gazetteer(points(trusted), pin_dir)

    # ---- PIN vs state (only when the state column holds a real state) ----------------------------
    def pin_mismatch(pin, given):
        if given not in valid_states:
            return False
        states = pin_admin.get(pin, {}).get("states")
        if states:
            return not any(same_state(given, s) for s in states)
        return pin_matches_state(pin, given) is False

    df["pin_state_mismatch"] = [pin_mismatch(p, s) for p, s in zip(df["postcode"], given_state)]

    # ---- possible merged records -----------------------------------------------------------------
    big_cities = {c: {p.state for p in places} for c, places in gaz.by_city.items()
                  if len(c) >= 5 and sum(p.n for p in places) >= 10}
    city_re = re.compile(r"(?<![a-z])(" + "|".join(re.escape(c) for c in sorted(big_cities, key=len, reverse=True))
                         + r")(?![a-z])") if big_cities else None
    merge_reasons, others_col = [], []
    for row in df.itertuples():
        reasons = []
        own = tokens(row.name)
        texts = [*row.capability, *row.procedure, *row.equipment, *(_sentences(row.description or ""))]
        others: list[str] = []
        for t in texts:
            o = other_facility(str(t), own)
            if o and o not in others:
                others.append(o)
        if len(others) >= 2:
            reasons.append(f"{len(others)} of its claims describe other facilities (e.g. “{others[0]}”, “{others[1]}”)")
        desc = row.description or ""
        own_region = row.postcode[0] if row.postcode else next(
            (k for k, states in PIN_REGIONS.items() if row.state_n in states), None)
        other_pins = sorted({p for p in re.findall(r"\b[1-9]\d{5}\b", desc) if own_region and p[0] != own_region})
        if other_pins:
            reasons.append(f"its description mentions PIN codes from another part of India ({', '.join(other_pins[:3])})")
        if city_re is not None and row.state_n:
            blob = normalize(" ".join([desc, *row.capability]))
            mentioned = {c for c in city_re.findall(blob)
                         if c != row.city_n and not any(same_state(row.state_n, s) for s in big_cities[c])}
            if len(mentioned) >= 2:
                reasons.append("its claims mention places in other states ("
                               + ", ".join(sorted(m.title() for m in mentioned)[:4]) + ")")
        merge_reasons.append(reasons)
        others_col.append(others[:5])
    df["merge_reasons"] = merge_reasons
    df["other_facilities"] = others_col

    df["own_site"] = [own_website(n, [*s, *w]) for n, s, w in zip(df["name"], df["source_urls"], df["website"])]
    df["n_claims"] = [len(a) + len(b) + len(c) + len(d) for a, b, c, d in
                      zip(df["specialties"], df["capability"], df["procedure"], df["equipment"])]
    df["breadth_flag"] = [n >= BREADTH_CLAIMS and k in ("clinic", "pharmacy", "dental", "diagnostic")
                          for n, k in zip(df["n_claims"], df["kind"])]
    df["completeness"] = [_completeness(r) for r in df.to_dict("records")]

    # Duplicate records of the same facility: same normalized name in the same PIN / city / spot.
    def loc_key(r):
        if r["postcode"]:
            return r["postcode"]
        if r["city_n"]:
            return r["city_n"]
        if r["lat"] is not None:
            return f"{r['lat']:.2f},{r['lon']:.2f}"
        return r["id"]

    records = df.to_dict("records")
    df["dup_group"] = [f"{normalize(r['name'] or r['id'])}|{loc_key(r)}" for r in records]
    df["dup_count"] = df.groupby("dup_group")["id"].transform("count") - 1
    return df, gaz
