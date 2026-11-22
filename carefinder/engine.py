"""Search: service + location -> ranked facilities, each with cited evidence and an explanation."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import access
from .evidence import FIELD_LABELS, FIELD_WEIGHTS, Evidence, score_evidence
from .geo import PinDirectory, ResolvedLocation, haversine_km
from .model import COVARIATE_TEXT, COVARIATES, FIELDS, INDICATORS, LatentClassModel, fit
from .quality import assess
from .schema import detect_columns, standardize
from .taxonomy import SERVICES, Service, ad_hoc_service, find_service

# Location problems no longer lower confidence (a wrong pin does not make a claim false); they widen the
# uncertainty of the distance instead (access.py). These texts explain why.
LOCATION_NOTES = {
    "coords_conflict": "its coordinates contradict its city and PIN code, and we could not resolve which is right",
    "coords_fixed": "its coordinates contradicted its address, so we placed it by its address instead",
    "address_inconsistent": "its city and PIN code disagree",
    "shared coordinates": "its coordinates are shared with other facilities (probably a city-centre placeholder)",
    "city centre": "it has no usable coordinates, so it is placed at its city centre",
    "PIN area": "it has no usable coordinates, so it is placed at its PIN area",
    "district centre": "it has no usable coordinates, so it is placed at its district centre",
}
# Labels on the posterior probability that the facility offers the service.
LABELS = ((0.80, "High"), (0.50, "Medium"), (0.0, "Low"))


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
    model: LatentClassModel | None = None

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
                 pin_directory: pd.DataFrame | None = None, n_boot: int = 100):
        """raw: facility table. pin_directory: optional India Post PIN directory (one row per post office)."""
        self.mapping = detect_columns(raw.columns, column_overrides)
        self.pin_dir = PinDirectory(pin_directory) if pin_directory is not None else None
        self.facilities, self.gazetteer = assess(standardize(raw, self.mapping), self.pin_dir)
        self._records = self.facilities.to_dict("records")
        self._evidence: dict[str, list[Evidence]] = {}
        self._models: dict[str, LatentClassModel] = {}
        self._xz: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._scores: dict[str, dict[str, np.ndarray]] = {}
        self.n_boot = n_boot

    # ---- evidence -------------------------------------------------------------------------
    def evidence_for(self, service: Service) -> list[Evidence]:
        if service.key not in self._evidence:
            self._evidence[service.key] = [score_evidence(r, service) for r in self._records]
        return self._evidence[service.key]

    def record_flags(self, row: dict, service: Service, ev: Evidence) -> list[str]:
        """Record-quality covariates for the evidence model (their effects are learned, not set by hand)."""
        kind = row["kind"]
        flags = {
            "clinic_for_hospital_service": kind in ("clinic", "diagnostic") and service.needs_hospital,
            "pharmacy_or_dental": kind == "pharmacy" or (kind == "dental" and service.key != "dental"),
            "merged_record": bool(row["merge_reasons"]),
            "corrupted_row": bool(row["corrupted"]),
            "mentions_other_facilities": bool(ev.foreign),
            "no_source_urls": not row["source_urls"],
            "no_own_website": bool(row["source_urls"]) and not row["own_site"],
            "too_few_beds": bool(service.min_beds and row["capacity"] is not None and row["capacity"] < service.min_beds),
        }
        return [c for c in COVARIATES if flags[c]]

    def location_notes(self, row: dict) -> list[str]:
        notes = []
        if row["location_issue"] in LOCATION_NOTES:
            notes.append(LOCATION_NOTES[row["location_issue"]] + (f" ({row['location_detail']})" if row["location_detail"] else ""))
        elif row["loc_quality"] in LOCATION_NOTES:
            notes.append(LOCATION_NOTES[row["loc_quality"]])
        if row["pin_state_mismatch"]:
            notes.append(f"its PIN code belongs to a different state than the one listed ({row['postcode']} vs {row['state']})")
        return notes

    def location_sd(self, row: dict) -> float:
        sd = access.LOCATION_SD_KM.get(row["loc_quality"], 5.0)
        if row["location_issue"] == "coords_fixed":
            sd = max(sd, 8.0)
        elif row["location_issue"] in ("coords_conflict", "address_inconsistent"):
            sd = max(sd, 20.0)
        return sd

    def features(self, service: Service) -> tuple[np.ndarray, np.ndarray]:
        """X: what each field says (0 none, 1 listed, 2 dedicated) + 3 signals; Z: record-quality flags."""
        evs = self.evidence_for(service)
        X = np.zeros((len(evs), len(INDICATORS)), dtype=int)
        Z = np.zeros((len(evs), len(COVARIATES)), dtype=float)
        for i, (rec, ev) in enumerate(zip(self._records, evs)):
            for j, fld in enumerate(FIELDS):
                st = ev.field_strength.get(fld)
                X[i, j] = 0 if st is None else (2 if st >= 1.0 else 1)
            X[i, len(FIELDS)] = int(bool(ev.support_fields) and not ev.core_fields)
            X[i, len(FIELDS) + 1] = int(any(h.kind == "core" for h in ev.negated))
            X[i, len(FIELDS) + 2] = int(ev.specific)
            for c in self.record_flags(rec, service, ev):
                Z[i, COVARIATES.index(c)] = 1.0
        return X, Z

    def model_for(self, service: Service) -> LatentClassModel:
        if service.key not in self._models:
            X, Z = self.features(service)
            self._models[service.key] = fit(X, Z, n_boot=self.n_boot)
            self._xz[service.key] = (X, Z)
        return self._models[service.key]

    def scores_for(self, service: Service) -> dict[str, np.ndarray]:
        """Per record: p (posterior it offers the service), lo/hi (90% bootstrap interval), p_text (text only)."""
        if service.key not in self._scores:
            m = self.model_for(service)
            X, Z = self._xz[service.key]
            lo, hi = m.interval(X, Z)
            self._scores[service.key] = {"p": m.posterior(X, Z), "lo": lo, "hi": hi, "p_text": m.evidence_only(X)}
        return self._scores[service.key]

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
        sc = self.scores_for(service)
        hours, basis = access.window(service.key)
        dist = haversine_km(np.array([r["loc_lat"] for r in rows], dtype=float),
                            np.array([r["loc_lon"] for r in rows], dtype=float), loc.lat, loc.lon)
        loc_sd = np.array([math.hypot(self.location_sd(r), loc.uncertainty_km or 0.0) for r in rows])
        reach = access.p_reach(dist, hours, loc_sd)
        cand = pd.DataFrame({"i": idx, "distance_km": np.round(dist, 1), "confidence": sc["p"][idx],
                             "lo": sc["lo"][idx], "hi": sc["hi"][idx], "p_text": sc["p_text"][idx],
                             "access": reach, "loc_sd": loc_sd})
        # Expected value of sending the patient there: P(it offers the service) × P(they arrive in time).
        cand["rank_score"] = cand["confidence"] * cand["access"]
        cand["dup_group"] = [self._records[i]["dup_group"] for i in cand["i"]]

        limit = max_km or max(3 * access.reach_km(hours), 100)
        within = cand[cand["distance_km"] <= limit]
        if within.empty:
            notes.append(f"No facility within {limit:.0f} km claims {service.label.lower()}. "
                         "Showing the nearest ones further away.")
            within = cand.nsmallest(top_k * 3, "distance_km")
        ranked = within.sort_values("rank_score", ascending=False).drop_duplicates("dup_group")
        top = ranked.head(top_k)
        # Always show the closest facility with strong evidence that the patient can likely reach in time.
        strong = ranked[(ranked["confidence"] >= LABELS[0][0]) & (ranked["access"] >= 0.5)]
        if len(strong) and len(top) >= top_k:
            closest_strong = strong.nsmallest(1, "distance_km")
            if int(closest_strong["i"].iloc[0]) not in set(top["i"].astype(int)):
                top = pd.concat([top.iloc[:-1], closest_strong]).sort_values("rank_score", ascending=False)
                r = self._records[int(closest_strong["i"].iloc[0])]
                notes.append(f"{r['name']} is included because it is the closest facility with strong evidence "
                             f"({_km(float(closest_strong['distance_km'].iloc[0]))}).")
        top = top.reset_index(drop=True)

        nearest = cand.nsmallest(1, "distance_km").iloc[0]
        if int(nearest["i"]) not in set(top["i"].astype(int)):
            r = self._records[int(nearest["i"])]
            ev = evs[int(nearest["i"])]
            flags = self.record_flags(r, service, ev)
            notes.append(
                f"The nearest facility that mentions {service.label.lower()} is {r['name']} "
                f"({_km(nearest['distance_km'])}), but it ranks lower: {confidence_label(nearest['confidence'])} "
                f"confidence, {nearest['confidence']:.2f} ({_evidence_summary(ev)}"
                + (f"; {COVARIATE_TEXT[flags[0]]}" if flags else "") + ").")
        if (top["confidence"].map(confidence_label) == "Low").any():
            notes.append("Results marked Low are weakly supported claims. Call ahead to confirm before travelling.")

        result.model = self.model_for(service)
        result.results = pd.DataFrame([self._result_row(n + 1, t, service, loc) for n, t in enumerate(top.to_dict("records"))])
        return result

    def _result_row(self, rank: int, t: dict, service: Service, loc: ResolvedLocation) -> dict:
        i = int(t["i"])
        r = self._records[i]
        ev = self.evidence_for(service)[i]
        model = self.model_for(service)
        odds = model.odds_ratios()
        flags = self.record_flags(r, service, ev)
        hours, basis = access.window(service.key)
        unknowns = [label for key, label in (("capacity", "bed count"), ("num_doctors", "number of doctors"),
                                              ("year_established", "year established")) if r[key] is None]
        if not r["equipment"]:
            unknowns.append("equipment list")
        citations = [{"field": FIELD_LABELS[h.field], "kind": h.kind, "term": h.term, "text": h.snippet,
                      "listed": h.listed} for h in ev.hits]
        sources = list(r["source_urls"])
        if r["own_site"]:
            sources.sort(key=lambda u: r["own_site"] not in u.lower())
        loc_notes = self.location_notes(r)
        penalties = [{"odds": round(odds[c], 2), "pct": round((1 - odds[c]) * 100), "reason": COVARIATE_TEXT[c]}
                     for c in flags if odds[c] < 0.995]  # flags the data says make no difference are not shown
        p, p_text = float(t["confidence"]), float(t["p_text"])
        row = {
            "rank": rank, "id": r["id"], "name": r["name"] or "(unnamed facility)", "kind": r["kind"],
            "address": r["address"], "city": r["city"], "state": r["state"], "postcode": r["postcode"],
            "lat": r["loc_lat"], "lon": r["loc_lon"], "location_quality": r["loc_quality"],
            "distance_km": t["distance_km"], "travel_h": round(access.travel_hours(t["distance_km"]), 2),
            "loc_sd_km": round(float(t["loc_sd"]), 1), "window_h": hours, "window_basis": basis,
            "access": round(float(t["access"]), 3),
            "evidence_score": round(p_text, 3), "trust": round(p / p_text, 3) if p_text > 0 else 1.0,
            "confidence": round(p, 3), "conf_lo": round(float(t["lo"]), 3), "conf_hi": round(float(t["hi"]), 3),
            "confidence_label": confidence_label(p), "rank_score": round(float(t["rank_score"]), 4),
            "evidence_fields": ", ".join(FIELD_LABELS[f] for f in ev.core_fields),
            "citations": citations, "caveats": [p_["reason"] for p_ in penalties] + loc_notes,
            "penalties": penalties, "location_notes": loc_notes,
            "specific": ev.specific, "listed_only": ev.listed_only, "unknowns": unknowns,
            "sources": sources[:5], "own_site": r["own_site"], "duplicates": int(r["dup_count"]),
            "capacity": r["capacity"], "num_doctors": r["num_doctors"], "year_established": r["year_established"],
            "phone": (r["phone"] or [None])[0], "website": (r["website"] or [None])[0],
        }
        row["explanation"] = explain(row, ev, model, service, loc)
        return row


def _km(d: float) -> str:
    return f"{d:.1f} km" if d < 10 else f"{d:.0f} km"


def _evidence_summary(ev: Evidence) -> str:
    if not ev.core_fields:
        return "no direct mention"
    fields = ", ".join(FIELD_LABELS[f].lower() for f in ev.core_fields)
    return f"mentioned only in {fields}" if len(ev.core_fields) == 1 else f"mentioned in {fields}"


def _x(v: float) -> str:
    return f"×{v:.0f}" if v >= 10 else f"×{v:.1f}" if v >= 1 else f"×{v:.2f}"


def explain(row: dict, ev: Evidence, model: LatentClassModel, service: Service, loc: ResolvedLocation) -> str:
    noun = service.label.lower()
    lines = [f"**Why this facility for {noun}?**"]
    core = [c for c in row["citations"] if c["kind"] == "core"]
    support = [c for c in row["citations"] if c["kind"] == "support"]
    n = len(ev.core_fields)
    lines.append(f"- Its record mentions {noun} in {n} field{'s' if n != 1 else ''}:")
    lines += [f'    - {c["field"]}: “{c["text"]}”' + (" _(inside a long list)_" if c.get("listed") else "")
              for c in core[:6]]
    support = sorted((c for c in support if len(c["text"]) <= 160), key=lambda c: len(c["text"]))
    if support:
        lines.append("- Related specialties/equipment: " + "; ".join(f'“{c["text"]}”' for c in support[:3]))
    if row.get("own_site"):
        lines.append(f"- Its sources include the facility's own website ({row['own_site']}).")

    lr = model.likelihood_ratios()
    learned = []
    for f in ev.core_fields:
        kind = "dedicated" if ev.field_strength.get(f, 0) >= 1.0 else "listed"
        learned.append(f"{FIELD_LABELS[f].lower()} ({'a dedicated mention' if kind == 'dedicated' else 'inside a list'}) "
                       f"{_x(lr[f][kind])}")
    if ev.specific:
        learned.append(f"concrete detail {_x(lr['specific']['present'])}")
    lines.append(f"\n**How likely is it that it offers {noun}? {row['confidence_label']}: {row['confidence']:.2f}** "
                 f"(90% interval {row['conf_lo']:.2f}-{row['conf_hi']:.2f})")
    lines.append(f"- Base rate: {model.prior():.0%} of records in this dataset are estimated to offer {noun}. "
                 + ("Learned from the data, each piece of evidence multiplies the odds: " + ", ".join(learned) + "."
                    if learned else ""))
    lines.append(f"- From its text alone: {row['evidence_score']:.2f}.")
    for p_ in row["penalties"]:
        lines.append(f"- Record check: {p_['reason']}: odds {_x(p_['odds'])} (learned).")
    if not row["penalties"]:
        lines.append("- No record-quality flags.")

    lines.append(f"\n**Can the patient get there in time?** {_km(row['distance_km'])} straight-line ≈ "
                 f"{row['travel_h'] * 60:.0f} min by road ({access.DETOUR}× detour at {access.SPEED_KMH:.0f} km/h). "
                 f"Chance of arriving within {row['window_h']:.0f} h: **{row['access']:.0%}** ({row['window_basis']}).")
    if row["location_notes"]:
        lines.append(f"- Location uncertain by about ±{row['loc_sd_km']:.0f} km: " + "; ".join(row["location_notes"]) + ".")
    if row["unknowns"]:
        lines.append(f"- Not in the data: {', '.join(row['unknowns'])}.")
    if row["duplicates"]:
        lines.append(f"- {row['duplicates']} other record(s) in the dataset appear to be this same facility.")
    if row["sources"]:
        lines.append("\n**Sources:** " + " · ".join(row["sources"][:3]))
    return "\n".join(lines)


def method_markdown(service: Service | None = None, model: LatentClassModel | None = None) -> str:
    """How results are produced, generated from the live constants and (if given) the service's fitted model."""
    labels = ", ".join(f"{label} ≥ {cut:.2f}" for cut, label in LABELS if cut > 0)
    out = f"""**How we decide**

1. **Find claims.** We search each facility's procedures, equipment, capabilities, name, description and
   specialties for words that mean the service (including Indian terms like LSCS, SNCU, CTVS, PMNDP), and for
   related words. Mentions negated nearby ("not available", "coming soon", "referred to") are flagged, in the
   spirit of the NegEx rules (Chapman et al. 2001), and sentences about a *different* hospital are dropped.
   Every match is kept as a quote.
2. **Learn how much each kind of evidence is worth.** There is no answer key, so the weights cannot be trained
   the usual way. We fit a latent class model with EM (Dawid & Skene 1979; the "label model" behind Snorkel):
   whether a facility offers the service is a hidden yes/no, and each field is a noisy witness with its own
   true-positive and false-positive rate. Those rates are estimated from how often the fields *agree with each
   other* across all 10,088 records. A field whose mentions are usually corroborated earns a large likelihood
   ratio; one whose mentions usually stand alone earns a small one. Fields scraped from one page are not truly
   independent, so repeated mentions are discounted by the Kish design effect 1 + (k-1)·ρ, where ρ is the
   correlation between fields within the "offers it" class, estimated from the fitted model. Signals whose
   direction we know are constrained: "not available" can never raise the odds, concrete detail can never lower
   them.
3. **Record checks are learned too.** Flags such as "looks like a clinic", "may merge several hospitals" or
   "no source URL" enter as covariates on the prior (latent class regression); EM estimates how much each one
   changes the odds. Location problems are *not* treated as evidence against the claim: they widen the
   uncertainty of the distance instead.
4. **Confidence** = P(offers the service | its record), by Bayes' rule, with a 90% interval from a bootstrap
   (refit on resampled facilities 100 times). Labels: {labels}, otherwise Low.
5. **Can the patient get there in time?** Road time = straight-line km × {access.DETOUR} (detour) ÷ speed, with
   speed log-normal around {access.SPEED_KMH:.0f} km/h (log-sd {access.SPEED_SD_LOG}) and location uncertainty
   added. We compute the probability of arriving within the service's clinical window: 2 h for emergency
   obstetric and surgical care (Lancet Commission on Global Surgery), 1 h for trauma, 1 h one way for dialysis
   (DOPPS), longer for planned care.
6. **Rank** by expected value: P(offers it) × P(arrives in time). We always also show the nearest facility
   that mentions the service, and why it ranked where it did.

**Assumptions we state openly:** fields are treated as independent witnesses given the truth (text scraped from
one web page can share errors); "offers the service" means the record consistently says so, not an on-site
check; the detour factor and speed are national averages. Duplicate records are collapsed and missing data is
never filled in."""
    if service is not None and model is not None and not service.key.startswith("custom:"):
        lr = model.likelihood_ratios()
        rows = "\n".join(f"| {FIELD_LABELS[f]} | {_x(lr[f]['dedicated'])} | {_x(lr[f]['listed'])} |" for f in FIELDS)
        ors = "\n".join(f"| {COVARIATE_TEXT[c]} | {_x(v)} |" for c, v in model.odds_ratios().items())
        hours, basis = access.window(service.key)
        out += f"""

**Learned for {service.label}** (EM on {model.n:,} records, base rate {model.prior():.1%}, within-class field
correlation ρ = {model.rho:.2f}, so 3 agreeing fields count as {3 / (1 + 2 * model.rho):.1f} independent ones):

| Field | Dedicated mention | Only inside a long list |
|---|---|---|
{rows}
| Related words only | {_x(lr['support_only']['present'])} | |
| Text says unavailable / referred | {_x(lr['negated']['present'])} | |
| Concrete detail (counts, brands) | {_x(lr['specific']['present'])} | |

| Record check | Odds multiplier |
|---|---|
{ors}

Time window: {hours:.0f} h ({basis}); reachable distance at 50%: {access.reach_km(hours):.0f} km."""
    return out


