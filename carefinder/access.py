"""Can the patient get there in time? A probability, not an arbitrary distance decay.

Travel time t = DETOUR × straight-line km ÷ v, with speed v log-normal (median SPEED_KMH, log-sd SPEED_SD_LOG),
so log t is normal. Location uncertainty (a facility placed at its city centre, a patient located by PIN code)
adds to that spread. The access probability is P(t ≤ window), where the window is a clinical time standard for
the service:

  * 2 h for emergency surgery and obstetrics: the Lancet Commission on Global Surgery's timely-access standard
    for the bellwether procedures (caesarean section, laparotomy, open fracture), Meara et al. 2015.
  * 1 h for trauma and emergency rooms: the conventional "golden hour".
  * 2 h for a cath lab: STEMI guidelines target reperfusion within 120 min of first medical contact.
  * 1 h one way for dialysis, three times a week: in DOPPS, one-way travel over 60 min was associated with
    higher mortality (Moist et al. 2008).
  * Longer windows for planned care (MRI, cancer treatment, cardiac surgery), which are our assumptions.

DETOUR and SPEED_KMH are assumptions too (we found no India-wide published value): road distance is about 1.4×
straight-line distance in US hospital-access studies (Boscoe et al. 2012), and 35 km/h is a door-to-door
motorised average on mixed Indian roads. Both are single constants, shown in the app, and easy to change.
Φ uses the logistic approximation 1/(1+e^(-1.702x)) (max error < 0.01) so SQL and Python give the same numbers.
"""

from __future__ import annotations

import math

import numpy as np

DETOUR = 1.4
SPEED_KMH = 35.0
SPEED_SD_LOG = 0.35

# service -> (time window in hours, where it comes from)
WINDOWS: dict[str, tuple[float, str]] = {
    "c_section": (2.0, "Lancet Commission on Global Surgery: caesarean section within 2 h"),
    "maternity": (2.0, "Lancet Commission 2 h standard for emergency obstetric care"),
    "nicu": (2.0, "2 h, same standard as emergency obstetric care"),
    "icu": (2.0, "2 h for critical care (assumption)"),
    "trauma": (1.0, "the 'golden hour' for major trauma"),
    "emergency": (1.0, "the 'golden hour' for emergency care"),
    "burn_care": (2.0, "2 h for acute burns (assumption)"),
    "cath_lab": (2.0, "STEMI reperfusion within 120 min of first medical contact"),
    "dialysis": (1.0, "DOPPS: one-way travel over 60 min linked to higher mortality"),
    "blood_bank": (1.0, "1 h for transfusion support (assumption)"),
    "ct_scan": (2.0, "2 h for emergency imaging (assumption)"),
    "mri": (4.0, "4 h for planned imaging (assumption)"),
    "neurosurgery": (2.0, "2 h for emergency head injury surgery (assumption)"),
    "cardiac_surgery": (6.0, "6 h for planned cardiac surgery (assumption)"),
    "oncology": (6.0, "6 h for planned cancer treatment (assumption)"),
    "orthopedic_surgery": (4.0, "4 h for planned orthopaedic surgery (assumption)"),
    "eye_surgery": (4.0, "4 h for planned eye surgery (assumption)"),
    "pediatrics": (1.0, "1 h for child care (assumption)"),
    "tb": (2.0, "2 h for repeated TB visits (assumption)"),
    "mental_health": (2.0, "2 h for psychiatric care (assumption)"),
    "ultrasound": (1.0, "1 h for antenatal scans (assumption)"),
    "dental": (1.0, "1 h for dental care (assumption)"),
}
DEFAULT_WINDOW = (2.0, "2 h default (assumption)")

# How far off a facility's location may be, by how we placed it (km, ~1 sd).
LOCATION_SD_KM = {"exact": 1.0, "unverified coordinates": 3.0, "shared coordinates": 8.0, "city centre": 8.0,
                  "PIN area": 6.0, "district centre": 20.0, "conflicting coordinates": 30.0}


def window(service_key: str) -> tuple[float, str]:
    return WINDOWS.get(service_key, DEFAULT_WINDOW)


def reach_km(hours: float) -> float:
    """Straight-line distance at which the median travel time equals the window (P = 0.5)."""
    return hours * SPEED_KMH / DETOUR


def phi(x):
    return 1.0 / (1.0 + np.exp(-1.702 * np.asarray(x, dtype=float)))


def p_reach(km, hours: float, loc_sd_km=0.0):
    """P(travel time ≤ hours) for straight-line distance(s) km, with location uncertainty loc_sd_km."""
    km = np.maximum(np.asarray(km, dtype=float), 0.05)
    sd = np.asarray(loc_sd_km, dtype=float)
    rel = sd / np.maximum(km, sd + 1e-9)           # relative distance error, at most ~1
    s = np.sqrt(SPEED_SD_LOG ** 2 + rel ** 2)
    median_h = DETOUR * km / SPEED_KMH
    return phi((math.log(hours) - np.log(median_h)) / s)


def travel_hours(km: float) -> float:
    return DETOUR * km / SPEED_KMH
