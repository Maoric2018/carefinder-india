"""Map the dataset's real column names onto the logical fields the pipeline uses.

We have not seen the final schema yet, so detection is name-based and every mapping can be
overridden explicitly (see CareFinder(column_overrides=...)).
"""

from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from .parse import clean_postcode, to_float, to_list, to_text, to_year

# Logical field -> candidate column names, most likely first.
LOGICAL_FIELDS: dict[str, list[str]] = {
    "id": ["pk_unique_id", "unique_id", "facility_id", "id", "uuid"],
    "name": ["name", "facility_name", "organization_name", "hospital_name"],
    "facility_type": ["facility_type_id", "facility_type", "type"],
    "organization_type": ["organization_type", "org_type"],
    "operator_type": ["operator_type_id", "operator_type", "ownership"],
    "address": ["address_line1", "address_line_1", "address", "full_address"],
    "city": ["address_city", "city", "town"],
    "district": ["address_district", "district"],
    "state": ["address_state_or_region", "state", "address_state", "region"],
    "postcode": ["address_zip_or_postcode", "postcode", "pincode", "pin_code", "zip", "zipcode", "postal_code"],
    "lat": ["latitude", "lat", "address_latitude", "geo_lat"],
    "lon": ["longitude", "lon", "lng", "long", "address_longitude", "geo_lon"],
    "specialties": ["specialties", "specialty", "specialities"],
    "capability": ["capability", "capabilities"],
    "procedure": ["procedure", "procedures"],
    "equipment": ["equipment", "equipments"],
    "description": ["description", "organization_description", "facility_description", "about"],
    "year_established": ["year_established", "established", "founded"],
    "num_doctors": ["number_doctors", "num_doctors", "number_of_doctors", "doctors"],
    "capacity": ["capacity", "bed_capacity", "beds", "number_of_beds", "num_beds"],
    "source_urls": ["source_urls", "source_url", "sources", "source"],
    "website": ["official_website", "website", "websites"],
    "phone": ["official_phone", "phone_numbers", "phone", "phones"],
}

LIST_FIELDS = ("specialties", "capability", "procedure", "equipment", "source_urls", "website", "phone")
EVIDENCE_FIELDS = ("procedure", "equipment", "capability", "specialties", "description")


def _norm(col: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(col))
    return re.sub(r"[^0-9a-zA-Z]+", "_", s).strip("_").lower()


def detect_columns(columns: Iterable[str], overrides: dict[str, str] | None = None) -> dict[str, str | None]:
    """Return {logical_field: actual_column_or_None}."""
    overrides = overrides or {}
    columns = list(columns)
    by_key: dict[str, str] = {}
    for c in columns:
        by_key.setdefault(_norm(c), c)
        by_key.setdefault(_norm(c).replace("_", ""), c)

    mapping: dict[str, str | None] = {}
    used: set[str] = set(overrides.values())
    for field, candidates in LOGICAL_FIELDS.items():
        if field in overrides:
            mapping[field] = overrides[field]
            continue
        found = None
        for cand in candidates:
            for key in (_norm(cand), _norm(cand).replace("_", "")):
                col = by_key.get(key)
                if col is not None and col not in used:
                    found = col
                    break
            if found:
                break
        mapping[field] = found
        if found:
            used.add(found)
    return mapping


def standardize(df: pd.DataFrame, mapping: dict[str, str | None]) -> pd.DataFrame:
    """Build a clean frame with logical column names and parsed values."""

    def col(field):
        src = mapping.get(field)
        if src is None or src not in df.columns:
            return pd.Series([None] * len(df), index=df.index)
        return df[src]

    out = pd.DataFrame(index=df.index)
    ids = col("id")
    out["id"] = [str(v) if v is not None and str(v).strip() not in ("", "nan", "None") else f"row-{i}"
                 for i, v in zip(range(len(df)), ids)]
    for field in ("name", "facility_type", "organization_type", "operator_type", "address", "city", "district",
                  "state", "description"):
        out[field] = col(field).map(to_text)
    out["postcode"] = col("postcode").map(clean_postcode)
    out["lat"] = col("lat").map(to_float)
    out["lon"] = col("lon").map(to_float)
    for field in LIST_FIELDS:
        out[field] = col(field).map(to_list)
    out["year_established"] = col("year_established").map(to_year)
    out["num_doctors"] = col("num_doctors").map(to_float)
    out["capacity"] = col("capacity").map(to_float)
    return out.reset_index(drop=True)