def evidence_table(finder: CareFinder, services=None) -> pd.DataFrame:
    """facility × service evidence for every facility with a direct mention (for Delta / Genie)."""
    rows = []
    for service in (services or SERVICES.values()):
        sc = finder.scores_for(service)
        odds = finder.model_for(service).odds_ratios()
        for i, (rec, ev) in enumerate(zip(finder._records, finder.evidence_for(service))):
            if not ev.has_core:
                continue
            flags = finder.record_flags(rec, service, ev)
            state = rec["state_n"] or (rec["state"] or "").lower() or None
            p, p_text = float(sc["p"][i]), float(sc["p_text"][i])
            rows.append({
                "facility_id": rec["id"], "facility_name": rec["name"], "address": rec["address"],
                "city": rec["city"], "district": rec["district_n"], "state": state, "postcode": rec["postcode"],
                "service": service.key, "service_label": service.label, "evidence_score": round(p_text, 3),
                "trust": round(p / p_text, 3) if p_text > 0 else 1.0, "confidence": round(p, 3),
                "conf_lo": round(float(sc["lo"][i]), 3), "conf_hi": round(float(sc["hi"][i]), 3),
                "confidence_label": confidence_label(p),
                "evidence_fields": ", ".join(FIELD_LABELS[f] for f in ev.core_fields),
                "citations": json.dumps([{"field": FIELD_LABELS[h.field], "kind": h.kind, "text": h.snippet}
                                         for h in ev.hits], ensure_ascii=False),
                "top_quote": next((h.snippet for h in ev.hits if h.kind == "core"), None),
                "caveats": " | ".join([f"{COVARIATE_TEXT[c]} (odds {_x(odds[c])})" for c in flags if odds[c] < 0.995]
                                      + finder.location_notes(rec)),
                "lat": rec["loc_lat"], "lon": rec["loc_lon"], "location_quality": rec["loc_quality"],
                "loc_sd_km": finder.location_sd(rec),
                "phone": (rec["phone"] or [None])[0], "website": rec["own_site"] or (rec["website"] or [None])[0],
                "sources": " ".join(list(rec["source_urls"])[:3]),
            })
    return pd.DataFrame(rows)


