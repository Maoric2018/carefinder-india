"""Search: service + location -> ranked facilities, each with cited evidence and an explanation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .evidence import (CORE_STRENGTH, FIELD_LABELS, FIELD_WEIGHTS, SPECIFIC_DETAIL_WEIGHT, SUPPORT_STRENGTH,
                       Evidence, score_evidence)
from .geo import PinDirectory, ResolvedLocation, haversine_km
from .quality import assess
from .schema import detect_columns, standardize
from .taxonomy import SERVICES, Service, ad_hoc_service, find_service

# Multipliers applied to the evidence score. Kept in one place so the "how we decided" text
# shown to users is generated from the same numbers the code uses.
TRUST = {
    "location_conflict": (0.60, "its coordinates contradict its stated city or PIN code"),
    "location_city": (0.90, "no usable coordinates, so distance is from its city centre"),
    "location_pin": (0.88, "no usable coordinates, so distance is from its PIN area"),
    "pin_state_mismatch": (0.85, "its PIN code belongs to a different region than its state"),
    "merged": (0.80, "the record may merge more than one facility"),
    "breadth": (0.85, "it claims an unusually long list of services for its size"),
    "no_sources": (0.90, "no source URL to check against"),
    "wrong_kind": (0.40, "it is listed as a pharmacy or dental practice"),
    "clinic": (0.80, "it looks like a clinic, and this service usually needs a hospital"),
    "too_small": (0.70, "its listed bed count is below what this service usually needs"),
    "negated": (0.70, "some of its own text says the service is unavailable, planned or referred elsewhere"),
}
LABELS = ((0.70, "High"), (0.45, "Medium"), (0.0, "Low"))


def confidence_label(score: float) -> str:
    return next(label for cut, label in LABELS if score >= cut)


@dataclass
class SearchResult:
    service: Service | None
    service_note: str = ""
    location: ResolvedLocation | None = None
    results: pd.DataFrame = field(default_factory=pd.DataFrame)
    notes: list[str] = field(default_factory=list)
    error: str = ""
    candidates: int = 0

    def to_markdown(self) -> str:
        if self.error:
            return f"**{self.error}**"
        loc = self.location
        out = [f"### {self.service.label} near {loc.label}",
               f"_Service: {self.service_note}. Location resolved by {loc.method}"
               + (f" (±{loc.uncertainty_km:.0f} km)" if loc.uncertainty_km else "") + "._"]
        out += [f"> {n}" for n in loc.notes + self.notes]
        for r in self.results.itertuples():
            out.append(f"\n#### {r.rank}. {r.name} · {_km(r.distance_km)} · {r.confidence_label} confidence")
            out.append(r.explanation)
        return "\n".join(out)

    def to_json(self) -> str:
        return self.results.drop(columns=["explanation"], errors="ignore").to_json(orient="records")


class CareFinder:
    def __init__(self, raw: pd.DataFrame, column_overrides: dict[str, str] | None = None,
                 pin_directory: pd.DataFrame | None = None):
        """raw: facility table. pin_directory: optional India Post PIN directory (one row per post office)."""
        self.mapping = detect_columns(raw.columns, column_overrides)
        self.pin_dir = PinDirectory(pin_directory) if pin_directory is not None else None
        self.facilities, self.gazetteer = assess(standardize(raw, self.mapping), self.pin_dir)
        self._records = self.facilities.to_dict("records")
        self._evidence: dict[str, list[Evidence]] = {}

    # ---- evidence -------------------------------------------------------------------------
    def evidence_for(self, service: Service) -> list[Evidence]:
        if service.key not in self._evidence:
            self._evidence[service.key] = [score_evidence(r, service) for r in self._records]
        return self._evidence[service.key]

    def trust_factors(self, row: dict, service: Service, ev: Evidence) -> list[tuple[float, str]]:
        f: list[tuple[float, str]] = []

        def add(key, detail=""):
            mult, reason = TRUST[key]
            f.append((mult, reason + (f" ({detail})" if detail else "")))

        if row["coords_conflict"]:
            add("location_conflict", row["conflict_detail"])
        elif row["loc_quality"] == "city centre":
            add("location_city")
        elif row["loc_quality"] in ("PIN area", "district centre"):
            add("location_pin")
        if row["pin_state_mismatch"]:
            add("pin_state_mismatch", f"PIN {row['postcode']} vs {row['state']}")
        if row["merge_reasons"]:
            add("merged", "; ".join(row["merge_reasons"]))
        if row["breadth_flag"]:
            add("breadth", f"{row['n_claims']} items")
        if not row["source_urls"]:
            add("no_sources")
        kind = row["kind"]
        if kind == "pharmacy" or (kind == "dental" and service.key != "dental"):
            add("wrong_kind", kind)
        elif kind in ("clinic", "diagnostic") and service.needs_hospital:
            add("clinic")
        if service.min_beds and row["capacity"] is not None and row["capacity"] < service.min_beds:
            add("too_small", f"{row['capacity']:.0f} beds listed, usually ≥{service.min_beds}")
        if ev.negated:
            add("negated", f'"{ev.negated[0].snippet}"')
        return f

    # ---- search ---------------------------------------------------------------------------
    def search(self, service_query: str, location_query: str, top_k: int = 5,
               max_km: float | None = None) -> SearchResult:
        service, how = find_service(service_query)
        notes: list[str] = []
        if service is None:
            service = ad_hoc_service(service_query)
            how = "not in our service list, so we searched for your exact words (no synonyms)"
            notes.append(f"'{service_query}' isn't one of the services we've mapped synonyms for, so we matched "
                         "your exact words only. Results may miss facilities that describe it differently.")
        result = SearchResult(service=service, service_note=how, notes=notes)

        loc, err = self.gazetteer.resolve(location_query)
        if loc is None:
            result.error = err
            return result
        result.location = loc
        if loc.uncertainty_km > 15:
            notes.append(f"Your location is approximate (±{loc.uncertainty_km:.0f} km). "
                         "A PIN code or coordinates will give better distances.")

        evs = self.evidence_for(service)
        idx = [i for i, e in enumerate(evs) if e.has_core and self._records[i]["loc_lat"] is not None]
        result.candidates = len(idx)
        if not idx:
            result.error = f"No facility in the dataset has usable evidence of offering {service.label.lower()}."
            return result

        rows = [self._records[i] for i in idx]
        dist = haversine_km(np.array([r["loc_lat"] for r in rows], dtype=float),
                            np.array([r["loc_lon"] for r in rows], dtype=float), loc.lat, loc.lon)
        table = []
        for i, r, d in zip(idx, rows, dist):
            ev = evs[i]
            factors = self.trust_factors(r, service, ev)
            trust = math.prod(m for m, _ in factors)
            conf = ev.score * trust
            table.append({"i": i, "distance_km": round(float(d), 1), "evidence": ev.score,
                          "trust": round(trust, 3), "confidence": round(conf, 3),
                          "proximity": math.exp(-float(d) / service.travel_km),
                          "factors": factors})
        cand = pd.DataFrame(table)
        cand["rank_score"] = cand["confidence"] * cand["proximity"]
        cand["dup_group"] = [self._records[i]["dup_group"] for i in cand["i"]]

        limit = max_km or max(3 * service.travel_km, 100)
        within = cand[cand["distance_km"] <= limit]
        if within.empty:
            notes.append(f"No facility within {limit:.0f} km claims {service.label.lower()}. "
                         "Showing the nearest ones further away.")
            within = cand.nsmallest(top_k * 3, "distance_km")
        top = (within.sort_values("rank_score", ascending=False)
                     .drop_duplicates("dup_group").head(top_k).reset_index(drop=True))

        nearest = cand.nsmallest(1, "distance_km").iloc[0]
        if nearest["i"] not in set(top["i"]):
            r = self._records[int(nearest["i"])]
            ev = evs[int(nearest["i"])]
            notes.append(
                f"The nearest facility that mentions {service.label.lower()} is {r['name']} "
                f"({_km(nearest['distance_km'])}), but it ranks lower: {confidence_label(nearest['confidence'])} "
                f"confidence ({_evidence_summary(ev)}"
                + (f"; {nearest['factors'][0][1]}" if nearest["factors"] else "") + ").")
        if (top["confidence"].map(confidence_label) == "Low").any():
            notes.append("Results marked Low are weakly supported claims. Call ahead to confirm before travelling.")

        result.results = pd.DataFrame([self._result_row(n + 1, t, service, loc) for n, t in enumerate(top.to_dict("records"))])
        return result

    def _result_row(self, rank: int, t: dict, service: Service, loc: ResolvedLocation) -> dict:
        r = self._records[t["i"]]
        ev = self.evidence_for(service)[t["i"]]
        unknowns = [label for key, label in (("capacity", "bed count"), ("num_doctors", "number of doctors"),
                                              ("year_established", "year established")) if r[key] is None]
        if not r["equipment"]:
            unknowns.append("equipment list")
        citations = [{"field": FIELD_LABELS[h.field], "kind": h.kind, "term": h.term, "text": h.snippet}
                     for h in ev.hits]
        row = {
            "rank": rank, "id": r["id"], "name": r["name"] or "(unnamed facility)", "kind": r["kind"],
            "address": r["address"], "city": r["city"], "state": r["state"], "postcode": r["postcode"],
            "lat": r["loc_lat"], "lon": r["loc_lon"], "location_quality": r["loc_quality"],
            "distance_km": t["distance_km"], "evidence_score": t["evidence"], "trust": t["trust"],
            "confidence": t["confidence"], "confidence_label": confidence_label(t["confidence"]),
            "rank_score": round(t["rank_score"], 4),
            "evidence_fields": ", ".join(FIELD_LABELS[f] for f in ev.core_fields),
            "citations": citations, "caveats": [reason for _, reason in t["factors"]], "unknowns": unknowns,
            "sources": list(r["source_urls"])[:5], "duplicates": int(r["dup_count"]),
            "capacity": r["capacity"], "num_doctors": r["num_doctors"], "year_established": r["year_established"],
            "phone": (r["phone"] or [None])[0], "website": (r["website"] or [None])[0],
        }
        row["explanation"] = explain(row, ev, t["factors"], service, loc)
        return row


def _km(d: float) -> str:
    return f"{d:.1f} km" if d < 10 else f"{d:.0f} km"


def _evidence_summary(ev: Evidence) -> str:
    if not ev.core_fields:
        return "no direct mention"
    fields = ", ".join(FIELD_LABELS[f].lower() for f in ev.core_fields)
    return f"mentioned only in {fields}" if len(ev.core_fields) == 1 else f"mentioned in {fields}"


def explain(row: dict, ev: Evidence, factors, service: Service, loc: ResolvedLocation) -> str:
    lines = [f"**Why this facility for {service.label.lower()}?**"]
    core = [c for c in row["citations"] if c["kind"] == "core"]
    support = [c for c in row["citations"] if c["kind"] == "support"]
    n = len(ev.core_fields)
    lines.append(f"- Its record mentions {service.label.lower()} in {n} field{'s' if n != 1 else ''}:")
    lines += [f'    - {c["field"]}: “{c["text"]}”' for c in core]
    if support:
        lines.append("- Related specialties/equipment: " + "; ".join(f'“{c["text"]}”' for c in support[:4]))
    if ev.specific:
        lines.append("- The claim includes concrete detail (counts, capacity or equipment brand), "
                     "which is harder to get wrong than a generic list entry.")
    where = {"exact": "using the facility's own coordinates",
             "city centre": ("measured from its stated city's centre, because its coordinates conflict with it"
                             if any("contradict" in c for c in row["caveats"])
                             else "measured from its city centre (no usable coordinates)"),
             "PIN area": "measured from its PIN area (no usable coordinates)",
             "district centre": "measured from its district centre",
             "conflicting coordinates": "using coordinates we could not confirm"}[row["location_quality"]]
    lines.append(f"- **{_km(row['distance_km'])}** from {loc.label}, {where}.")

    lines.append(f"\n**How sure are we? {row['confidence_label']}** — evidence {row['evidence_score']:.2f} "
                 f"× trust {row['trust']:.2f} = {row['confidence']:.2f}")
    for mult, reason in factors:
        lines.append(f"- −{(1 - mult) * 100:.0f}%: {reason}")
    if not factors:
        lines.append("- No red flags: location is consistent and the record looks like a single facility.")
    if row["unknowns"]:
        lines.append(f"- Not in the data: {', '.join(row['unknowns'])}.")
    if row["duplicates"]:
        lines.append(f"- {row['duplicates']} other record(s) in the dataset appear to be this same facility.")
    if row["sources"]:
        lines.append("\n**Sources:** " + " · ".join(row["sources"][:3]))
    return "\n".join(lines)


def method_markdown(service: Service | None = None) -> str:
    """Plain-language description of HOW results are produced, generated from the live constants."""
    weights = ", ".join(f"{FIELD_LABELS[f]} {w:.2f}" for f, w in FIELD_WEIGHTS.items())
    penalties = "\n".join(f"  - ×{m:.2f} if {reason}" for m, reason in TRUST.values())
    labels = ", ".join(f"{label} ≥ {cut:.2f}" for cut, label in LABELS if cut > 0)
    svc = ""
    if service is not None and not service.key.startswith("custom:"):
        svc = (f"\n\n**For {service.label}** we count these as direct mentions: {', '.join(service.core)}. "
               f"These only corroborate: {', '.join(service.support) or 'none'}. "
               f"Distance scale: {service.travel_km:.0f} km.")
    return f"""**How we decide**

