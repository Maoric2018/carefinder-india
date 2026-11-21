"""CareFinder India: a Databricks App (Streamlit) for health workers and NGO coordinators.

Local run (synthetic data):  CAREFINDER_LOCAL_CSV=tests/sample_facilities.csv streamlit run app.py
On Databricks Apps the data comes from Unity Catalog through the SQL warehouse in app.yaml.
"""

from __future__ import annotations

import html
import math
import os

import pandas as pd
import pydeck as pdk
import streamlit as st

from carefinder import SERVICES, CareFinder
from carefinder.engine import method_markdown

st.set_page_config(page_title="CareFinder India", page_icon="🩺", layout="wide")

FACILITY_TABLE = os.getenv("FACILITY_TABLE", "")
PIN_TABLE = os.getenv("PIN_TABLE", "")
LABELS = [s.label for s in SERVICES.values()]
EXAMPLES = [  # (service, place, button label)
    ("Dialysis", "Bakhtiyarpur, Bihar", "Dialysis · Bakhtiyarpur"),
    ("Emergency C-section", "Nagpur", "C-section · Nagpur"),
    ("Burn care", "411001", "Burn care · PIN 411001"),
    ("Neonatal intensive care (NICU)", "Lucknow", "NICU · Lucknow"),
]
TONE = {"High": ("#047857", "#ECFDF5", "#A7F3D0"), "Medium": ("#B45309", "#FFFBEB", "#FDE68A"),
        "Low": ("#B91C1C", "#FEF2F2", "#FECACA")}