def places_table(finder: CareFinder) -> pd.DataFrame:
    """Every place name we can resolve (city, district, post office, PIN, state) -> coordinates, for SQL/Genie."""
    from .geo import CITY_ALIASES
    g, pd_ = finder.gazetteer, finder.pin_dir
    rows = []

    def add(name, kind, p, state=None):
        rows.append({"name": name, "label": p.label, "kind": kind, "state": state or p.state,
                     "lat": round(p.lat, 5), "lon": round(p.lon, 5), "n": int(p.n), "spread_km": round(p.spread_km, 1)})

    for city, places in g.by_city.items():
        for p in places:
            add(city, "city", p)
    for alias, target in CITY_ALIASES.items():
        if alias != target:
            for p in g.by_city.get(target, []):
                add(alias, "city", p)
    if pd_ is not None:
        for d, places in pd_.districts.items():
            for p in places:
                add(d, "district", p)
        for pin, p in pd_.pins.items():
            add(pin, "pin", p, state=p.states[0] if p.states else None)
        for office, places in pd_.offices.items():
            for p in places:
                add(office, "post office", p)
    else:
        for d, places in g.by_district.items():
            for p in places:
                add(d, "district", p)
        for pin, p in g.by_pin.items():
            add(pin, "pin", p)
    for s, p in g.by_state.items():
        add(s, "state", p)
    return pd.DataFrame(rows)


