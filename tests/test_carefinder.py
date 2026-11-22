import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import pytest  # noqa: E402

from carefinder import CareFinder, find_service  # noqa: E402
from carefinder.engine import evidence_table, method_markdown  # noqa: E402
from carefinder.parse import clean_postcode, to_list  # noqa: E402
from carefinder.schema import detect_columns  # noqa: E402
from make_sample import sample_frame, sample_pins  # noqa: E402


@pytest.fixture(scope="module")
def finder():
    return CareFinder(sample_frame())


def test_schema_detection():
    m = detect_columns(sample_frame().columns)
    assert m["state"] == "address_stateOrRegion"
    assert m["postcode"] == "address_zipOrPostcode"
    assert m["lat"] == "latitude" and m["lon"] == "longitude"
    assert m["num_doctors"] == "numberDoctors"


def test_parsing():
    assert to_list('["a", "b", "a"]') == ["a", "b"]
    assert to_list("['x', 'y']") == ["x", "y"]
    assert to_list("null") == []
    assert clean_postcode(800001.0) == "800001"
    assert clean_postcode("800 001") == "800001"


def test_service_lookup():
    assert find_service("kidney dialysis")[0].key == "dialysis"
    assert find_service("C-section")[0].key == "c_section"
    assert find_service("LSCS")[0].key == "c_section"
    assert find_service("NICU")[0].key == "nicu"
    assert find_service("cardiac surgery")[0].key == "cardiac_surgery"


def test_quality_flags(finder):
    f = finder.facilities.set_index("id")
    assert f.loc["f3", "coords_conflict"]  # Delhi coordinates for a Patna address
    assert f.loc["f7", "merge_reasons"]    # two facility names + other-state places
    assert f.loc["f8", "kind"] == "pharmacy"
    assert f.loc["f1", "dup_count"] == 1   # f6 is the same facility


def test_dialysis_patna(finder):
    res = finder.search("dialysis", "Patna")
    assert not res.error, res.error
    top = res.results
    assert top.iloc[0]["id"] == "f1"
    assert top.iloc[0]["confidence_label"] == "High"
    ids = list(top["id"])
    assert "f6" not in ids            # duplicate collapsed
    assert "f9" not in ids            # negated / "coming soon" claim doesn't count
    assert "f8" not in ids            # "dialysis consumables" at a chemist is a product, not a service
    assert top.iloc[0]["citations"]   # every recommendation carries quotes
    conflict = top[top["id"] == "f3"]
    if len(conflict):
        assert any("contradict" in c for c in conflict.iloc[0]["caveats"])
    print(res.to_markdown())


def test_c_section_and_aliases(finder):
    res = finder.search("emergency c-section", "800013")
    assert res.location.method == "PIN code"
    assert res.results.iloc[0]["id"] == "f4"


def test_location_aliases(finder):
    res = finder.search("dental", "Madras")
    assert res.location.label.lower().startswith("chennai")
    res = finder.search("cardiac surgery", "Bombay, Maharashtra")
    assert res.results.iloc[0]["id"] == "m1"
    assert finder.search("dialysis", "25.61, 85.14").location.method == "coordinates"
    assert finder.search("dialysis", "Nowhereville").error


def test_unknown_service_falls_back(finder):
    res = finder.search("Root canal", "Chennai")
    assert not res.error
    assert len(res.results) > 0


def test_pin_directory():
    f = CareFinder(sample_frame(), pin_directory=sample_pins())
    # A village that has no facility of its own resolves through its post office.
    res = f.search("dialysis", "Bakhtiyarpur")
    assert res.location.method == "post office / town"
    assert res.results.iloc[0]["confidence_label"] == "High"
    # PINs come from India Post, with the district named.
    assert "Patna" in f.search("dialysis", "800020").location.label
    # f3's Delhi coordinates contradict both its city and its PIN, which agree with each other -> use the address.
    row = f.facilities.set_index("id").loc["f3"]
    assert row["location_issue"] == "coords_fixed"
    assert row["loc_quality"] == "PIN area"
    assert f.facilities.set_index("id").loc["f5", "district_n"] == "vaishali"