DOT = {"High": [4, 120, 87], "Medium": [217, 119, 6], "Low": [220, 38, 38]}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stMarkdown, .stTextInput, .stSelectbox, button { font-family: 'Inter', system-ui, sans-serif !important; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] { visibility: hidden; height: 0; }
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1320px; }
.cf-hero { display:flex; align-items:center; justify-content:space-between; gap:24px; padding:22px 26px; border-radius:18px;
  background: linear-gradient(120deg, #0B3B3C 0%, #0F766E 55%, #14B8A6 100%); color:#fff; box-shadow: 0 12px 30px -12px rgba(15,118,110,.55); }
.cf-brand { display:flex; align-items:center; gap:14px; }
.cf-logo { width:48px; height:48px; border-radius:14px; background:rgba(255,255,255,.14); display:flex; align-items:center; justify-content:center; }
.cf-brand h1 { font-size:30px; font-weight:800; letter-spacing:-.02em; margin:0; padding:0; color:#fff; line-height:1.1; }
.cf-brand p { margin:4px 0 0; font-size:15px; color:rgba(255,255,255,.86); }
.cf-stats { display:flex; gap:10px; flex-wrap:wrap; justify-content:flex-end; }
.cf-stat { background:rgba(255,255,255,.13); border:1px solid rgba(255,255,255,.22); border-radius:12px; padding:8px 12px; text-align:right; }
.cf-stat b { display:block; font-size:19px; font-weight:800; color:#fff; }
.cf-stat span { font-size:11.5px; color:rgba(255,255,255,.82); text-transform:uppercase; letter-spacing:.05em; }
.cf-label { font-size:12px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.07em; margin:18px 0 6px; }
div[data-testid="stForm"] { background:#fff; border:1px solid #E5E7EB; border-radius:16px; padding:18px 20px 6px; box-shadow:0 1px 2px rgba(15,23,42,.04); }
.stButton > button { border-radius:999px; border:1px solid #D1D5DB; background:#fff; color:#0F172A; font-weight:500; font-size:13.5px; padding:4px 14px; }
.stButton > button:hover { border-color:#0F766E; color:#0F766E; background:#F0FDFA; }
div[data-testid="stFormSubmitButton"] > button { border-radius:12px; background:#0F766E; color:#fff; border:none; font-weight:700; padding:8px 26px; font-size:15px; }
div[data-testid="stFormSubmitButton"] > button:hover { background:#0B5F59; color:#fff; }
div[data-testid="stFormSubmitButton"] > button:focus, div[data-testid="stFormSubmitButton"] > button:active,
div[data-testid="stFormSubmitButton"] > button:focus:not(:active) { background:#0F766E; color:#fff !important; border:none; }
.cf-results-h { font-size:26px; font-weight:800; letter-spacing:-.02em; margin:26px 0 8px; color:#0F172A; }
.cf-chips { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }
.cf-chip { display:inline-flex; align-items:center; gap:6px; background:#fff; border:1px solid #E5E7EB; border-radius:999px; padding:5px 12px; font-size:13px; color:#334155; }
.cf-chip b { color:#0F172A; }
.cf-note { display:flex; gap:10px; align-items:flex-start; border-radius:12px; padding:11px 14px; margin:8px 0; font-size:14px; line-height:1.45; }
.cf-note.trade { background:#EFF6FF; border:1px solid #BFDBFE; color:#1E3A8A; }
.cf-note.warn { background:#FFFBEB; border:1px solid #FDE68A; color:#78350F; }
.cf-note .i { font-weight:800; white-space:nowrap; }
.cf-card { background:#fff; border:1px solid #E5E7EB; border-radius:16px; padding:18px 20px 16px; margin:12px 0 4px; box-shadow:0 1px 3px rgba(15,23,42,.05); }
.cf-top { display:flex; align-items:flex-start; gap:14px; }
.cf-rank { flex:none; width:34px; height:34px; border-radius:50%; background:#0F172A; color:#fff; font-weight:800; display:flex; align-items:center; justify-content:center; font-size:15px; }
.cf-title { flex:1; min-width:0; }
.cf-name { font-size:19px; font-weight:700; color:#0F172A; letter-spacing:-.01em; line-height:1.25; }
.cf-sub { font-size:13.5px; color:#64748B; margin-top:3px; }
.cf-pill { flex:none; display:inline-flex; align-items:center; gap:7px; border-radius:999px; padding:6px 12px; font-weight:700; font-size:13.5px; border:1px solid; }
.cf-pill i { width:8px; height:8px; border-radius:50%; display:inline-block; }
.cf-metrics { display:grid; grid-template-columns: 1fr 1fr 1fr 1.6fr; gap:10px; margin:14px 0 12px; }
.cf-m { background:#F8FAFC; border:1px solid #EEF2F6; border-radius:12px; padding:9px 12px; }
.cf-m .k { display:block; font-size:11px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.06em; }
.cf-m .v { display:block; font-size:18px; font-weight:800; color:#0F172A; margin-top:2px; }
.cf-m .v.s { font-size:13px; font-weight:600; line-height:1.35; margin-top:4px; }
.cf-bar { height:5px; border-radius:9px; background:#E2E8F0; margin-top:6px; overflow:hidden; }
.cf-bar i { display:block; height:100%; border-radius:9px; }
.cf-why-h { font-size:12px; font-weight:700; color:#64748B; text-transform:uppercase; letter-spacing:.07em; margin:4px 0 6px; }
.cf-q { display:flex; gap:10px; align-items:baseline; padding:7px 0; border-top:1px dashed #E5E7EB; font-size:14.5px; color:#1E293B; line-height:1.45; }
.cf-q:first-of-type { border-top:none; }
.cf-tag { flex:none; font-size:11px; font-weight:700; color:#0F766E; background:#F0FDFA; border:1px solid #99F6E4; border-radius:6px; padding:2px 7px; text-transform:uppercase; letter-spacing:.04em; }
.cf-q em { color:#94A3B8; font-style:normal; font-size:12px; }
.cf-flags { margin-top:12px; border-radius:12px; padding:9px 12px; font-size:13.5px; line-height:1.45; }
.cf-flags.ok { background:#ECFDF5; border:1px solid #A7F3D0; color:#065F46; }
.cf-flags.bad { background:#FFF7ED; border:1px solid #FED7AA; color:#7C2D12; }
.cf-flags div { padding:2px 0; }
.cf-flags b { font-weight:800; }
.cf-good { display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }
.cf-good span { font-size:12.5px; background:#F1F5F9; color:#334155; border-radius:999px; padding:3px 10px; }
.cf-contact { margin-top:10px; font-size:13px; color:#475569; }
.cf-contact a { color:#0F766E; text-decoration:none; font-weight:600; }
.cf-side { background:#fff; border:1px solid #E5E7EB; border-radius:16px; padding:14px 16px; margin-top:12px; }
.cf-row { display:flex; align-items:center; gap:10px; padding:8px 0; border-top:1px solid #F1F5F9; font-size:14px; }
.cf-row:first-child { border-top:none; }
.cf-row .n { width:22px; height:22px; border-radius:50%; color:#fff; font-size:12px; font-weight:800; display:flex; align-items:center; justify-content:center; flex:none; }
.cf-row .nm { flex:1; font-weight:600; color:#0F172A; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.cf-row .km { color:#475569; font-variant-numeric: tabular-nums; }
.cf-legend { display:flex; gap:14px; font-size:12.5px; color:#475569; margin:8px 2px 0; flex-wrap:wrap; }
.cf-legend span i { width:9px; height:9px; border-radius:50%; display:inline-block; margin-right:5px; vertical-align:middle; }
.cf-steps { display:grid; grid-template-columns: repeat(3, 1fr); gap:14px; margin-top:10px; }
.cf-step { background:#fff; border:1px solid #E5E7EB; border-radius:16px; padding:16px 18px; }
.cf-step .no { width:30px; height:30px; border-radius:9px; background:#F0FDFA; color:#0F766E; font-weight:800; display:flex; align-items:center; justify-content:center; margin-bottom:8px; }
.cf-step h4 { margin:0 0 4px; font-size:16px; font-weight:700; color:#0F172A; padding:0; }
.cf-step p { margin:0; font-size:13.5px; color:#475569; line-height:1.5; }
.cf-formula { margin-top:12px; text-align:center; font-size:17px; font-weight:700; color:#0F172A; background:#fff; border:1px dashed #CBD5E1; border-radius:14px; padding:12px; }
.cf-formula span { color:#0F766E; }
.cf-foot { margin-top:30px; font-size:12px; color:#94A3B8; text-align:center; }
</style>
"""

LOGO = ('<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.2" '
        'stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12z"/>'
        '<path d="M12 6.5v6M9 9.5h6"/></svg>')


def esc(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def _query(sql: str) -> pd.DataFrame:
    from databricks import sql as dbsql
    from databricks.sdk.core import Config

    cfg = Config()
    with dbsql.connect(server_hostname=cfg.host,
                       http_path=f"/sql/1.0/warehouses/{os.environ['DATABRICKS_WAREHOUSE_ID']}",
                       credentials_provider=lambda: cfg.authenticate) as conn, conn.cursor() as cur:
        cur.execute(sql)
        return cur.fetchall_arrow().to_pandas()


@st.cache_resource(show_spinner="Loading 10,088 facilities and checking every record…")
def load_finder() -> CareFinder:
    local = os.getenv("CAREFINDER_LOCAL_CSV")
    if local:
        pins_path = os.getenv("CAREFINDER_LOCAL_PINS")
        return CareFinder(pd.read_csv(local), pin_directory=pd.read_csv(pins_path) if pins_path else None)
    raw = _query(f"SELECT * FROM {FACILITY_TABLE}")
    pins = _query(f"SELECT officename, pincode, district, statename, latitude, longitude FROM {PIN_TABLE}") \
        if PIN_TABLE else None
    return CareFinder(raw, pin_directory=pins)


def pick(service: str, place: str):
    st.session_state.service = service
    st.session_state.place = place
    st.session_state.other = ""
    st.session_state.query = (service, place)


def submit():
    service = st.session_state.other.strip() or st.session_state.service
    st.session_state.query = (service, st.session_state.place)


def hero(finder: CareFinder):
    n = len(finder.facilities)
    st.markdown(
        f'<div class="cf-hero"><div class="cf-brand"><div class="cf-logo">{LOGO}</div><div>'
        f'<h1>CareFinder India</h1><p>Where can this patient get the care they need, and why should we trust it?</p>'
        f'</div></div><div class="cf-stats">'
        f'<div class="cf-stat"><b>{n:,}</b><span>facilities checked</span></div>'
        f'<div class="cf-stat"><b>{len(SERVICES)}</b><span>services</span></div>'
        f'<div class="cf-stat"><b>100%</b><span>answers cited</span></div></div></div>',
        unsafe_allow_html=True)


def card(r) -> str:
    fg, bg, border = TONE[r.confidence_label]
    place = ", ".join(x for x in (r.address, r.city, r.state, r.postcode) if isinstance(x, str) and x)
    core = [c for c in r.citations if c["kind"] == "core"]
    quotes = "".join(
        f'<div class="cf-q"><span class="cf-tag">{esc(c["field"])}</span><span>“{esc(c["text"])}”'
        + (' <em>· in a long list</em>' if c.get("listed") else "") + '</span></div>'
        for c in core[:3])
    more = len(core) - 3
    if more > 0:
        quotes += f'<div class="cf-q"><em>+ {more} more quote{"s" if more > 1 else ""} below</em></div>'
    if r.penalties:
        flags = '<div class="cf-flags bad">' + "".join(
            f'<div><b>−{p["pct"]}%</b> {esc(p["reason"][0].upper() + p["reason"][1:])}</div>' for p in r.penalties) + '</div>'
    else:
        flags = ('<div class="cf-flags ok"><b>✓ No red flags.</b> Location matches its address and the record '
                 'looks like a single facility.</div>')
    good = []
    if r.own_site:
        good.append(f"✓ Own website among sources ({esc(r.own_site)})")
    if r.specific:
        good.append("✓ Concrete detail (counts, beds or equipment)")
    if r.duplicates:
        good.append(f"{r.duplicates} duplicate record(s) merged")
    goods = '<div class="cf-good">' + "".join(f"<span>{g}</span>" for g in good) + '</div>' if good else ""
    contact = " · ".join(x for x in (
        f"☎ {esc(r.phone)}" if isinstance(r.phone, str) and r.phone else "",
        f'<a href="https://{esc(r.website)}" target="_blank">{esc(r.website)}</a>'
        if isinstance(r.website, str) and r.website and "://" not in r.website else
        (f'<a href="{esc(r.website)}" target="_blank">website</a>' if isinstance(r.website, str) and r.website else ""),
    ) if x)
    return (
        f'<div class="cf-card"><div class="cf-top"><div class="cf-rank">{r.rank}</div>'
        f'<div class="cf-title"><div class="cf-name">{esc(r.name)}</div><div class="cf-sub">{esc(place)}</div></div>'
        f'<div class="cf-pill" style="color:{fg};background:{bg};border-color:{border}"><i style="background:{fg}"></i>'
        f'{r.confidence_label} confidence · {r.confidence:.2f}</div></div>'
        f'<div class="cf-metrics">'
        f'<div class="cf-m"><span class="k">Distance</span><span class="v">{r.distance_km:.1f} km</span></div>'
        f'<div class="cf-m"><span class="k">Evidence</span><span class="v">{r.evidence_score:.2f}</span>'
        f'<div class="cf-bar"><i style="width:{r.evidence_score*100:.0f}%;background:#0F766E"></i></div></div>'
        f'<div class="cf-m"><span class="k">Trust</span><span class="v">{r.trust:.2f}</span>'
        f'<div class="cf-bar"><i style="width:{r.trust*100:.0f}%;background:{fg}"></i></div></div>'
        f'<div class="cf-m"><span class="k">Found in</span><span class="v s">{esc(r.evidence_fields) or "—"}</span></div>'
        f'</div><div class="cf-why-h">Why this facility: its own record says</div>{quotes}{flags}{goods}'
        + (f'<div class="cf-contact">{contact}</div>' if contact else "") + '</div>')


def deck(results: pd.DataFrame, loc) -> pdk.Deck:
    pts = results[["lat", "lon", "name", "rank", "distance_km", "confidence_label"]].dropna(subset=["lat", "lon"]).copy()
    pts["color"] = pts["confidence_label"].map(DOT)
    pts["label"] = pts["rank"].astype(str)
    pts["tip"] = pts.apply(lambda r: f"{r['rank']}. {r['name']} · {r.distance_km:.1f} km · {r.confidence_label}", axis=1)
    you = pd.DataFrame([{"lat": loc.lat, "lon": loc.lon, "tip": f"Patient: {loc.label}"}])
    lats = list(pts["lat"]) + [loc.lat]
    lons = list(pts["lon"]) + [loc.lon]
    mid_lat = (max(lats) + min(lats)) / 2
    # Fit the bounding box (with margin) into a ~400 x 430 px map; latitude spans stretch by 1/cos(lat) in Mercator.
    lon_span = max(max(lons) - min(lons), 0.01)
    lat_span = max(max(lats) - min(lats), 0.01) / math.cos(math.radians(mid_lat))
    zoom_lon = math.log2(400 * 360 / (512 * 1.5 * lon_span))  # deck.gl uses 512 px tiles
    zoom_lat = math.log2(430 * 360 / (512 * 1.5 * lat_span))
    zoom = max(3.5, min(13.0, min(zoom_lon, zoom_lat)))
    layers = [
        pdk.Layer("ScatterplotLayer", you, get_position="[lon, lat]", get_radius=1, radius_min_pixels=22,
                  get_fill_color=[37, 99, 235, 40], stroked=False, pickable=False),
        pdk.Layer("ScatterplotLayer", you, get_position="[lon, lat]", get_radius=1, radius_min_pixels=9,
                  get_fill_color=[37, 99, 235, 255], get_line_color=[255, 255, 255], line_width_min_pixels=3,
                  stroked=True, pickable=True),
        pdk.Layer("ScatterplotLayer", pts, get_position="[lon, lat]", get_radius=1, radius_min_pixels=13,
                  get_fill_color="color", get_line_color=[255, 255, 255], line_width_min_pixels=2, stroked=True,
                  pickable=True),
        pdk.Layer("TextLayer", pts, get_position="[lon, lat]", get_text="label", get_size=13,
                  get_color=[255, 255, 255], font_weight=800, get_alignment_baseline="'center'"),
    ]
    return pdk.Deck(layers=layers, map_provider="carto", map_style="light",
                    initial_view_state=pdk.ViewState(latitude=mid_lat, longitude=(max(lons) + min(lons)) / 2,
                                                     zoom=zoom),
                    tooltip={"text": "{tip}"})


def how_it_works(service=None):
    st.markdown(
        '<div class="cf-label">How we decide</div><div class="cf-steps">'
        '<div class="cf-step"><div class="no">1</div><h4>Evidence</h4><p>We search each facility\'s own record '
        '(procedures, equipment, capabilities, description) for the service. Each place it is stated counts as a '
        'separate witness, and every match is shown to you as a quote.</p></div>'
        '<div class="cf-step"><div class="no">2</div><h4>Trust</h4><p>We lower the score for red flags: coordinates '
        'that contradict the address, records that merge two hospitals, a clinic claiming hospital-only care, or text '
        'saying the service is planned or unavailable.</p></div>'
        '<div class="cf-step"><div class="no">3</div><h4>Distance</h4><p>Closer is better, on a scale that fits the '
        'service: about 25 km for an emergency room, 150 km for planned cardiac surgery. We always show the nearest '
        'option too, and why it ranked where it did.</p></div></div>'
        '<div class="cf-formula">rank = <span>evidence</span> × <span>trust</span> × '
        '<span>e<sup>−km ÷ scale</sup></span> &nbsp;·&nbsp; High ≥ 0.70 · Medium ≥ 0.45 · Low below</div>',
        unsafe_allow_html=True)
    with st.expander("Full method: every weight and trade-off"):
        st.markdown(method_markdown(service))


# ---------------------------------------------------------------------------------------------------------------
st.markdown(CSS, unsafe_allow_html=True)
for key, default in (("service", "Dialysis"), ("place", ""), ("other", ""), ("query", None)):
    st.session_state.setdefault(key, default)

finder = load_finder()
hero(finder)

st.markdown('<div class="cf-label">Find care</div>', unsafe_allow_html=True)
with st.form("search", border=False):
    c1, c2, c3 = st.columns([1.1, 1.3, 0.45], vertical_alignment="bottom")
    c1.selectbox("What care does the patient need?", LABELS, key="service")
    c2.text_input("Where is the patient?", key="place",
                  placeholder="Town, district, village, 6-digit PIN code, or lat, lon")
    c3.form_submit_button("Find care", on_click=submit, use_container_width=True)
    with st.expander("More options"):
        o1, o2, o3 = st.columns(3)
        o1.text_input("Or describe another service", key="other", placeholder="e.g. kidney transplant")
        top_k = o2.slider("How many options to show", 1, 10, 5)
        max_km = o3.slider("Furthest the patient can travel (km). 0 = let us decide", 0, 1000, 0, step=25)

ex_cols = st.columns([0.32] + [1] * len(EXAMPLES) + [1.6], vertical_alignment="center")
ex_cols[0].markdown('<div style="font-size:13px;color:#64748B;font-weight:600">Try</div>', unsafe_allow_html=True)
for col, (svc, place, label) in zip(ex_cols[1:], EXAMPLES):
    col.button(label, on_click=pick, args=(svc, place), use_container_width=True)

query = st.session_state.query
if not query:
    how_it_works()
else:
    service_query, place = query
    res = finder.search(service_query, place, top_k=top_k, max_km=max_km or None)
    if res.error:
        st.error(res.error)
    else:
        loc = res.location
        st.markdown(f'<div class="cf-results-h">{esc(res.service.label)} near {esc(loc.label)}</div>',
                    unsafe_allow_html=True)
        approx = f" · ±{loc.uncertainty_km:.0f} km" if loc.uncertainty_km else ""
        source = {"post office / town": "India Post directory", "PIN code": "India Post PIN directory",
                  "city": "facility addresses", "district": "India Post directory",
                  "coordinates": "your coordinates", "state": "state centre"}.get(loc.method, loc.method)
        st.markdown(
            '<div class="cf-chips">'
            f'<span class="cf-chip">📍 Located by <b>{esc(loc.method)}</b> via {esc(source)}{approx}</span>'
            f'<span class="cf-chip"><b>{res.candidates:,}</b> facilities mention {esc(res.service.label.lower())}</span>'
            f'<span class="cf-chip">Showing the best <b>{len(res.results)}</b></span></div>',
            unsafe_allow_html=True)
        for note in res.notes:
            kind = "trade" if ("nearest" in note or "closest" in note) else "warn"
            icon = "Trade-off" if kind == "trade" else "Heads up"
            st.markdown(f'<div class="cf-note {kind}"><span class="i">{icon}</span><span>{esc(note)}</span></div>',
                        unsafe_allow_html=True)

        results = res.results
        left, right = st.columns([1.65, 1], gap="large")
        with left:
            for r in results.itertuples():
                st.markdown(card(r), unsafe_allow_html=True)
                with st.expander(f"Full evidence, sources and unknowns for {r.name}"):
                    st.markdown(r.explanation)
        with right:
            st.pydeck_chart(deck(results, loc), use_container_width=True)  # no height kwarg on Streamlit 1.38
            st.markdown(
                '<div class="cf-legend"><span><i style="background:#2563EB"></i>Patient</span>'
                '<span><i style="background:#047857"></i>High</span><span><i style="background:#D97706"></i>Medium</span>'
                '<span><i style="background:#DC2626"></i>Low</span></div>', unsafe_allow_html=True)
            rows = "".join(
                f'<div class="cf-row"><span class="n" style="background:{TONE[r.confidence_label][0]}">{r.rank}</span>'
                f'<span class="nm">{esc(r.name)}</span><span class="km">{r.distance_km:.1f} km</span></div>'
                for r in results.itertuples())
            st.markdown(f'<div class="cf-side"><div class="cf-why-h">At a glance</div>{rows}</div>',
                        unsafe_allow_html=True)
            st.download_button("Download these results (JSON)", res.to_json(), file_name="carefinder_results.json",
                               use_container_width=True)
        how_it_works(res.service)

st.markdown('<div class="cf-foot">Data: Virtue Foundation facility dataset (DAIS 2026) and India Post PIN directory, '
            'via the Databricks Marketplace. Facility details come from public web pages and may be wrong: always '
            'call ahead.</div>', unsafe_allow_html=True)
