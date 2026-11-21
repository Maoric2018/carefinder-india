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
    # f3's Delhi coordinates contradict its own PIN as well as its city.
    row = f.facilities.set_index("id").loc["f3"]
    assert "PIN 800020" in row["conflict_detail"]
    assert f.facilities.set_index("id").loc["f5", "district_n"] == "vaishali"


def test_method_and_table(finder):
    assert "How we decide" in method_markdown()
    table = evidence_table(finder)
    assert {"facility_id", "service", "confidence", "citations"} <= set(table.columns)
