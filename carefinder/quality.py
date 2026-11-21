"""Record-level trust checks: is the location consistent, is this possibly two facilities merged,
are the claims plausible for the facility's size and type, and which records are duplicates."""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .geo import (PIN_REGIONS, Gazetteer, PinDirectory, fix_coordinates, haversine_km, norm_city, norm_state,
                  pin_matches_state)
from .taxonomy import normalize

_FACILITY_NOUN = r"(?:hospital|clinic|nursing home|medical cent(?:re|er)|diagnostics?|health cent(?:re|er)|dispensary|polyclinic)"
_TWO_FACILITIES = re.compile(rf"{_FACILITY_NOUN}\b.*?(?:\band\b|&|/|\+).*?\b{_FACILITY_NOUN}", re.IGNORECASE)

MIN_CITY_POINTS = 3          # need this many facilities before trusting a city's centre
CONFLICT_MIN_KM = 25         # coordinates further than this (and 4x the city's spread) from the city = conflict
BREADTH_CLAIMS = 40          # this many claimed items is suspicious for a small facility


def _classify(text: str) -> str | None:
    t = text.lower()
    if re.search(r"\bdent", t):
        return "dental"
    if re.search(r"hospital|medical college|nursing home|institute of medical|aiims|sanatorium", t):
        return "hospital"
    if re.search(r"pharmac|chemist|medical store|drug store|\bmedicos?\b", t):
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