1. **Find claims.** We search each facility's procedures, equipment, capabilities, name, description and
   specialties for words that mean the service (including Indian terms like LSCS, SNCU, CTVS) and for
   related words (specialty, equipment, staff). Text saying the service is unavailable, planned or referred
   elsewhere is not counted. Each match is kept as a quote, so every claim can be checked.
2. **Score the evidence (0–1).** Each field that names the service counts as a separate witness with weight
   {weights}. A field with only related words counts at {SUPPORT_STRENGTH:.0%} of its weight, and concrete
   detail (counts, bed numbers, equipment brands) adds {SPECIFIC_DETAIL_WEIGHT:.2f}. Combined as
   1 − ∏(1 − weight), so being mentioned consistently in several places matters more than one mention.
3. **Check whether we can trust the record.** The evidence score is multiplied by:
{penalties}
4. **Confidence** = evidence × trust. Labels: {labels}, otherwise Low.
5. **Rank** by confidence × proximity, where proximity = e^(−km ÷ distance scale). The distance scale
   depends on the service: shorter for emergencies (C-section, trauma), longer for planned care (cardiac
   surgery, cancer).

**Trade-offs we made on purpose:** a well-documented facility a bit further away can outrank a closer one
whose claim is weak, so we always tell you about the nearest facility that mentions the service too.
Duplicate records of the same facility are collapsed. We never fill in missing data. If something isn't in the
record, we say so.{svc}"""


def evidence_table(finder: CareFinder, services=None) -> pd.DataFrame:
    """facility × service evidence for every facility with a direct mention (for Delta / Genie)."""
    rows = []
    for service in (services or SERVICES.values()):
        for rec, ev in zip(finder._records, finder.evidence_for(service)):
            if not ev.has_core:
                continue
            factors = finder.trust_factors(rec, service, ev)
            trust = math.prod(m for m, _ in factors)
            rows.append({
                "facility_id": rec["id"], "facility_name": rec["name"], "city": rec["city"], "state": rec["state"],
                "service": service.key, "service_label": service.label, "evidence_score": ev.score,
                "trust": round(trust, 3), "confidence": round(ev.score * trust, 3),
                "confidence_label": confidence_label(ev.score * trust),
                "evidence_fields": ", ".join(FIELD_LABELS[f] for f in ev.core_fields),
                "citations": json.dumps([{"field": FIELD_LABELS[h.field], "kind": h.kind, "text": h.snippet}
                                         for h in ev.hits], ensure_ascii=False),
                "caveats": " | ".join(reason for _, reason in factors),
                "lat": rec["loc_lat"], "lon": rec["loc_lon"], "location_quality": rec["loc_quality"],
            })
    return pd.DataFrame(rows)
