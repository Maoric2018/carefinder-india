"""Services a user can ask for, and the words that count as evidence for each.

`core` terms mean "this facility says it delivers the service" (e.g. LSCS for a C-section).
`support` terms only corroborate (the specialty, the equipment, the staff you would expect).
Indian terminology is included on purpose: LSCS, SNCU, CEmONC, CTVS, PMNDP, DOTS, etc.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    key: str
    label: str
    core: tuple[str, ...]
    support: tuple[str, ...]
    travel_km: float  # distance at which the proximity factor drops to ~0.37
    needs_hospital: bool = False
    min_beds: int | None = None
    aliases: tuple[str, ...] = ()


SERVICES: dict[str, Service] = {s.key: s for s in [
    Service(
        "dialysis", "Dialysis",
        core=("dialysis", "hemodialysis", "haemodialysis", "peritoneal dialysis", "capd", "crrt",
              "renal replacement therapy", "pmndp", "dialysis unit", "dialysis centre", "dialysis center"),
        support=("nephrology", "nephrologist", "kidney", "renal", "dialyzer", "dialyser", "ro plant",
                 "av fistula", "kidney transplant", "renal transplant"),
        travel_km=40, aliases=("kidney dialysis", "renal dialysis", "kidney failure"),
    ),
    Service(
        "c_section", "Emergency C-section",
        core=("c section", "caesarean", "cesarean", "caeserean", "lscs", "lower segment caesarean",
              "emergency obstetric", "cemonc", "cemoc", "emonc", "comprehensive emergency obstetric"),
        support=("obstetrics", "obstetric", "obstetrician", "gynaecology", "gynecology", "obgyn", "ob gyn",
                 "labour room", "labor room", "maternity", "blood bank", "blood storage", "operation theatre",
                 "operation theater", "anaesthesia", "anesthesia", "anaesthetist", "anesthetist",
                 "high risk pregnancy", "first referral unit", "fru", "nicu", "sncu"),
        travel_km=30, needs_hospital=True, min_beds=10,
        aliases=("c section", "caesarean section", "cesarean section", "high risk delivery",
                 "emergency delivery", "obstetric emergency", "csection"),
    ),
    Service(
        "nicu", "Neonatal intensive care (NICU)",
        core=("nicu", "neonatal intensive care", "neonatal icu", "sncu", "special newborn care unit",
              "newborn intensive care", "level iii nicu", "level 3 nicu"),
        support=("neonatology", "neonatologist", "neonatal", "newborn", "incubator", "radiant warmer",
                 "phototherapy", "neonatal ventilator", "bubble cpap", "cpap", "picu", "pediatrics",
                 "paediatrics", "premature", "preterm"),
        travel_km=40, needs_hospital=True, min_beds=10,
        aliases=("neonatal care", "newborn icu", "premature baby", "sick newborn"),
    ),
    Service(
        "cardiac_surgery", "Cardiac surgery",
        core=("cardiac surgery", "heart surgery", "open heart", "cabg", "coronary artery bypass",
              "bypass surgery", "valve replacement", "cardiothoracic", "cardio thoracic", "ctvs",
              "cardiovascular surgery", "cardiac surgeon"),
        support=("cardiology", "cardiologist", "cath lab", "cathlab", "catheterization", "angioplasty",
                 "angiography", "heart lung machine", "perfusion", "cardiac icu", "ccu", "iccu",
                 "echocardiography", "ecmo"),
        travel_km=150, needs_hospital=True, min_beds=30,
        aliases=("heart surgery", "bypass", "open heart surgery", "cabg"),
    ),
    Service(
        "cath_lab", "Angioplasty / cath lab",
        core=("cath lab", "cathlab", "catheterization lab", "cardiac catheterization", "angioplasty", "ptca",
              "coronary angiography", "angiography", "stent", "stenting", "primary pci"),
        support=("cardiology", "cardiologist", "interventional cardiology", "ccu", "iccu", "cardiac icu",
                 "echocardiography", "tmt", "ecg"),
        travel_km=100, needs_hospital=True, min_beds=20,
        aliases=("angioplasty", "heart attack", "stent", "angiography"),
    ),
    Service(
        "mri", "MRI scan",
        core=("mri", "magnetic resonance", "1.5 tesla", "3 tesla", "1.5t mri", "3t mri", "mr imaging"),
        support=("radiology", "radiologist", "ct scan", "imaging", "diagnostic centre", "diagnostic center"),
        travel_km=75, aliases=("mri scan", "magnetic resonance imaging"),
    ),
    Service(
        "ct_scan", "CT scan",
        core=("ct scan", "ct scanner", "computed tomography", "cat scan", "mdct", "multislice ct",
              "multi slice ct", "slice ct", "hrct", "ct angiography"),
        support=("radiology", "radiologist", "imaging", "x ray", "ultrasound"),
        travel_km=60, aliases=("ct", "cat scan", "ct scan"),
    ),
    Service(
        "trauma", "Trauma care",
        core=("trauma centre", "trauma center", "trauma care", "trauma unit", "trauma ward", "polytrauma",
              "level 1 trauma", "level i trauma", "level ii trauma", "trauma surgery"),
        support=("casualty", "emergency department", "accident and emergency", "24x7 emergency",
                 "orthopaedic", "orthopedic", "neurosurgery", "neurosurgeon", "ct scan", "blood bank",
                 "icu", "ventilator", "ambulance", "operation theatre"),
        travel_km=30, needs_hospital=True, min_beds=20,
        aliases=("road accident", "accident", "trauma centre", "injury", "polytrauma"),
    ),
    Service(
        "emergency", "24x7 emergency room",
        core=("emergency department", "emergency room", "casualty", "accident and emergency",
              "24x7 emergency", "24 7 emergency", "24 hour emergency", "24 hours emergency",
              "emergency services", "emergency care", "emergency medicine"),
        support=("ambulance", "icu", "trauma", "ventilator", "blood bank", "critical care"),
        travel_km=25, needs_hospital=True,
        aliases=("emergency", "er", "casualty", "a&e"),
    ),
    Service(
        "burn_care", "Burn care",
        core=("burn unit", "burns unit", "burn ward", "burns ward", "burn care", "burns care", "burn centre",
              "burn center", "burn icu", "burns icu", "burn treatment", "burns management", "burn management"),
        support=("plastic surgery", "plastic surgeon", "skin graft", "skin grafting", "reconstructive surgery",
                 "wound care", "debridement", "icu"),
        travel_km=75, needs_hospital=True, min_beds=20, aliases=("burns", "burn injury", "burn"),
    ),
    Service(
        "oncology", "Cancer treatment",
        core=("oncology", "oncologist", "chemotherapy", "radiotherapy", "radiation therapy", "radiation oncology",
              "linac", "linear accelerator", "brachytherapy", "cobalt therapy", "cancer hospital",
              "cancer centre", "cancer center", "cancer treatment", "surgical oncology", "medical oncology"),
        support=("pet ct", "pet scan", "mammography", "biopsy", "histopathology", "cancer", "palliative"),
        travel_km=150, needs_hospital=True, aliases=("cancer", "chemo", "radiation", "tumour", "tumor"),
    ),
    Service(
        "icu", "Intensive care (ICU)",
        core=("icu", "intensive care", "critical care", "micu", "sicu", "ccu", "iccu", "hdu",
              "high dependency unit"),
        support=("ventilator", "intensivist", "multipara monitor", "cardiac monitor", "abg", "oxygen"),
        travel_km=40, needs_hospital=True, min_beds=10, aliases=("intensive care", "critical care", "ventilator"),
    ),
    Service(
        "maternity", "Maternity / normal delivery",
        core=("maternity", "labour room", "labor room", "normal delivery", "institutional delivery",
              "obstetrics", "antenatal", "obstetrician", "delivery services"),
        support=("gynaecology", "gynecology", "gynaecologist", "gynecologist", "ultrasound", "nicu", "sncu",
                 "blood bank"),
        travel_km=30, aliases=("delivery", "pregnancy", "childbirth", "antenatal care"),
    ),
    Service(
        "neurosurgery", "Neurosurgery",
        core=("neurosurgery", "neuro surgery", "neurosurgeon", "brain surgery", "craniotomy", "spine surgery"),
        support=("neurology", "neurologist", "ct scan", "mri", "icu", "neuro icu"),
        travel_km=150, needs_hospital=True, min_beds=30, aliases=("brain surgery", "head injury surgery"),
    ),
    Service(
        "orthopedic_surgery", "Orthopedic surgery",
        core=("joint replacement", "knee replacement", "hip replacement", "arthroplasty", "orthopaedic surgery",
              "orthopedic surgery", "fracture surgery", "arthroscopy"),
        support=("orthopaedics", "orthopedics", "orthopaedic", "orthopedic", "physiotherapy", "x ray", "c arm"),
        travel_km=100, needs_hospital=True, aliases=("knee replacement", "hip replacement", "fracture", "ortho"),
    ),
    Service(
        "eye_surgery", "Eye care / cataract surgery",
        core=("cataract", "phaco", "phacoemulsification", "sics", "intraocular lens", "lasik", "vitreoretinal",
              "glaucoma surgery", "ophthalmic surgery", "eye surgery"),
        support=("ophthalmology", "ophthalmologist", "eye hospital", "eye care", "optometry", "slit lamp",
                 "retina"),
        travel_km=100, aliases=("cataract", "eye", "eye surgery", "ophthalmology"),
    ),
    Service(
        "blood_bank", "Blood bank / transfusion",
        core=("blood bank", "blood storage", "blood storage unit", "blood transfusion", "blood centre",
              "blood center", "blood component"),
        support=("transfusion", "pathology", "laboratory"),
        travel_km=40, aliases=("blood", "transfusion"),
    ),
    Service(
        "pediatrics", "Child care (pediatrics)",
        core=("pediatrics", "paediatrics", "pediatric", "paediatric", "pediatrician", "paediatrician", "picu"),
        support=("neonatology", "nicu", "vaccination", "immunization", "immunisation"),
        travel_km=40, aliases=("child", "children", "kids", "pediatric care"),
    ),
    Service(
        "tb", "Tuberculosis treatment",
        core=("tuberculosis", "tb treatment", "tb clinic", "dots centre", "dots center", "dots", "nikshay",
              "mdr tb", "drug resistant tb", "chest clinic"),
        support=("pulmonology", "pulmonologist", "chest physician", "respiratory medicine", "sputum", "cbnaat",
                 "genexpert", "truenat", "chest x ray"),
        travel_km=50, aliases=("tb", "tuberculosis"),
    ),
    Service(
        "mental_health", "Mental health / psychiatry",
        core=("psychiatry", "psychiatric", "psychiatrist", "mental health", "de addiction", "deaddiction",
              "addiction treatment"),
        support=("psychologist", "psychology", "counselling", "counseling", "neurology"),
        travel_km=75, aliases=("mental health", "psychiatry", "depression", "addiction"),
    ),
    Service(
        "ultrasound", "Ultrasound",
        core=("ultrasound", "ultrasonography", "usg", "sonography", "doppler"),
        support=("radiology", "radiologist", "imaging", "x ray"),
        travel_km=30, aliases=("sonography", "usg", "scan"),
    ),
    Service(
        "dental", "Dental care",
        core=("dental", "dentist", "dentistry", "oral surgery", "root canal", "orthodontic", "maxillofacial"),
        support=("opg", "rvg", "dental x ray"),
        travel_km=40, aliases=("teeth", "tooth", "dentist"),
    ),
]}


def normalize(text: str) -> str:
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(text))  # camelCase specialty codes -> words
    text = text.lower().replace("&", " and ")
    text = re.sub(r"(?<=\d)\s*x\s*(?=\d)", "x", text)  # "24 x 7" -> "24x7"
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def find_service(query: str) -> tuple[Service | None, str]:
    """Resolve free text ('kidney dialysis', 'C-section') to a Service. Returns (service, how)."""
    q = normalize(query)
    if not q:
        return None, "empty query"
    for s in SERVICES.values():
        if q == s.key.replace("_", " ") or q == normalize(s.label):
            return s, "exact match"
    for s in SERVICES.values():
        if q in {normalize(a) for a in s.aliases}:
            return s, f"alias of {s.label}"
    for s in SERVICES.values():
        if q in {normalize(t) for t in s.core}:
            return s, f"'{query}' is a core term for {s.label}"
    # Fuzzy fallback over labels, aliases and core terms.
    choices: dict[str, Service] = {}
    for s in SERVICES.values():
        for name in (s.label, *s.aliases, *s.core):
            choices[normalize(name)] = s
    match = difflib.get_close_matches(q, list(choices), n=1, cutoff=0.75)
    if match:
        return choices[match[0]], f"closest match to '{match[0]}'"
    return None, "not in the service list"


def ad_hoc_service(query: str) -> Service:
    """A service built from the user's own words when it isn't in the list (no synonyms expanded)."""
    q = normalize(query)
    return Service(key=f"custom:{q}", label=query.strip(), core=(q,), support=(), travel_km=60)
