"""Find and score the evidence that a facility offers a service, keeping the exact text as a citation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from .names import other_facility, tokens
from .taxonomy import Service, normalize

# How much a single field counts as evidence. They are combined like independent witnesses
# (noisy-OR): 1 - prod(1 - weight), so corroboration across fields raises the score.
FIELD_WEIGHTS: dict[str, float] = {
    "procedure": 0.60,
    "equipment": 0.60,
    "capability": 0.55,
    "name": 0.50,
    "description": 0.45,
    "specialties": 0.40,
}
CORE_STRENGTH = 1.0      # the field names the service itself
LIST_STRENGTH = 0.6      # ...but only inside a long laundry list ("Specialities: A, B, C, D, ...")
SUPPORT_STRENGTH = 0.35  # the field only names related specialty/equipment/staff
SPECIFIC_DETAIL_WEIGHT = 0.25  # a core claim with concrete detail (counts, brands, capacity)

FIELD_LABELS = {
    "procedure": "Procedures", "equipment": "Equipment", "capability": "Capabilities",
    "name": "Facility name", "description": "Description", "specialties": "Specialties",
}

_NEG_WORDS = {"no", "not", "without", "lack", "lacks", "lacking", "unavailable", "planned", "proposed",
              "upcoming", "awaited", "nil"}
_NEG_AFTER = ("not available", "coming soon", "under construction", "not functional", "non functional",
              "planned", "proposed", "unavailable", "is not", "are not", "awaited")
# "dialysis consumables", "MRI contrast supplies": a product being sold, not a service being offered.
_PRODUCT_AFTER = {"consumable", "consumables", "supplies", "supply", "kit", "kits", "products", "disposables",
                  "accessories", "spares", "dealer", "dealers", "distributor", "distributors"}
_REFER = re.compile(r"\b(?:refer|referred|refers|referral)\s+(?:\w+\s+){0,2}(?:to|for)\s*$")

_SPECIFIC = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:-\s*)?(?:bed(?:ded)?s?|machines?|units?|slices?|tesla|t|stations?|chairs?|cots?|"
    r"incubators?|warmers?|ventilators?|tables?|theatres?|theaters?)\b"
    r"|\b(?:siemens|philips|fresenius|nipro|b\.? ?braun|toshiba|canon|hitachi|ge healthcare|wipro ge|baxter|"
    r"dr[aä]eger|mindray|medtronic|elekta|varian)\b",
    re.IGNORECASE,
)


@dataclass
class Hit:
    field: str
    term: str
    kind: str  # "core" or "support"
    snippet: str
    negated: bool = False
    listed: bool = False          # only appears inside a long list of services
    other_facility: str | None = None  # the sentence is about this other facility


@dataclass
class Evidence:
    score: float = 0.0
    core_fields: list[str] = field(default_factory=list)
    support_fields: list[str] = field(default_factory=list)
    hits: list[Hit] = field(default_factory=list)
    negated: list[Hit] = field(default_factory=list)
    foreign: list[Hit] = field(default_factory=list)  # mentions that describe a different facility
    specific: bool = False
    listed_only: bool = False  # every direct mention is inside a long list

    @property
    def has_core(self) -> bool:
        return bool(self.core_fields)


def _alternation(terms) -> str:
    normed = sorted({normalize(t) for t in terms if normalize(t)}, key=len, reverse=True)
    return "|".join(re.escape(t) for t in normed)


@lru_cache(maxsize=256)
def _matcher(service: Service) -> re.Pattern:
    parts = [f"(?P<core>{_alternation(service.core)})"]
    if service.support:
        parts.append(f"(?P<support>{_alternation(service.support)})")
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(parts) + r")(?:s|es)?(?![a-z0-9])")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+|\s*[•·]\s*", text) if s and s.strip()]


def _is_negated(unit_norm: str, start: int, end: int) -> bool:
    before = unit_norm[max(0, start - 60):start]
    if set(before.split()[-4:]) & _NEG_WORDS:
        return True
    if _REFER.search(before):
        return True
    after = " ".join(unit_norm[end:end + 60].split()[:5])
    return any(p in after for p in _NEG_AFTER)


def _snippet(text: str, term: str = "", limit: int = 220) -> str:
    """The text, or a window of it centred on the matched term so the quote always shows the match."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    pos = 0
    if term:
        m = re.search(r"[^a-z0-9]+".join(re.escape(w) for w in term.split()), text, re.IGNORECASE)
        pos = m.start() if m else 0
    start = max(0, min(pos - limit // 3, len(text) - limit))
    if start > 0:
        start = text.find(" ", start) + 1 or start
    end = min(len(text), start + limit)
    if end < len(text):
        end = text.rfind(" ", start, end) if text.rfind(" ", start, end) > pos else end
    return ("…" if start > 0 else "") + text[start:end].strip() + ("…" if end < len(text) else "")


def _is_list(text: str) -> bool:
    """A long enumeration of services, where one entry is weaker evidence than a dedicated statement."""
    return text.count(",") + text.count(";") >= 6


def _units(row) -> list[tuple[str, str]]:
    """(field, original text) pairs to search."""
    units: list[tuple[str, str]] = []
    for f in ("procedure", "equipment", "capability", "specialties"):
        for item in row.get(f) or []:
            units.append((f, str(item)))
    if row.get("name"):
        units.append(("name", str(row["name"])))
    if row.get("description"):
        units.extend(("description", s) for s in _sentences(str(row["description"])))
    return units


def score_evidence(row, service: Service, max_hits_per_field: int = 2) -> Evidence:
    pattern = _matcher(service)
    ev = Evidence()
    core_strength: dict[str, float] = {}
    support_fields: set[str] = set()
    found: list[Hit] = []
    own = tokens(row.get("name"))

    for fld, text in _units(row):
        norm = normalize(text)
        best: Hit | None = None  # one citation per unit: its strongest non-negated mention
        other = None
        for m in pattern.finditer(norm):
            kind = "core" if m.group("core") else "support"
            if set(norm[m.end():m.end() + 40].split()[:2]) & _PRODUCT_AFTER:
                continue
            hit = Hit(fld, m.group(kind), kind, _snippet(text, m.group(kind)))
            if _is_negated(norm, m.start(), m.end()):
                hit.negated = True
                ev.negated.append(hit)
                continue
            if fld != "name":
                other = other if other is not None else (other_facility(text, own) or "")
                if other:
                    hit.other_facility = other
                    if kind == "core":
                        ev.foreign.append(hit)
                    continue
            if kind == "core":
                hit.listed = _is_list(text)
                strength = LIST_STRENGTH if hit.listed else CORE_STRENGTH
                core_strength[fld] = max(core_strength.get(fld, 0.0), strength)
                ev.specific = ev.specific or (not hit.listed and bool(_SPECIFIC.search(text)))
                if best is None or best.kind != "core" or (best.listed and not hit.listed):
                    best = hit
            else:
                support_fields.add(fld)
                best = best or hit
        if best:
            found.append(best)
    core_fields = set(core_strength)

    order = list(FIELD_WEIGHTS)
    found.sort(key=lambda h: (h.kind != "core", h.listed, order.index(h.field)))
    per_field: dict[tuple[str, str], int] = {}
    for h in found:
        key = (h.field, h.kind)
        if per_field.get(key, 0) < max_hits_per_field:
            per_field[key] = per_field.get(key, 0) + 1
            ev.hits.append(h)

    support_fields -= core_fields
    ev.core_fields = [f for f in FIELD_WEIGHTS if f in core_fields]
    ev.support_fields = [f for f in FIELD_WEIGHTS if f in support_fields]
    ev.listed_only = bool(core_strength) and max(core_strength.values()) < CORE_STRENGTH

    remaining = 1.0
    for f, w in FIELD_WEIGHTS.items():
        if f in core_fields:
            remaining *= 1 - w * core_strength[f]
        elif f in support_fields:
            remaining *= 1 - w * SUPPORT_STRENGTH
    if ev.specific:
        remaining *= 1 - SPECIFIC_DETAIL_WEIGHT
    ev.score = round(1 - remaining, 3)
    return ev
