"""Facility-name helpers: which words identify a facility, and does a sentence talk about a different one?

Many records were assembled from directory pages and articles, so a claim like
"Madras Medical Mission, Chennai is listed as a referral hospital" can sit inside another hospital's record.
Such claims describe a different facility and must not count as evidence for this one.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

GENERIC = {
    "hospital", "hospitals", "institute", "institutes", "medical", "college", "centre", "center", "centres", "clinic",
    "clinics", "nursing", "home", "multispeciality", "multispecialty", "multi", "speciality", "specialty",
    "specialities", "super", "superspeciality", "superspecialty", "research", "care", "health", "healthcare", "the",
    "of", "and", "pvt", "ltd", "private", "limited", "sciences", "science", "trust", "foundation", "mission", "general",
    "government", "govt", "district", "civil", "community", "primary", "sub", "divisional", "city", "new", "sri",
    "shri", "shree", "st", "dr", "saint", "for", "in", "at", "a", "an", "&", "unit", "department", "dept", "services",
    "society", "charitable", "group", "chain", "branch", "india", "indian", "national", "state",
}
_SUFFIX = (r"(?:Hospitals?|Institute(?:\s+of\s+[A-Z][\w]*(?:\s+[A-Z][\w]*)*)?|Medical College|Medical Cent(?:re|er)|"
           r"Nursing Home|Clinic|Healthcare|Health Care|Mission|Medicity|Infirmary)")
_MENTION = re.compile(rf"((?:[A-Z][A-Za-z.&'’-]*\s+){{1,5}}{_SUFFIX})")


def tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in GENERIC and not w.isdigit()}


def other_facility(text: str, own: set[str]) -> str | None:
    """Return the name of a *different* facility the text talks about, or None.

    Same facility = one name's distinctive words contain the other's. "Fortis Memorial Research Institute"
    inside "Fortis Hospital Anandapur" counts as different (another branch of the chain).
    """
    if not own:
        return None
    for m in _MENTION.finditer(text):
        mention = m.group(1).strip()
        t = tokens(mention)
        if not t:
            continue
        if t <= own or own <= t:
            continue
        return mention
    return None


def own_website(name: str | None, urls) -> str | None:
    """First source/website whose domain contains a distinctive word of the facility name."""
    words = [w for w in tokens(name) if len(w) >= 4]
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
