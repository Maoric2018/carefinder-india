"""Distances, Indian place-name cleanup, and turning a user's location text into coordinates.

The gazetteer is built from the facility dataset itself (median coordinates of facilities in each
city / PIN code / state), so it needs no external geocoding service.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .taxonomy import normalize

INDIA_LAT = (6.5, 37.6)
INDIA_LON = (68.0, 97.5)
# A post office this far from the median of its state's post offices carries another place's coordinates
# (e.g. Aurangabad, Bihar geocoded to Aurangabad, Maharashtra). The largest states span ~500 km from their centre.
STATE_OUTLIER_KM = 700

STATE_ALIASES = {
    "orissa": "odisha", "uttaranchal": "uttarakhand", "pondicherry": "puducherry", "pondy": "puducherry",
    "nct of delhi": "delhi", "new delhi": "delhi", "national capital territory of delhi": "delhi",
    "j and k": "jammu and kashmir", "jk": "jammu and kashmir", "tamilnadu": "tamil nadu", "tn": "tamil nadu",
    "chattisgarh": "chhattisgarh", "chhatisgarh": "chhattisgarh", "telengana": "telangana",
    "up": "uttar pradesh", "mp": "madhya pradesh", "ap": "andhra pradesh", "wb": "west bengal",
    "andaman and nicobar": "andaman and nicobar islands", "daman and diu": "dadra and nagar haveli and daman and diu",
    "dadra and nagar haveli": "dadra and nagar haveli and daman and diu", "u p": "uttar pradesh",
    "nct delhi": "delhi", "delhi nct": "delhi", "nct": "delhi", "government of nct delhi": "delhi", "br": "bihar",
    "mh": "maharashtra", "ka": "karnataka", "kl": "kerala", "gj": "gujarat", "rj": "rajasthan", "hr": "haryana",
    "pb": "punjab", "jh": "jharkhand", "od": "odisha", "or": "odisha", "as": "assam", "uk": "uttarakhand",
    "hp": "himachal pradesh", "cg": "chhattisgarh", "ts": "telangana", "tg": "telangana", "wb": "west bengal",
    "jammu": "jammu and kashmir", "kashmir": "jammu and kashmir", "tamil nadu india": "tamil nadu",
}
# Old/new names of the same territory: a PIN in one of these is not evidence of a wrong state.
EQUIVALENT_STATES = [{"andhra pradesh", "telangana"}, {"jammu and kashmir", "ladakh"}]

# First digit of a PIN code -> postal region (well-established, unlike finer prefixes).
PIN_REGIONS = {
    "1": {"delhi", "haryana", "punjab", "himachal pradesh", "jammu and kashmir", "ladakh", "chandigarh"},
    "2": {"uttar pradesh", "uttarakhand"},
    "3": {"rajasthan", "gujarat", "dadra and nagar haveli and daman and diu"},
    "4": {"maharashtra", "goa", "madhya pradesh", "chhattisgarh"},
    "5": {"andhra pradesh", "telangana", "karnataka"},
    "6": {"tamil nadu", "kerala", "puducherry", "lakshadweep"},
    "7": {"west bengal", "odisha", "assam", "arunachal pradesh", "manipur", "meghalaya", "mizoram",
          "nagaland", "tripura", "sikkim", "andaman and nicobar islands"},
    "8": {"bihar", "jharkhand"},
}
KNOWN_STATES = set().union(*PIN_REGIONS.values())

CITY_ALIASES = {
    "bombay": "mumbai", "bangalore": "bengaluru", "calcutta": "kolkata", "madras": "chennai",
    "gurgaon": "gurugram", "poona": "pune", "baroda": "vadodara", "trivandrum": "thiruvananthapuram",
    "cochin": "kochi", "ernakulam": "kochi", "mysore": "mysuru", "benares": "varanasi", "banaras": "varanasi",
    "allahabad": "prayagraj", "calicut": "kozhikode", "pondicherry": "puducherry", "vizag": "visakhapatnam",
    "mangalore": "mangaluru", "belgaum": "belagavi", "gulbarga": "kalaburagi", "new delhi": "delhi",
    "trichy": "tiruchirappalli", "tiruchirapalli": "tiruchirappalli", "secunderabad": "hyderabad",
    "hubli": "hubballi", "shimoga": "shivamogga", "tumkur": "tumakuru", "bellary": "ballari",
    "cuttack city": "cuttack", "kanpur nagar": "kanpur", "navi mumbai": "navi mumbai",
}


def norm_state(value) -> str | None:
    if not value:
        return None
    s = normalize(str(value))
    s = re.sub(r"\b(state|region|india|ut|union territory)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = STATE_ALIASES.get(s, s)
    return s or None


def same_state(a: str | None, b: str | None) -> bool:
    return a == b or any(a in g and b in g for g in EQUIVALENT_STATES)


def norm_city(value) -> str | None:
    if not value:
        return None
    s = normalize(str(value))
    s = re.sub(r"\b(city|district|dist|town|urban|rural)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return CITY_ALIASES.get(s, s) or None


def pin_matches_state(pin: str | None, state: str | None) -> bool | None:
    """None when we cannot tell (no PIN, unknown state)."""
    if not pin or not state or state not in KNOWN_STATES:
        return None
    return state in PIN_REGIONS.get(pin[0], set())


def haversine_km(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = (np.radians(np.asarray(x, dtype=float)) for x in (lat1, lon1, lat2, lon2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def in_india(lat, lon) -> bool:
    return lat is not None and lon is not None and INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LON[0] <= lon <= INDIA_LON[1]


def fix_coordinates(lat, lon) -> tuple[float | None, float | None, str]:
    """Returns (lat, lon, status): ok | missing | swapped | outside_india."""
    if lat is None or lon is None or (lat == 0 and lon == 0) or np.isnan(lat) or np.isnan(lon):
        return None, None, "missing"
    if in_india(lat, lon):
        return lat, lon, "ok"
    if in_india(lon, lat):
        return lon, lat, "swapped"
    return None, None, "outside_india"


@dataclass
class Place:
    key: str
    label: str
    lat: float
    lon: float
    n: int
    spread_km: float
    state: str | None = None
    districts: tuple[str, ...] = ()
    states: tuple[str, ...] = ()


def norm_office(value) -> str | None:
    """'Abhayapuri B.O' -> 'abhayapuri'."""
    s = norm_city(value)
    if not s:
        return None
    s = re.sub(r"\s+(?:b o|s o|h o|g p o|bo|so|ho|gpo|sub office|head office|branch office)$", "", s)
    return s or None


class PinDirectory:
    """India Post PIN directory (one row per post office) aggregated to PIN, district and office level.

    Rows without coordinates are kept for district/state lookups but not for centroids.
    A PIN can map to several districts/states; we keep all of them instead of guessing.
    """

    def __init__(self, raw: pd.DataFrame):
        cols = {c.lower().replace("_", ""): c for c in raw.columns}

        def pick(*names):
            for n in names:
                if n in cols:
                    return raw[cols[n]]
            return pd.Series([None] * len(raw), index=raw.index)

        from .parse import clean_postcode, to_float
        df = pd.DataFrame({
            "pin": pick("pincode", "pin").map(clean_postcode),
            "office": pick("officename", "office").map(norm_office),
            "district": pick("district", "districtname").map(norm_city),
            "state": pick("statename", "state").map(norm_state),
            "lat": pick("latitude", "lat").map(to_float),
            "lon": pick("longitude", "lon", "lng").map(to_float),
        })
        fixed = [fix_coordinates(a, b) if a is not None and b is not None else (None, None, "missing")
                 for a, b in zip(df["lat"], df["lon"])]
        df["lat"] = [f[0] for f in fixed]
        df["lon"] = [f[1] for f in fixed]
        self.dropped_far = 0
        ok = df["lat"].notna() & df["lon"].notna() & df["state"].notna()
        if ok.any():
            pts = df.loc[ok, ["state", "lat", "lon"]].astype({"lat": float, "lon": float})
            centre = pts.groupby("state")[["lat", "lon"]].median()
            pts = pts.join(centre.add_suffix("_state"), on="state")
            far = haversine_km(pts["lat"], pts["lon"], pts["lat_state"], pts["lon_state"]) > STATE_OUTLIER_KM
            df.loc[pts.index[far], ["lat", "lon"]] = None
            self.dropped_far = int(far.sum())
        self.rows = df
        geo = df.dropna(subset=["lat", "lon"]).astype({"lat": float, "lon": float})

        self.pins: dict[str, Place] = {}
        admin = df.dropna(subset=["pin"]).groupby("pin").agg(
            districts=("district", lambda s: tuple(sorted(set(s.dropna())))),
            states=("state", lambda s: tuple(sorted(set(s.dropna()))))).to_dict("index")
        for pin, g in geo.dropna(subset=["pin"]).groupby("pin"):
            lat, lon, spread = _center(g)
            a = admin.get(pin, {})
            self.pins[pin] = Place(pin, f"PIN {pin}", lat, lon, len(g), spread,
                                   districts=a.get("districts", ()), states=a.get("states", ()))
        self.pin_admin = admin  # districts/states even for PINs with no coordinates

        self.districts: dict[str, list[Place]] = {}
        for (district, state), g in geo.dropna(subset=["district"]).assign(
                state=geo["state"].fillna("")).groupby(["district", "state"]):
            lat, lon, spread = _center(g)
            self.districts.setdefault(district, []).append(
                Place(district, _title(district, state or None) + " district", lat, lon, len(g), spread, state or None))

        self.offices: dict[str, list[Place]] = {}
        for (office, state, district), g in geo.dropna(subset=["office"]).assign(
                state=geo["state"].fillna(""), district=geo["district"].fillna("")).groupby(["office", "state", "district"]):
            label = office.title() + (f", {district.title()} district" if district else "") + (f", {state.title()}" if state else "")
            self.offices.setdefault(office, []).append(
                Place(office, label, float(g["lat"].median()), float(g["lon"].median()), len(g), 3.0, state or None))


@dataclass
class ResolvedLocation:
    lat: float
    lon: float
    label: str
    method: str
    uncertainty_km: float
    notes: list[str] = field(default_factory=list)


def _center(group: pd.DataFrame) -> tuple[float, float, float]:
    lat, lon = float(group["lat"].median()), float(group["lon"].median())
    d = haversine_km(group["lat"].to_numpy(), group["lon"].to_numpy(), lat, lon)
    spread = float(np.median(d)) if len(d) >= 3 else 5.0
    return lat, lon, max(spread, 2.0)


class Gazetteer:
    def __init__(self, points: pd.DataFrame, pin_dir: PinDirectory | None = None):
        """points: columns lat, lon, city, state, postcode, district (normalized, coords valid)."""
        self.pin_dir = pin_dir
        self.by_city: dict[str, list[Place]] = {}
        self.by_city_state: dict[tuple[str, str | None], Place] = {}
        self.by_district: dict[str, list[Place]] = {}
        self.by_pin: dict[str, Place] = {}
        self.by_pin3: dict[str, Place] = {}
        self.by_state: dict[str, Place] = {}
        pts = points.dropna(subset=["lat", "lon"]).copy()
        pts["state_key"] = pts["state"].fillna("")

        for (city, state), g in pts.dropna(subset=["city"]).groupby(["city", "state_key"]):
            lat, lon, spread = _center(g)
            place = Place(city, _title(city, state or None), lat, lon, len(g), spread, state or None)
            self.by_city.setdefault(city, []).append(place)
            self.by_city_state[(city, state or None)] = place
        for (district, state), g in pts.dropna(subset=["district"]).groupby(["district", "state_key"]):
            lat, lon, spread = _center(g)
            self.by_district.setdefault(district, []).append(
                Place(district, _title(district, state or None) + " district", lat, lon, len(g), spread, state or None))
        with_pin = pts.dropna(subset=["postcode"]).copy()
        with_pin["pin3"] = with_pin["postcode"].str[:3]
        for pin, g in with_pin.groupby("postcode"):
            lat, lon, spread = _center(g)
            self.by_pin[pin] = Place(pin, f"PIN {pin}", lat, lon, len(g), spread)
        for pin3, g in with_pin.groupby("pin3"):
            lat, lon, spread = _center(g)
            self.by_pin3[pin3] = Place(pin3, f"PIN area {pin3}xxx", lat, lon, len(g), spread)
        for state, g in pts.dropna(subset=["state"]).groupby("state"):
            lat, lon, spread = _center(g)
            self.by_state[state] = Place(state, state.title(), lat, lon, len(g), spread, state)

    def city_center(self, city: str | None, state: str | None) -> Place | None:
        if not city:
            return None
        place = self.by_city_state.get((city, state))
        if place is None and city in self.by_city and len(self.by_city[city]) == 1:
            place = self.by_city[city][0]
        return place

    def resolve(self, query: str) -> tuple[ResolvedLocation | None, str]:
        q = (query or "").strip()
        if not q:
            return None, "Please enter a location."

        m = re.fullmatch(r"\(?\s*(-?\d{1,2}(?:\.\d+)?)\s*[,\s]\s*(-?\d{2,3}(?:\.\d+)?)\s*\)?", q)
        if m:
            lat, lon, status = fix_coordinates(float(m.group(1)), float(m.group(2)))
            if lat is None:
                return None, f"Coordinates {q} are not inside India."
            notes = ["Latitude and longitude looked swapped; we swapped them back."] if status == "swapped" else []
            return ResolvedLocation(lat, lon, f"{lat:.4f}, {lon:.4f}", "coordinates", 0.0, notes), ""

        notes: list[str] = []
        pd_ = self.pin_dir
        pin_m = re.search(r"\b[1-9]\d{5}\b", q)
        if pin_m:
            pin = pin_m.group()
            if pd_ is not None and pin in pd_.pins:
                p = pd_.pins[pin]
                where = ", ".join(d.title() for d in p.districts) or "unknown district"
                n = [f"Centre of {p.n} post offices with this PIN (India Post directory), {where}."]
                if len(p.districts) > 1:
                    n.append(f"This PIN spans {len(p.districts)} districts, so the location is approximate.")
                return ResolvedLocation(p.lat, p.lon, f"PIN {pin} ({where})", "PIN code", p.spread_km, n), ""
            if pin in self.by_pin:
                p = self.by_pin[pin]
                return ResolvedLocation(p.lat, p.lon, p.label, "PIN code", p.spread_km,
                                        [f"Centre of {p.n} facilities with this PIN in the data."]), ""
            if pin[:3] in self.by_pin3:
                p = self.by_pin3[pin[:3]]
                return ResolvedLocation(p.lat, p.lon, f"near PIN {pin}", "PIN area", p.spread_km,
                                        [f"PIN {pin} isn't in the data; used the centre of its area ({pin[:3]}xxx)."]), ""
            notes.append(f"PIN {pin} isn't in the data, so we used the place name instead.")
            q = q.replace(pin, " ")

        parts = [p.strip() for p in re.split(r"[,;/]", q) if p.strip()]
        state = next((norm_state(p) for p in parts if norm_state(p) in self.by_state or norm_state(p) in KNOWN_STATES), None)
        place_parts = [p for p in parts if norm_state(p) != state] or parts

        indexes = [(self.by_city, "city", "facilities listed in"), (self.by_district, "district", "facilities listed in")]
        if pd_ is not None:
            indexes = [(self.by_city, "city", "facilities listed in"), (pd_.districts, "district", "post offices in"),
                       (pd_.offices, "post office / town", "post office records for")]
        for exact in (True, False):
            for part in place_parts + [q]:
                for index, kind, what in indexes:
                    is_office = kind.startswith("post")
                    if is_office and not exact:
                        continue  # ~150k office names: exact match only, fuzzy would be slow and noisy
                    key = norm_office(part) if is_office else norm_city(part)
                    hit = self._lookup(key, index, state, fuzzy=not exact)
                    if hit:
                        place, how = hit
                        return ResolvedLocation(place.lat, place.lon, place.label, kind, place.spread_km,
                                                notes + how + [f"Centre of {place.n} {what} {place.label}."]), ""

        if state and state in self.by_state:
            p = self.by_state[state]
            return ResolvedLocation(p.lat, p.lon, p.label, "state", p.spread_km,
                                    notes + ["Only the state was recognised, so distances are very rough. "
                                             "Add a city, district or PIN code."]), ""
        return None, (f"Couldn't find '{query}' among the cities, districts and PIN codes in the data. "
                      "Try a nearby town, a 6-digit PIN code, or 'lat, lon' coordinates.")

    @staticmethod
    def _lookup(key, index, state, fuzzy: bool = True) -> tuple[Place, list[str]] | None:
        if not key:
            return None
        how: list[str] = []
        places = index.get(key)
        if not places:
            if not fuzzy:
                return None
            match = difflib.get_close_matches(key, list(index), n=1, cutoff=0.85)
            if not match:
                return None
            places = index[match[0]]
            how.append(f"Interpreted '{key}' as '{match[0].title()}'.")
        if state:
            in_state = [p for p in places if p.state == state]
            if in_state:
                places = in_state
        best = max(places, key=lambda p: p.n)
        others = [p.label for p in places if p is not best and p.state in KNOWN_STATES and p.n >= 3
                  and not same_state(p.state, best.state)]
        if others:
            how.append(f"There is also a '{key.title()}' in {', '.join(others)}; add the state to pick that one.")
        return best, how


def _title(city: str, state: str | None) -> str:
    return f"{city.title()}, {state.title()}" if state else city.title()
