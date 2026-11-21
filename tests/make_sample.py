"""Synthetic facility records that imitate the dataset's known problems, for local tests.

NOT real data. Column names follow the Virtue Foundation style (camelCase, list fields as JSON strings)
so schema detection gets exercised too.
"""

import json
from pathlib import Path

import pandas as pd

ROWS = [
    # Patna, Bihar: one strong dialysis centre, one weak claim, one with a conflicting location.
    dict(pk_unique_id="f1", name="Patna Kidney Care Hospital", facilityTypeId="hospital",
         address_city="Patna", address_stateOrRegion="Bihar", address_zipOrPostcode="800001",
         latitude=25.6100, longitude=85.1400, specialties=["nephrology", "internalMedicine"],
         capability=["24x7 dialysis unit", "Kidney transplant workup"],
         procedure=["Hemodialysis", "Peritoneal dialysis (CAPD)"], equipment=["6 Fresenius dialysis machines", "RO plant"],
         description="Patna Kidney Care runs a 6-bed dialysis unit under PMNDP. Nephrologist available daily.",
         yearEstablished=2009, numberDoctors=14, capacity=60, source_urls=["https://example.org/pkc"]),
    dict(pk_unique_id="f2", name="Sai Clinic", facilityTypeId="clinic",
         address_city="Patna", address_stateOrRegion="Bihar", address_zipOrPostcode="800004",
         latitude=25.6000, longitude=85.1300, specialties=["generalMedicine"], capability=[], procedure=[],
         equipment=[], description="General physician clinic. Dialysis services also available.",
         source_urls=[]),
    dict(pk_unique_id="f3", name="Ganga Hospital", facilityTypeId="hospital",
         address_city="Patna", address_stateOrRegion="Bihar", address_zipOrPostcode="800020",
         latitude=28.6100, longitude=77.2000,  # Delhi coordinates: contradicts the address
         specialties=["nephrology"], capability=["Dialysis"], procedure=["Haemodialysis"], equipment=[],
         description="Multi-specialty hospital with dialysis.", capacity=40, source_urls=["https://example.org/ganga"]),
    dict(pk_unique_id="f4", name="Bihar Heart & Maternity Hospital", facilityTypeId="hospital",
         address_city="Patna", address_stateOrRegion="Bihar", address_zipOrPostcode="800013",
         latitude=25.5941, longitude=85.1376, specialties=["obstetricsAndGynecology", "neonatology"],
         capability=["Level III NICU", "24x7 emergency obstetric care", "Blood bank"],
         procedure=["LSCS", "Normal delivery"], equipment=["12 radiant warmers", "Neonatal ventilator"],
         description="Comprehensive emergency obstetric and newborn care (CEmONC). Labour room and obstetric OT 24x7.",
         capacity=80, numberDoctors=20, source_urls=["https://example.org/bhm", "https://other.example.com/bhm"]),
    dict(pk_unique_id="f5", name="Hajipur Dialysis Centre", facilityTypeId="clinic",
         address_city="Hajipur", address_stateOrRegion="Bihar", address_zipOrPostcode="844101",
         latitude=25.6858, longitude=85.2146, specialties=["nephrology"], capability=["Dialysis"],
         procedure=["Hemodialysis"], equipment=["Dialysis machines"],
         description="Standalone dialysis centre.", source_urls=["https://example.org/hdc"]),
    dict(pk_unique_id="f6", name="Patna Kidney Care Hospital", facilityTypeId="hospital",  # duplicate of f1
         address_city="Patna", address_stateOrRegion="Bihar", address_zipOrPostcode="800001",
         latitude=25.6101, longitude=85.1401, specialties=["nephrology"], capability=["Dialysis"],
         procedure=[], equipment=[], description="Kidney hospital.", source_urls=["https://example.org/pkc2"]),
    dict(pk_unique_id="f7", name="City Hospital and Sunrise Clinic", facilityTypeId="hospital",
         address_city="Patna", address_stateOrRegion="Bihar", address_zipOrPostcode="800001",
         latitude=25.6050, longitude=85.1350, specialties=["cardiology"], capability=["Cath lab"],
         procedure=["Angioplasty"], equipment=[],
         description="Branches in Mumbai and Chennai and Bengaluru. Contact 400001 or 600001.",
         source_urls=["https://example.org/city"]),
    dict(pk_unique_id="f8", name="Danapur Medicos", facilityTypeId="pharmacy",
         address_city="Danapur", address_stateOrRegion="Bihar", address_zipOrPostcode="801503",
         latitude=25.6200, longitude=85.0450, specialties=[], capability=["Dialysis consumables"],
         procedure=[], equipment=[], description="Chemist and druggist.", source_urls=[]),
    dict(pk_unique_id="f9", name="Gaya Medical Hospital", facilityTypeId="hospital",
         address_city="Gaya", address_stateOrRegion="Bihar", address_zipOrPostcode="823001",
         latitude=24.7914, longitude=85.0002, specialties=["nephrology"], capability=["Dialysis unit (coming soon)"],
         procedure=[], equipment=[], description="We do not have dialysis yet; patients are referred to Patna for dialysis.",
         source_urls=["https://example.org/gaya"]),
    # Other cities so the gazetteer has more than one place.
    *[dict(pk_unique_id=f"m{i}", name=f"Mumbai Hospital {i}", facilityTypeId="hospital", address_city="Mumbai",
           address_stateOrRegion="Maharashtra", address_zipOrPostcode=f"40000{i}",
           latitude=19.07 + i * 0.01, longitude=72.87 + i * 0.01, specialties=["cardiology"],
           capability=["Cardiac surgery" if i == 1 else "Cardiology OPD"], procedure=["CABG"] if i == 1 else [],
           equipment=["Heart-lung machine"] if i == 1 else [], description="Hospital in Mumbai.",
           capacity=200, source_urls=[f"https://example.org/m{i}"]) for i in range(1, 5)],
    *[dict(pk_unique_id=f"c{i}", name=f"Chennai Clinic {i}", facilityTypeId="clinic", address_city="Madras",
           address_stateOrRegion="Tamilnadu", address_zipOrPostcode=f"60000{i}",
           latitude=13.08 + i * 0.01, longitude=80.27 + i * 0.01, specialties=["dentistry"],
           capability=[], procedure=["Root canal"], equipment=[], description="Dental clinic.",
           source_urls=[]) for i in range(1, 4)],
    *[dict(pk_unique_id=f"b{i}", name=f"Bengaluru Nursing Home {i}", facilityTypeId="hospital",
           address_city="Bangalore", address_stateOrRegion="Karnataka", address_zipOrPostcode=f"56000{i}",
           latitude=12.97 + i * 0.01, longitude=77.59 + i * 0.01, specialties=["generalSurgery"],
           capability=[], procedure=[], equipment=[], description="Nursing home.",
           source_urls=[]) for i in range(1, 4)],
    *[dict(pk_unique_id=f"p{i}", name=f"Patna Health Centre {i}", facilityTypeId="clinic", address_city="Patna",
           address_stateOrRegion="Bihar", address_zipOrPostcode="800001",
           latitude=25.60 + i * 0.005, longitude=85.13 + i * 0.005, specialties=["generalMedicine"],
           capability=[], procedure=[], equipment=[], description="Primary care.", source_urls=[]) for i in range(1, 4)],
]


