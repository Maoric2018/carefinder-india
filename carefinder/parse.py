"""Turn messy scraped cells into clean Python values."""

from __future__ import annotations

import ast
import json
import math
import re

_NULLS = {"", "null", "none", "nan", "n/a", "na", "[]", "{}", "-", "unknown"}


def _is_missing(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def to_text(value) -> str | None:
    if _is_missing(value):
        return None
    s = str(value).strip()
    return None if s.lower() in _NULLS else s


def to_list(value) -> list[str]:
    """Handle real arrays, JSON strings, Python-repr strings and delimited text."""
    if _is_missing(value):
        return []
    if isinstance(value, str):
        s = value.strip()
        if s.lower() in _NULLS:
            return []
        items = None
        if s.startswith("[") and s.endswith("]"):
            for loader in (json.loads, ast.literal_eval):
                try:
                    parsed = loader(s)
                    if isinstance(parsed, (list, tuple)):
                        items = list(parsed)
                        break
                except Exception:
                    pass
            if items is None:
                items = [p for p in re.split(r'",\s*"|\',\s*\'', s.strip("[]"))]
        elif "\n" in s or ";" in s or "|" in s:
            items = re.split(r"[\n;|]+", s)
        else:
            items = [s]
    elif isinstance(value, dict):
        items = [f"{k}: {v}" for k, v in value.items()]
    elif hasattr(value, "__iter__") and not isinstance(value, bytes):
        items = list(value)
    else:
        items = [value]

    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if _is_missing(item):
            continue
        text = str(item).strip().strip("\"'").strip()
        if text.lower() in _NULLS:
            continue
        key = text.lower()
        if key not in seen:
            seen.add(key)
            out.append(text)
    return out


def to_float(value) -> float | None:
    if _is_missing(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    m = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    return float(m.group()) if m else None


def to_year(value) -> int | None:
    if _is_missing(value):
        return None
    m = re.search(r"\b(1[89]\d{2}|20\d{2})\b", str(value))
    return int(m.group()) if m else None


def clean_postcode(value) -> str | None:
    """Indian PIN codes are 6 digits and never start with 0."""
    if _is_missing(value):
        return None
    s = str(value)
    if isinstance(value, float):
        s = str(int(value))
    s = re.sub(r"(?<=\d)\s+(?=\d)", "", s)
    m = re.search(r"\b[1-9]\d{5}\b", s)
    return m.group() if m else None