def find_care_sql(target: str) -> str:
    """SQL table function with the same ranking as CareFinder.search, for Genie and dashboards."""
    return f"""
CREATE OR REPLACE FUNCTION {target}.find_care(service_name STRING, place STRING)
RETURNS TABLE (option_rank INT, facility_name STRING, address STRING, city STRING, district STRING, state STRING,
               distance_km DOUBLE, p_arrive_in_time DOUBLE, confidence_label STRING, confidence DOUBLE,
               conf_lo DOUBLE, conf_hi DOUBLE, evidence_score DOUBLE, trust DOUBLE,
               evidence_fields STRING, top_quote STRING, citations STRING, caveats STRING, location_quality STRING,
               phone STRING, website STRING)
COMMENT 'Best facilities for a service near a place (city, district, village/post office, 6-digit PIN, or state; add ", <state>" to disambiguate). Ranked by confidence (learned probability the facility offers the service) x p_arrive_in_time (probability of arriving within the service time window), the same rule as the CareFinder app. Always quote top_quote/citations as evidence and report conf_lo-conf_hi and caveats as uncertainty.'
RETURN
  WITH q AS (
    SELECT lower(trim(split(place, ',')[0])) AS p,
           lower(trim(try_element_at(split(place, ','), 2))) AS st
  ),
  loc AS (
    SELECT pl.lat, pl.lon FROM {target}.places pl CROSS JOIN q
    WHERE pl.name = q.p
    ORDER BY CASE WHEN q.st IS NOT NULL AND pl.state = q.st THEN 0 ELSE 1 END,
             CASE pl.kind WHEN 'pin' THEN 0 WHEN 'city' THEN 1 WHEN 'district' THEN 2 WHEN 'post office' THEN 3 ELSE 4 END,
             pl.n DESC
    LIMIT 1
  ),
  svc AS (
    SELECT service, window_h FROM {target}.services
    WHERE lower(label) = lower(trim(service_name)) OR service = lower(trim(service_name))
       OR lower(label) LIKE concat('%', lower(trim(service_name)), '%')
       OR lower(core_terms) LIKE concat('%', lower(trim(service_name)), '%')
    ORDER BY CASE WHEN lower(label) = lower(trim(service_name)) OR service = lower(trim(service_name)) THEN 0 ELSE 1 END
    LIMIT 1
  ),
  c AS (
    SELECT e.*, svc.window_h,
           2 * 6371 * asin(sqrt(pow(sin(radians(e.lat - loc.lat) / 2), 2)
             + cos(radians(loc.lat)) * cos(radians(e.lat)) * pow(sin(radians(e.lon - loc.lon) / 2), 2))) AS d
    FROM {target}.facility_service_evidence e CROSS JOIN loc CROSS JOIN svc
    WHERE e.service = svc.service AND e.lat IS NOT NULL
  ),
  a AS (
    SELECT c.*, 1 / (1 + exp(-1.702 * (ln(window_h) - ln({access.DETOUR} * greatest(d, 0.05) / {access.SPEED_KMH}))
             / sqrt(pow({access.SPEED_SD_LOG}, 2) + pow(loc_sd_km / greatest(d, loc_sd_km + 1e-9), 2)))) AS reach
    FROM c
  )
  SELECT CAST(row_number() OVER (ORDER BY confidence * reach DESC) AS INT) AS option_rank,
         facility_name, address, city, district, state, round(d, 1) AS distance_km, round(reach, 3) AS p_arrive_in_time,
         confidence_label, confidence, conf_lo, conf_hi, evidence_score, trust, evidence_fields, top_quote, citations,
         caveats, location_quality, phone, website
  FROM a
  ORDER BY option_rank
  LIMIT 10
"""
