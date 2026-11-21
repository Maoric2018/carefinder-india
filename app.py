"""CareFinder India: a Databricks App (Streamlit) for health workers and NGO coordinators.

Local run (synthetic data):  CAREFINDER_LOCAL_CSV=tests/sample_facilities.csv streamlit run app.py
On Databricks Apps the data comes from Unity Catalog through the SQL warehouse in app.yaml.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from carefinder import SERVICES, CareFinder
from carefinder.engine import method_markdown

st.set_page_config(page_title="CareFinder India", page_icon="🏥", layout="wide")

FACILITY_TABLE = os.getenv("FACILITY_TABLE", "")
PIN_TABLE = os.getenv("PIN_TABLE", "")
BADGE = {"High": "🟢 High", "Medium": "🟡 Medium", "Low": "🔴 Low"}


def _query(sql: str) -> pd.DataFrame:
    from databricks import sql as dbsql
    from databricks.sdk.core import Config

    cfg = Config()
    with dbsql.connect(server_hostname=cfg.host,
                       http_path=f"/sql/1.0/warehouses/{os.environ['DATABRICKS_WAREHOUSE_ID']}",
                       credentials_provider=lambda: cfg.authenticate) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall_arrow().to_pandas()


@st.cache_resource(show_spinner="Loading 10,000 facilities and checking their records…")
def load_finder() -> CareFinder:
    local = os.getenv("CAREFINDER_LOCAL_CSV")
    if local:
        pins_path = os.getenv("CAREFINDER_LOCAL_PINS")
        return CareFinder(pd.read_csv(local), pin_directory=pd.read_csv(pins_path) if pins_path else None)
    raw = _query(f"SELECT * FROM {FACILITY_TABLE}")
    pins = _query(f"SELECT officename, pincode, district, statename, latitude, longitude FROM {PIN_TABLE}") \
        if PIN_TABLE else None
    return CareFinder(raw, pin_directory=pins)


finder = load_finder()

st.title("🏥 CareFinder India")
st.caption("Find where a patient can get a specific kind of care, and see the evidence behind every suggestion. "
           "Facility details come from public web sources and may be wrong: always call ahead.")

labels = [s.label for s in SERVICES.values()]
with st.form("search"):
    c1, c2 = st.columns([1, 1])
    choice = c1.selectbox("What care does the patient need?", labels + ["Something else…"],
                          index=labels.index("Dialysis"))
    other = c1.text_input("Describe it", placeholder="e.g. kidney transplant") if choice == "Something else…" else ""
    location = c2.text_input("Where is the patient?", placeholder="Town, district, village, PIN code, or lat, lon")
    with st.expander("Options"):
        top_k = st.slider("How many options to show", 1, 10, 5)
        max_km = st.slider("Furthest the patient can travel (km). 0 = let us decide", 0, 1000, 0, step=25)
    submitted = st.form_submit_button("Find care", type="primary")

if submitted:
    service_query = other or choice
    with st.spinner("Searching…"):
        res = finder.search(service_query, location, top_k=top_k, max_km=max_km or None)

    if res.error:
        st.error(res.error)
        st.stop()

    loc = res.location
    st.subheader(f"{res.service.label} near {loc.label}")
    approx = f" · ±{loc.uncertainty_km:.0f} km" if loc.uncertainty_km else ""
    st.caption(f"Location found by {loc.method}{approx}. Service: {res.service_note}. "
               f"{res.candidates:,} facilities in the data mention this service.")
    for note in loc.notes + res.notes:
        st.info(note)

    results = res.results
    left, right = st.columns([3, 2])
    with left:
        for r in results.itertuples():
            with st.container(border=True):
                st.markdown(f"### {r.rank}. {r.name}")
                place = ", ".join(x for x in (r.address, r.city, r.state, r.postcode) if isinstance(x, str) and x)
                st.markdown(f"**{r.distance_km:.1f} km away** · Confidence: **{BADGE[r.confidence_label]}** "
                            f"({r.confidence:.2f})  \n{place}")
                contact = " · ".join(x for x in (r.phone, r.website) if isinstance(x, str) and x)
                if contact:
                    st.caption(contact)
                st.markdown(f"Evidence found in: {r.evidence_fields or '—'}")
                with st.expander("Why this facility? (evidence and caveats)", expanded=r.rank == 1):
                    st.markdown(r.explanation)
    with right:
        st.caption("🔵 patient · 🔴 recommended facilities")
        pts = results[["lat", "lon"]].dropna().assign(size=400, color="#d93636cc")
        you = pd.DataFrame([{"lat": loc.lat, "lon": loc.lon, "size": 700, "color": "#1f66e5ee"}])
        st.map(pd.concat([you, pts], ignore_index=True), latitude="lat", longitude="lon", size="size", color="color")
        st.dataframe(results[["rank", "name", "distance_km", "confidence_label", "evidence_score", "trust",
                              "location_quality"]], hide_index=True, use_container_width=True)
        st.download_button("Download results (JSON)", res.to_json(), file_name="carefinder_results.json")

    with st.expander("How did we decide? (method, weights and trade-offs)"):
        st.markdown(method_markdown(res.service))
else:
    with st.expander("How does this work?"):
        st.markdown(method_markdown())
