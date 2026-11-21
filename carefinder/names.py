"""Facility-name helpers: which words identify a facility, and does a sentence talk about a different one?

Many records were assembled from directory pages and articles, so a claim like
"Madras Medical Mission, Chennai is listed as a referral hospital" can sit inside another hospital's record.
Such claims describe a different facility and must not count as evidence for this one.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

GENERIC = set("""
hospital hospitals institute institutes medical college centre center centres clinic clinics nursing home homes
multispeciality multispecialty multi poly polyclinic speciality specialty specialities super superspeciality
superspecialty research care health healthcare the of and pvt ltd private limited sciences science trust foundation
mission general government govt district civil community primary sub divisional city new sri shri shree smt st dr
saint for in at an unit department dept services society charitable group chain branch india indian national state
top best leading famous popular renowned reputed associated affiliated partner para operates operated runs run
provides offers has have is its our their this that other nearby near opposite male female women womens woman men
mens children childrens child kids mother practo practos justdial rated recommended trusted listed
urology oncology radiation cancer heart cardiac cardiology eye eyes dental dentist ent ortho orthopaedic orthopedic
bone joint kidney renal neuro neurology gastro liver skin hair cosmetic laser ivf fertility gynaec gynae maternity
surgical surgery diagnostic diagnostics imaging scan scans lab labs pathology ayurvedic ayurveda homeopathy
homoeopathic physiotherapy rehab rehabilitation dialysis emergency trauma critical accident speciality
network hospitals spine pediatric paediatric laparoscopy oriented skill training
""".split())
_SUFFIX = (r"(?:Hospitals?|Institute(?:\s+of\s+[A-Z][\w]*(?:\s+[A-Z][\w]*)*)?|Medical College|Medical Cent(?:re|er)|"
           r"Nursing Home|Clinic|Healthcare|Health Care|Mission|Medicity|Infirmary)")
_MENTION = re.compile(rf"((?:[A-Z][A-Za-z.&'’-]*\s+){{1,5}}{_SUFFIX})")
_LANDMARK = re.compile(r"\b(near|opp|opposite|behind|beside|next to|adjacent to|in front of|close to|landmark|"
                       r"road|marg|chowk|lane|street)\W*$", re.IGNORECASE)


def tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in GENERIC and not w.isdigit()}


def _covered(a: set[str], b: set[str]) -> bool:
    """Every word of a matches a word of b, allowing spelling variants (Dhanvantari / Dhanvatri)."""
    return all(any(x == y or (len(x) >= 4 and len(y) >= 4 and SequenceMatcher(None, x, y).ratio() >= 0.8)
                   for y in b) for x in a)


def other_facility(text: str, own: set[str]) -> str | None:
    """Return the name of a *different* facility the text talks about, or None.

    Same facility = one name's distinctive words cover the other's. "Fortis Memorial Research Institute"
    inside "Fortis Hospital Anandapur" counts as different (another branch of the chain). Landmarks in
    addresses ("Opposite City Hospital") and listing-site phrases ("Top Clinic") are ignored.
    """
    if not own:
        return None
    for m in _MENTION.finditer(text):
        mention = m.group(1).strip()
        t = tokens(mention)
        if not t or _LANDMARK.search(text[max(0, m.start() - 30):m.start()]):
            continue
        if _covered(t, own) or _covered(own, t):
            continue
        return mention
    return None


def own_website(name: str | None, urls) -> str | None:
    """First source/website whose domain contains a distinctive word of the facility name."""
    words = [w for w in re.findall(r"[a-z0-9]+", (name or "").lower()) if len(w) >= 4 and w not in {
        "hospital", "hospitals", "clinic", "clinics", "centre", "center", "medical", "health", "care", "multi",
        "speciality", "specialty", "super", "nursing", "home", "institute", "research", "dental"}]
    if not words:
        return None
    for url in urls or []:
        try:
            host = urlparse(url if "//" in url else f"//{url}").netloc.lower()
        except ValueError:
            continue
        host = host.removeprefix("www.")
        if not host or any(s in host for s in ("facebook.", "instagram.", "justdial.", "practo.", "google.",
                                               "wikipedia.", "linkedin.", "twitter.", "x.com", "youtube.")):
            continue
        if any(w in host for w in words):
            return host
    return None