def sample_pins() -> pd.DataFrame:
    """Imitates india_post_pincode_directory.csv: one row per post office, some without coordinates."""
    rows = [
        ("Patna G.P.O", "800001", "PO", "PATNA", "BIHAR", 25.611, 85.141),
        ("Patna Sachivalaya S.O", "800001", "PO", "PATNA", "BIHAR", 25.605, 85.130),
        ("Kankarbagh S.O", "800020", "PO", "PATNA", "BIHAR", 25.594, 85.157),
        ("Bakhtiyarpur B.O", "803212", "BO", "PATNA", "BIHAR", 25.461, 85.531),
        ("Hajipur H.O", "844101", "HO", "VAISHALI", "BIHAR", 25.686, 85.215),
        ("Gaya H.O", "823001", "HO", "GAYA", "BIHAR", 24.791, 85.000),
        ("Remote B.O", "803999", "BO", "PATNA", "BIHAR", "NA", "NA"),
        ("Mumbai G.P.O", "400001", "PO", "MUMBAI", "MAHARASHTRA", 18.938, 72.835),
        ("Aurangabad H.O", "824101", "HO", "AURANGABAD", "BIHAR", 19.880, 75.340),  # wrong: Maharashtra coords
    ]
    return pd.DataFrame(rows, columns=["officename", "pincode", "officetype", "district", "statename",
                                       "latitude", "longitude"])


def sample_nfhs() -> pd.DataFrame:
    """Imitates nfhs_5_district_health_indicators (a few of its 109 columns, real column names, made-up values)."""
    cols = ["district_name", "state_ut", "institutional_birth_5y_pct", "births_delivered_by_csection_5y_pct",
            "mothers_who_had_at_least_4_anc_visits_lb5y_pct", "hh_member_covered_health_insurance_pct",
            "w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
            "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
            "w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
            "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct"]
    rows = [
        ("Patna", "Bihar", 84.1, 15.2, 40.3, 12.0, 14.0, 16.0, 18.0, 22.0),
        ("Vaishali", "Bihar", 79.0, 9.8, 30.1, 10.5, 12.5, 15.5, 17.0, 20.0),
        ("Gaya", "Bihar", 76.5, 7.1, 28.0, 9.0, 13.0, 17.0, 16.0, 21.0),
        ("Pashchim Champaran", "Bihar", 70.2, 4.9, 19.5, 6.0, 11.0, 13.0, 15.0, 18.0),
        ("Mumbai", "Maharashtra", 98.0, 38.0, 80.0, 30.0, 15.0, 17.0, 20.0, 24.0),
    ]
    return pd.DataFrame(rows, columns=cols)


def sample_frame() -> pd.DataFrame:
    df = pd.DataFrame(ROWS)
    for col in ("specialties", "capability", "procedure", "equipment", "source_urls"):
        df[col] = df[col].map(json.dumps)  # list fields arrive as JSON strings
    return df


if __name__ == "__main__":
    here = Path(__file__).parent
    sample_frame().to_csv(here / "sample_facilities.csv", index=False)
    sample_pins().to_csv(here / "sample_pins.csv", index=False)
    sample_nfhs().to_csv(here / "sample_nfhs.csv", index=False)
    print(f"wrote sample_facilities.csv, sample_pins.csv and sample_nfhs.csv in {here}")