def test_other_facility_claims_are_ignored():
    from carefinder.names import other_facility, own_website, tokens
    own = tokens("Aravind Eye Hospital")
    assert other_facility("Madras Medical Mission, Chennai is listed as a referral hospital", own)
    assert other_facility("Aravind Eye Hospital is listed in the Hyderabad directory", own) is None
    assert other_facility("Robotic surgery at Fortis Memorial Research Institute", tokens("Fortis Hospital Anandapur"))
    assert other_facility("Hip replacement at Fortis Hospital, Anandapur", tokens("Fortis Hospital Anandapur")) is None
    assert own_website("Patna Dialysis Centre", ["https://www.justdial.com/x", "http://patnadialysis.com/"]) == "patnadialysis.com"
    # Listing-site phrases, spelling variants, verbs and landmarks are not other facilities.
    assert other_facility("Rated a Top Clinic on Practo", tokens("Bansal Hospital")) is None
    assert other_facility("Also spelled Dhanvatri Hospital", tokens("Dhanvantari Hospital")) is None
    assert other_facility("Operates Dental IQ Clinic", tokens("Dental IQ Clinic")) is None
    assert other_facility("Located opposite City Hospital, Main Road", tokens("Sai Clinic")) is None
    assert other_facility("Patients referred from Ganga Ram Hospital", tokens("Sai Clinic")) == "Ganga Ram Hospital"


def test_negated_related_words_do_not_penalise():
    """'lack of ICU' must not count as 'burn care unavailable'; only direct mentions of the service do."""
    from carefinder.evidence import score_evidence
    from carefinder.taxonomy import SERVICES
    f = CareFinder(sample_frame())
    rec = dict(f._records[0], description="Inspectors noted a lack of ICU beds. Has a 10-bed burn unit.",
               procedure=[], capability=[], equipment=[], specialties=[])
    ev = score_evidence(rec, SERVICES["burn_care"])
    assert ev.has_core
    assert not any(h.kind == "core" for h in ev.negated)  # only direct mentions can count as "unavailable"


def test_snippet_shows_the_match():
    from carefinder.evidence import _snippet
    long = "Specialties include " + ", ".join(f"Thing{i}" for i in range(40)) + ", Burns Management, Cardiology"
    assert "Burns" in _snippet(long, "burns")


def test_render(finder):
    from carefinder.render import md_to_html
    page = md_to_html(finder.search("dialysis", "Patna").to_markdown())
    assert "<h4>" in page and "<b>" in page and "<li>" in page and "**" not in page


def test_method_and_table(finder):
    assert "How we decide" in method_markdown()
    table = evidence_table(finder)
    assert {"facility_id", "service", "confidence", "citations", "district", "top_quote"} <= set(table.columns)


def test_places_and_sql():
    from carefinder.engine import find_care_sql, places_table
    f = CareFinder(sample_frame(), pin_directory=sample_pins())
    places = places_table(f)
    assert {"city", "pin", "district", "post office", "state"} <= set(places["kind"])
    assert (places["name"] == "bakhtiyarpur").any()
    assert (places["name"] == "bombay").any()  # alias rows
    sql = find_care_sql("workspace.carefinder")
    assert "workspace.carefinder.places" in sql and "find_care" in sql


def test_planner_coverage():
    from carefinder import find_service
    from carefinder.coverage import (INDICATORS, _variants, audit_summary, coverage, facility_confidence,
                                     place_districts, prepare_nfhs)
    from make_sample import sample_nfhs

    f = CareFinder(sample_frame(), pin_directory=sample_pins())
    nfhs = prepare_nfhs(sample_nfhs())
    assert nfhs.loc[0, "state"] == "bihar"
    assert nfhs.loc[0, "sugar"] == pytest.approx(15.0)  # women and men averaged
    assert nfhs["vaccinated"].isna().all()  # column not in this table -> NaN, not an error
    assert "west champaran" in _variants("Pashchim Champaran")
    assert "belagavi" in _variants("Belgaum")
    assert "north 24 parganas" in _variants("North Twenty Four Pargana")
    assert "nellore" in _variants("Sri Potti Sriramulu Nello")
    assert "khandwa" in _variants("Khandwa (East Nimar)") and "west singhbhum" in _variants("Pashchimi Singhbhum")

    placed = place_districts(nfhs, f).set_index("district")
    assert placed.loc["Patna", "placed_by"] == "India Post district"
    assert placed.loc["Vaishali", "placed_by"] == "India Post district"
    assert placed.loc["Pashchim Champaran", "placed_by"] == "not placed"
    assert f.pin_dir.dropped_far == 1 and "aurangabad" not in f.pin_dir.districts  # coords from another state

    dialysis = find_service("dialysis")[0]
    fac = facility_confidence(f, dialysis)
    assert (fac["label"] == "High").any()
    cov = coverage(placed.reset_index(), fac, dialysis, "sugar").set_index("district")
    assert cov.loc["Patna", "status"] == "covered"
    assert cov.loc["Vaishali", "status"] == "covered"  # Hajipur is ~10 km from Patna's dialysis hospital
    assert cov.loc["Gaya", "status"] in ("gap", "weak evidence only")
    assert cov.loc["Gaya", "nearest_high_km"] > dialysis.travel_km
    assert cov.loc["Pashchim Champaran", "status"] == "not placed"
    # gaps come first
    assert list(coverage(placed.reset_index(), fac, dialysis, "sugar")["status"])[0] != "covered"
    assert set(INDICATORS) >= {"csection", "sugar", "bp", "insurance"}

    audit = audit_summary(f)
    assert audit["records"] == len(f.facilities) and audit["location_fixed"] + audit["location_conflict"] >= 1


