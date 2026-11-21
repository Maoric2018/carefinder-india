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
from carefinder.coverage import (DEFAULT_NEED, INDICATORS, SERVICE_NEED, audit_summary, coverage, facility_confidence,
                                 place_districts, prepare_nfhs)
from carefinder.engine import method_markdown

st.set_page_config(page_title="CareFinder India", page_icon="🩺", layout="wide")

FACILITY_TABLE = os.getenv("FACILITY_TABLE", "")
PIN_TABLE = os.getenv("PIN_TABLE", "")
NFHS_TABLE = os.getenv("NFHS_TABLE", "")
BY_LABEL = {s.label: s for s in SERVICES.values()}
STATUS = {  # status -> (label, text colour, background, border, map RGB)
    "gap": ("No well-documented option", "#B91C1C", "#FEF2F2", "#FECACA", [220, 38, 38]),
    "weak evidence only": ("Only weak claims", "#B45309", "#FFFBEB", "#FDE68A", [217, 119, 6]),
    "covered": ("Covered", "#047857", "#ECFDF5", "#A7F3D0", [4, 120, 87]),
    "not placed": ("Not on map", "#475569", "#F1F5F9", "#E2E8F0", [148, 163, 184]),
}
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
div[data-testid="stTabs"] button[role="tab"] p { font-size:16px; font-weight:700; }
div[data-testid="stTabs"] [data-baseweb="tab-list"] { gap:18px; margin-top:10px; }
.cf-intro { font-size:14.5px; color:#475569; margin:0 0 10px; line-height:1.5; }
.cf-kpis { display:grid; grid-template-columns: repeat(4, 1fr); gap:12px; margin:14px 0 6px; }
.cf-kpi { background:#fff; border:1px solid #E5E7EB; border-radius:14px; padding:12px 14px; }
.cf-kpi b { display:block; font-size:24px; font-weight:800; color:#0F172A; letter-spacing:-.02em; line-height:1.15; }
.cf-kpi b.red { color:#B91C1C; }
.cf-kpi b.sm { font-size:19px; }
.cf-kpi span { display:block; font-size:12.5px; color:#64748B; margin-top:4px; line-height:1.35; }
.cf-prow { display:flex; align-items:center; gap:12px; padding:10px 2px; border-top:1px solid #F1F5F9; }
.cf-prow:first-child { border-top:none; }
.cf-prow .n { width:26px; height:26px; border-radius:8px; color:#fff; font-size:12.5px; font-weight:800; display:flex; align-items:center; justify-content:center; flex:none; }
.cf-prow .d { flex:1; min-width:0; }
.cf-prow .d b { font-size:15px; color:#0F172A; }
.cf-prow .d small { display:block; font-size:12.5px; color:#64748B; margin-top:2px; line-height:1.35; }
.cf-prow .need { width:150px; flex:none; font-size:12px; color:#475569; text-align:right; }
.cf-prow .need .cf-bar { margin-top:4px; }
.cf-st { display:inline-block; vertical-align:2px; margin-left:6px; font-size:11px; font-weight:700; border:1px solid; border-radius:999px; padding:1px 8px; }
.cf-audit { display:grid; grid-template-columns: repeat(6, 1fr); gap:10px; margin-top:8px; }
.cf-audit div { background:#fff; border:1px solid #E5E7EB; border-radius:12px; padding:10px 12px; }
.cf-audit b { display:block; font-size:20px; font-weight:800; color:#0F172A; }
.cf-audit span { font-size:12px; color:#64748B; line-height:1.3; display:block; margin-top:2px; }
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


@st.cache_resource(show_spinner="Joining NFHS-5 district health indicators and placing every district…")
def load_districts(_finder: CareFinder) -> pd.DataFrame | None:
    local = os.getenv("CAREFINDER_LOCAL_NFHS")
    if local:
        raw = pd.read_csv(local)
    elif NFHS_TABLE:
        raw = _query(f"SELECT * FROM {NFHS_TABLE}")
    else:
        return None
    return place_districts(prepare_nfhs(raw), _finder)


@st.cache_data(show_spinner=False)
def facilities_for(service_key: str) -> pd.DataFrame:
    return facility_confidence(finder, SERVICES[service_key])


@st.cache_data(show_spinner=False)
def audit() -> dict:
    return audit_summary(finder)


def need_options(service_key: str) -> list[str]:
    first = list(SERVICE_NEED.get(service_key, DEFAULT_NEED))
    return first + [k for k in INDICATORS if k not in first]


def reset_need():
    st.session_state.plan_need = need_options(BY_LABEL[st.session_state.plan_service].key)[0]


def coverage_deck(cov: pd.DataFrame, fac: pd.DataFrame) -> pdk.Deck:
    pts = cov.dropna(subset=["lat", "lon"]).copy()
    pts["color"] = pts["status"].map(lambda s: STATUS[s][4] + [215])
    pts["radius"] = 7 + 15 * pts["need_pct"].fillna(0.3)
    pts["tip"] = [
        f"{d} · {STATUS[s][0]}" + (f" · nearest well-documented: {n} ({k:.0f} km)" if isinstance(n, str) else "")
        + (f" · need: {v:.1f}%" if v == v else "")
        for d, s, n, k, v in zip(pts["district"], pts["status"], pts["nearest_high"], pts["nearest_high_km"], pts["need_value"])]
    lats, lons = pts["lat"].astype(float), pts["lon"].astype(float)
    mid_lat = (lats.max() + lats.min()) / 2
    lon_span = max(lons.max() - lons.min(), 0.3)
    lat_span = max(lats.max() - lats.min(), 0.3) / math.cos(math.radians(mid_lat))
    zoom = max(3.4, min(9.0, min(math.log2(560 * 360 / (512 * 1.25 * lon_span)), math.log2(520 * 360 / (512 * 1.25 * lat_span)))))
    near = fac[(fac["label"] == "High") & fac["lat"].between(lats.min() - 1.5, lats.max() + 1.5)
               & fac["lon"].between(lons.min() - 1.5, lons.max() + 1.5)].copy() if len(fac) else fac
    if len(near):
        near["tip"] = "Well-documented: " + near["name"].astype(str)
    layers = [
        pdk.Layer("ScatterplotLayer", pts, get_position="[lon, lat]", get_radius="radius", radius_units="'pixels'",
                  get_fill_color="color", get_line_color=[255, 255, 255], line_width_min_pixels=1.5, stroked=True,
                  pickable=True),
    ]
    if len(near):
        layers.append(pdk.Layer("ScatterplotLayer", near, get_position="[lon, lat]", get_radius=1, radius_min_pixels=3.5,
                                get_fill_color=[15, 23, 42, 230], pickable=True))
    return pdk.Deck(layers=layers, map_provider="carto", map_style="light",
                    initial_view_state=pdk.ViewState(latitude=mid_lat, longitude=(lons.max() + lons.min()) / 2, zoom=zoom),
                    tooltip={"text": "{tip}"})


def planner(districts: pd.DataFrame | None):
    st.markdown('<div class="cf-label">Plan coverage</div><p class="cf-intro">For NGO coordinators and district '
                'planners: where is well-documented care missing, and where is the need highest? Need comes from '
                'India\'s National Family Health Survey (NFHS-5, 2019-21), district by district.</p>',
                unsafe_allow_html=True)
    if districts is None:
        st.info("The planner needs the NFHS-5 district table (set NFHS_TABLE).")
        return
    states = sorted(districts["state_label"].dropna().unique())
    st.session_state.setdefault("plan_service", "Emergency C-section")
    st.session_state.setdefault("plan_state", "Bihar" if "Bihar" in states else states[0])
    st.session_state.setdefault("plan_need", need_options(BY_LABEL[st.session_state.plan_service].key)[0])
    c1, c2, c3 = st.columns([1.1, 0.9, 1.4])
    c1.selectbox("Service", LABELS, key="plan_service", on_change=reset_need)
    c2.selectbox("State or union territory", ["All India"] + states, key="plan_state")
    service = BY_LABEL[st.session_state.plan_service]
    c3.selectbox("Need indicator (NFHS-5)", need_options(service.key), key="plan_need",
                 format_func=lambda k: INDICATORS[k].label)
    need = INDICATORS[st.session_state.plan_need]
    state = st.session_state.plan_state

    fac = facilities_for(service.key)
    pool = districts if state == "All India" else districts[districts["state_label"] == state]
    cov = coverage(pool, fac, service, need.key)
    placed = cov[cov["status"] != "not placed"]
    n_gap = int((placed["status"] != "covered").sum())
    median_km = placed["nearest_high_km"].median()
    in_state = fac if state == "All India" else fac[fac["state"] == pool["state"].iloc[0]] if len(fac) and len(pool) else fac
    n_high_state = int((in_state["label"] == "High").sum()) if len(in_state) else 0
    worst = cov.dropna(subset=["need_value"]).sort_values("need_pct", ascending=False).head(1)
    worst_txt = (f"{worst['district'].iloc[0]}: {worst['need_value'].iloc[0]:.1f}%" if len(worst) else "n/a")
    noun = service.label.lower()
    st.markdown(
        '<div class="cf-kpis">'
        f'<div class="cf-kpi"><b class="red">{n_gap} of {len(placed)}</b><span>districts with no well-documented '
        f'{esc(noun)} within {service.travel_km:.0f} km of their centre</span></div>'
        f'<div class="cf-kpi"><b>{(f"{median_km:.0f} km" if median_km == median_km else "n/a")}</b><span>median distance from a district centre to the nearest '
        f'well-documented {esc(noun)}</span></div>'
        f'<div class="cf-kpi"><b>{n_high_state}</b><span>facilities with a High-confidence {esc(noun)} claim in '
        f'{esc(state)}</span></div>'
        f'<div class="cf-kpi"><b class="sm">{esc(worst_txt)}</b><span>highest need: {esc(need.label.lower())}'
        f'{" (low = more need)" if need.need_when == "low" else ""}</span></div></div>',
        unsafe_allow_html=True)

    left, right = st.columns([1.1, 1], gap="large")
    with left:
        st.markdown('<div class="cf-why-h" style="margin-top:12px">Priority districts: gaps first, highest need first</div>',
                    unsafe_allow_html=True)
        top = cov.head(10)
        vmax = max(float(cov["need_value"].max() or 1), 1.0)
        rows = []
        for i, r in enumerate(top.itertuples(), 1):
            label, fg, bg, border, _ = STATUS[r.status]
            near = (f"Nearest well-documented: {esc(r.nearest_high)} · {r.nearest_high_km:.0f} km"
                    if isinstance(r.nearest_high, str) else "No well-documented facility found")
            near += f" · {r.medium_within} weaker claim{'s' if r.medium_within != 1 else ''} within reach" if r.medium_within else ""
            need_html = (f'{need.label.split(" (")[0]}: <b>{r.need_value:.1f}%</b><div class="cf-bar">'
                         f'<i style="width:{100 * r.need_value / vmax:.0f}%;background:{fg}"></i></div>'
                         if r.need_value == r.need_value else "no NFHS value")
            rows.append(f'<div class="cf-prow"><span class="n" style="background:{fg}">{i}</span>'
                        f'<div class="d"><b>{esc(r.district)}</b>{", " + esc(r.state_label) if state == "All India" else ""}'
                        f' <span class="cf-st" style="color:{fg};background:{bg};border-color:{border}">{label}</span>'
                        f'<small>{near}</small></div>'
                        f'<div class="need">{need_html}</div></div>')
        st.markdown(f'<div class="cf-side" style="margin-top:4px">{"".join(rows)}</div>', unsafe_allow_html=True)
    with right:
        if len(placed):
            st.pydeck_chart(coverage_deck(cov, fac), use_container_width=True)
        legend = "".join(f'<span><i style="background:rgb{tuple(STATUS[s][4])}"></i>{STATUS[s][0]}</span>'
                         for s in ("gap", "weak evidence only", "covered"))
        st.markdown(f'<div class="cf-legend">{legend}<span><i style="background:#0F172A"></i>Well-documented facility</span>'
                    '<span>Bigger circle = more need</span></div>', unsafe_allow_html=True)

    unplaced = cov[cov["status"] == "not placed"]["district"].tolist()
    st.markdown(
        f'<div class="cf-note trade"><span class="i">How to read this</span><span><b>Covered</b> means a facility '
        f'with a High-confidence {esc(noun)} claim is within {service.travel_km:.0f} km of the district centre (the '
        f'same distance scale the search uses). <b>Only weak claims</b> means only Medium-confidence ones are. A gap '
        f'means no well-documented claim in this dataset, which is not proof the service is missing: verify locally. '
        f'District centres come from India Post post offices.'
        + (f' {len(unplaced)} district(s) could not be placed: {esc(", ".join(unplaced[:8]))}'
           + ("…" if len(unplaced) > 8 else "") + '.' if unplaced else '') + '</span></div>',
        unsafe_allow_html=True)
    with st.expander(f"All {len(cov)} districts as a table"):
        table = cov[["district", "state_label", "status", "nearest_high", "nearest_high_km", "high_within",
                     "medium_within", "need_value", "placed_by"]].rename(columns={
            "district": "District", "state_label": "State", "status": "Status",
            "nearest_high": "Nearest well-documented facility", "nearest_high_km": "Distance (km)",
            "high_within": f"High within {service.travel_km:.0f} km", "medium_within": f"Medium within {service.travel_km:.0f} km",
            "need_value": f"{need.label} (%)", "placed_by": "District centre from"})
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.download_button("Download this table (CSV)", table.to_csv(index=False),
                           file_name=f"carefinder_coverage_{service.key}_{state.replace(' ', '_').lower()}.csv")

    a = audit()
    st.markdown(
        '<div class="cf-label">What we checked in the data</div><div class="cf-audit">'
        f'<div><b>{a["records"]:,}</b><span>facility records read and checked</span></div>'
        f'<div><b>{a["location_fixed"]:,}</b><span>coordinates contradicted the address; re-placed by address</span></div>'
        f'<div><b>{a["location_conflict"] + a["address_inconsistent"]:,}</b><span>locations we could not confirm (shown with a penalty)</span></div>'
        f'<div><b>{a["merged"]:,}</b><span>records that mix in other hospitals</span></div>'
        f'<div><b>{a["duplicates"]:,}</b><span>records with a duplicate elsewhere (merged)</span></div>'
        f'<div><b>{a["corrupted"]:,}</b><span>corrupted rows (shifted columns)</span></div></div>',
        unsafe_allow_html=True)


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

tab_find, tab_plan = st.tabs(["Find care for a patient", "Plan coverage across districts"])
with tab_find:
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

with tab_plan:
    try:
        district_table = load_districts(finder)
    except Exception as exc:  # e.g. the app's service principal cannot read the NFHS table yet
        district_table = None
        st.error(f"Could not load the NFHS-5 district table: {exc}")
    planner(district_table)

st.markdown('<div class="cf-foot">Data: Virtue Foundation facility dataset (DAIS 2026), India Post PIN directory and NFHS-5 '
            'district health indicators, '
            'via the Databricks Marketplace. Facility details come from public web pages and may be wrong: always '
            'call ahead.</div>', unsafe_allow_html=True)