def assess(df: pd.DataFrame, pin_dir: PinDirectory | None = None) -> tuple[pd.DataFrame, Gazetteer]:
    """Add trust columns to a standardized frame and build the gazetteer from trustworthy points."""
    df = df.copy()
    for c in ("capacity", "num_doctors", "year_established", "lat", "lon"):
        df[c] = df[c].astype(object).map(_nan_to_none)
    df["state_n"] = df["state"].map(norm_state)
    df["city_n"] = df["city"].map(norm_city)
    df["district_n"] = df["district"].map(norm_city)
    fixed = [fix_coordinates(a, b) for a, b in zip(df["lat"], df["lon"])]
    df["lat"] = [f[0] for f in fixed]
    df["lon"] = [f[1] for f in fixed]
    df["coord_status"] = [f[2] for f in fixed]
    df["kind"] = [facility_kind(t, n) for t, n in zip(df["facility_type"], df["name"])]
    pins = pin_dir.pins if pin_dir is not None else {}
    pin_admin = pin_dir.pin_admin if pin_dir is not None else {}
    df["district_n"] = [d or next(iter(pin_admin.get(p, {}).get("districts", ())), None)
                        for d, p in zip(df["district_n"], df["postcode"])]

    def points(mask):
        p = df.loc[mask, ["lat", "lon", "city_n", "state_n", "postcode", "district_n"]]
        return p.rename(columns={"city_n": "city", "state_n": "state", "district_n": "district"}).astype(
            {"lat": float, "lon": float})

    has_coords = df["coord_status"].isin(["ok", "swapped"])
    first_pass = Gazetteer(points(has_coords))

    km_from_city, conflict, conflict_detail = [], [], []
    for row in df.itertuples():
        details = []
        d_city = None
        if row.coord_status in ("ok", "swapped"):
            center = first_pass.city_center(row.city_n, row.state_n)
            if center is not None and center.n >= MIN_CITY_POINTS:
                d_city = float(haversine_km(row.lat, row.lon, center.lat, center.lon))
                if d_city > max(CONFLICT_MIN_KM, 4 * center.spread_km):
                    details.append(f"{d_city:.0f} km from {row.city}")
            pin_place = pins.get(row.postcode)
            if pin_place is not None:
                d_pin = float(haversine_km(row.lat, row.lon, pin_place.lat, pin_place.lon))
                if d_pin > max(CONFLICT_MIN_KM + 5, 4 * pin_place.spread_km):
                    details.append(f"{d_pin:.0f} km from its PIN {row.postcode}")
        km_from_city.append(round(d_city, 1) if d_city is not None else None)
        conflict.append(bool(details))
        conflict_detail.append("; ".join(details))
    df["km_from_city"] = km_from_city
    df["coords_conflict"] = conflict
    df["conflict_detail"] = conflict_detail

    gaz = Gazetteer(points(has_coords & ~df["coords_conflict"]), pin_dir)

    # Where we measure distance from, and how good that position is.
    loc_lat, loc_lon, loc_quality = [], [], []
    for row in df.itertuples():
        if row.coord_status in ("ok", "swapped") and not row.coords_conflict:
            loc_lat.append(row.lat), loc_lon.append(row.lon), loc_quality.append("exact")
            continue
        place, quality = pins.get(row.postcode), "PIN area"
        if place is None:
            place, quality = gaz.city_center(row.city_n, row.state_n), "city centre"
        if place is None and row.postcode and row.postcode in gaz.by_pin:
            place, quality = gaz.by_pin[row.postcode], "PIN area"
        if place is None and row.district_n in gaz.by_district:
            place, quality = gaz.by_district[row.district_n][0], "district centre"
        if place is None and row.coords_conflict:  # nothing better than the conflicting coordinates
            place, quality = None, "conflicting coordinates"
            loc_lat.append(row.lat), loc_lon.append(row.lon), loc_quality.append(quality)
            continue
        loc_lat.append(place.lat if place else None)
        loc_lon.append(place.lon if place else None)
        loc_quality.append(quality if place else "unknown")
    df["loc_lat"], df["loc_lon"], df["loc_quality"] = loc_lat, loc_lon, loc_quality

    def pin_mismatch(pin, state):
        states = pin_admin.get(pin, {}).get("states")
        if states and state:
            return state not in states
        return pin_matches_state(pin, state) is False

    df["pin_state_mismatch"] = [pin_mismatch(p, s) for p, s in zip(df["postcode"], df["state_n"])]

    # Possible merged records.
    big_cities = {c: {p.state for p in places} for c, places in gaz.by_city.items()
                  if len(c) >= 5 and sum(p.n for p in places) >= 10}
    city_re = re.compile(r"(?<![a-z])(" + "|".join(re.escape(c) for c in sorted(big_cities, key=len, reverse=True))
                         + r")(?![a-z])") if big_cities else None
    merge_reasons = []
    for row in df.itertuples():
        reasons = []
        if row.name and _TWO_FACILITIES.search(row.name):
            reasons.append("the name looks like two facilities joined together")
        desc = row.description or ""
        own_region = row.postcode[0] if row.postcode else next(
            (k for k, states in PIN_REGIONS.items() if row.state_n in states), None)
        other_pins = sorted({p for p in re.findall(r"\b[1-9]\d{5}\b", desc) if own_region and p[0] != own_region})
        if other_pins:
            reasons.append(f"the description mentions PIN codes from another part of India ({', '.join(other_pins[:3])})")
        if city_re is not None and row.state_n and desc:
            mentioned = {c for c in city_re.findall(normalize(desc))
                         if c != row.city_n and row.state_n not in big_cities[c]}
            if len(mentioned) >= 2:
                reasons.append("the description mentions places in other states ("
                               + ", ".join(sorted(m.title() for m in mentioned)[:4]) + ")")
        merge_reasons.append(reasons)
    df["merge_reasons"] = merge_reasons

    df["n_claims"] = [len(a) + len(b) + len(c) + len(d) for a, b, c, d in
                      zip(df["specialties"], df["capability"], df["procedure"], df["equipment"])]
    small = [(cap is not None and cap < 30) or (doc is not None and doc < 5) or kind in ("clinic", "pharmacy", "dental", "diagnostic")
             for cap, doc, kind in zip(df["capacity"], df["num_doctors"], df["kind"])]
    df["breadth_flag"] = [n >= BREADTH_CLAIMS and s for n, s in zip(df["n_claims"], small)]
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