def test_em_recovers_known_parameters():
    """Simulate records from a known latent class model; EM must recover its rates and covariate effect."""
    import numpy as np
    from carefinder.model import fit, simulate
    cats = (3, 3, 3, 2)
    theta1 = [np.array([0.3, 0.2, 0.5]), np.array([0.5, 0.1, 0.4]), np.array([0.6, 0.3, 0.1]), np.array([0.7, 0.3])]
    theta0 = [np.array([0.97, 0.02, 0.01]), np.array([0.98, 0.015, 0.005]), np.array([0.95, 0.04, 0.01]),
              np.array([0.9, 0.1])]
    gamma = np.array([-2.0, -1.0])
    rng = np.random.default_rng(1)
    Z = (rng.random((40000, 1)) < 0.3).astype(float)
    X, Z, y = simulate(40000, theta1, theta0, gamma, Z, seed=2)
    m = fit(X, Z, cats=cats, n_boot=20)  # true effect is negative, so the sign constraint is inactive
    for est, true in zip(m.theta1 + m.theta0, theta1 + theta0):
        assert np.abs(est - true).max() < 0.03
    assert abs(m.gamma[0] - gamma[0]) < 0.15 and abs(m.gamma[1] - gamma[1]) < 0.2
    p = m.posterior(X, Z)
    assert ((p > 0.5) == y).mean() > 0.9
    lo, hi = m.interval(X[:50], Z[:50])
    assert (lo <= p[:50] + 1e-9).all() and (hi >= p[:50] - 1e-9).all()


def test_access_probability():
    import numpy as np
    from carefinder import access
    km = access.reach_km(2.0)
    assert abs(float(access.p_reach(km, 2.0)) - 0.5) < 1e-6          # median travel time = window
    d = np.array([1, 10, 30, 60, 120, 300])
    p = access.p_reach(d, 2.0)
    assert (np.diff(p) < 0).all() and p[0] > 0.99 and p[-1] < 0.05      # monotone, sensible tails
    assert access.p_reach(30, 1.0) < access.p_reach(30, 2.0)            # tighter window, lower chance
    far = float(access.p_reach(120, 2.0)); fuzzy = float(access.p_reach(120, 2.0, 60.0))
    assert fuzzy > far                                                  # uncertainty pulls a far place towards 0.5


def test_learned_model_orders_evidence(finder):
    """More independent fields saying it -> higher learned probability; a record check lowers it."""
    from carefinder import find_service
    svc = find_service("dialysis")[0]
    sc = finder.scores_for(svc)
    ids = list(finder.facilities["id"])
    p = dict(zip(ids, sc["p"]))
    assert p["f1"] >= p["f5"] > p["f2"]  # 4 fields + detail >= 3 fields > one line in a description
    m = finder.model_for(svc)
    lr = m.likelihood_ratios()
    assert all(lr[f]["dedicated"] > 1 for f in ("procedure", "capability"))


def test_breakdown_reproduces_posterior():
    """The arithmetic shown in the app (base odds × field factors^(1/deff) × signals × flags) is the model's posterior."""
    import numpy as np
    from carefinder.model import CATS, fit, simulate
    t1 = [np.array([.2, .3, .5])] * 6 + [np.array([.8, .2])] * 3
    t0 = [np.array([.9, .07, .03])] * 6 + [np.array([.9, .1])] * 3
    Z = (np.random.default_rng(1).random((3000, 2)) < 0.2).astype(float)
    X, Z, _ = simulate(3000, t1, t0, np.array([-2.0, -1.0, 0.0]), Z=Z, seed=3)
    m = fit(X, Z, cats=CATS, n_boot=0)
    m.rho = 0.1
    post = m.posterior(X[:50], Z[:50])
    for i in range(50):
        b = m.breakdown(X[i], Z[i])
        assert abs(b["p"] - post[i]) < 1e-9
        flags = np.prod([o for _, o in b["flags"]]) if b["flags"] else 1.0
        sig = np.prod([v for _, _, v in b["signals"]])
        assert abs(b["base_odds"] * b["field_factor"] * sig * flags - b["odds"]) < 1e-6 * max(1, b["odds"])
