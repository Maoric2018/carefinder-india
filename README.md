# CareFinder India — CMU Datathon 2026 (Databricks × Virtue Foundation)

Input: a **service** (dialysis, emergency C-section, NICU, …) and a **location** (city, district, village,
PIN code or `lat, lon`). Output: the best facilities, each with **quoted evidence from its own record**,
a **confidence label**, the **caveats** that lowered it, and a plain-language **"how we decided"** section.

## Layout

| Path | What |
|---|---|
| `carefinder/` | Core engine (pure pandas; same code runs in notebooks, the app and tests) |
| `carefinder/taxonomy.py` | 22 services and the words that count as evidence (incl. LSCS, SNCU, CTVS, PMNDP, DOTS) |
| `carefinder/evidence.py` | Finds mentions, skips negated or "coming soon" ones, scores corroboration across fields |
| `carefinder/quality.py` | Record trust: coordinates vs city/PIN, merged records, facility type, claim lists too long for the facility's size, duplicates |
| `carefinder/geo.py` | Location lookup from the India Post PIN directory + facility data (no external geocoder) |
| `carefinder/engine.py` | Ranking, explanations, method text, facility × service evidence table |
| `notebooks/01_explore_data.py` | Profile the real data, check the column mapping, count data-quality problems |
| `notebooks/02_build_tables.py` | Write `facilities_scored`, `facility_service_evidence`, `services` Delta tables (for Genie / dashboards) |
| `notebooks/03_find_care.py` | Widget-driven demo: pick a service, type a place, Run all |
| `app.py`, `app.yaml` | Streamlit Databricks App for non-technical users |
| `tests/` | Synthetic messy data + tests (`make_sample.py` is NOT real data) |

## How a recommendation is scored

1. **Evidence (0–1):** each field that names the service (procedures 0.60, equipment 0.60, capabilities 0.55,
   name 0.50, description 0.45, specialties 0.40) is an independent "witness": `1 − ∏(1 − w)`. Related-only
   words count at 35%. Concrete detail (counts, bed numbers, brands) adds 0.25.
2. **Trust (multiplier):** ×0.60 coordinates contradict city/PIN · ×0.80 possible merged record · ×0.40
   pharmacy/dental listing · ×0.80 clinic for a hospital-level service · ×0.70 too few beds · ×0.70 own text
   says unavailable/planned/referred · ×0.85 PIN in wrong state · ×0.85 claim list too long for its size ·
   ×0.90 no source URL · ×0.88–0.90 position approximated.
3. **Confidence** = evidence × trust → High ≥ 0.70, Medium ≥ 0.45, else Low.
4. **Rank** = confidence × e^(−km / distance scale), scale per service (25 km ER … 150 km cardiac surgery).
   We always also report the *nearest* facility that mentions the service, if it was ranked lower, and why.

## Run locally (synthetic data)

```bash
uv run --with pandas --with numpy --with pytest python -m pytest tests -q
```

```bash
CAREFINDER_LOCAL_CSV=tests/sample_facilities.csv CAREFINDER_LOCAL_PINS=tests/sample_pins.csv uv run --with streamlit --with pandas --with numpy streamlit run app.py
```

## Run on Databricks Free Edition

1. Marketplace → **Virtue Foundation Dataset (DAIS 2026)** → **Get instant access**.
2. Put this folder in the workspace (Git folder from a GitHub repo, or Workspace → Import).
3. Run `notebooks/01_explore_data.py`. Check the printed column mapping. If a field is wrong, pass
   `column_overrides={"capacity": "real_column_name"}` to `CareFinder(...)`.
4. Run `notebooks/02_build_tables.py`, then try `notebooks/03_find_care.py`.
5. **Genie space** (optional): add `workspace.carefinder.facility_service_evidence` and `facilities_scored`.
6. **App:** Compute → Apps → Create → custom, source = this folder; add a SQL warehouse resource named
   `sql-warehouse`; set `FACILITY_TABLE` / `PIN_TABLE` in `app.yaml` to the names notebook 01 prints; grant the
   app's service principal `SELECT` on the Marketplace catalog.

## What we found in the real data (10,088 facilities, 51 columns)

- **List fields are JSON arrays of whole sentences** ("Dialysis treatment is provided via a 20-bed Dialysis Unit
  with 10 machines as part of the Pradhan Mantri National Dialysis Programme"), which makes them good citations.
- **Location is often contradictory.** Coordinates are >90 km from their own city for ~10% of records. Letting
  coordinates, city and PIN vote: 80% consistent · 591 coordinates corrected from the address (city + PIN agree) ·
  743 addresses internally inconsistent (a wrong PIN or city) · 677 unresolved · 88 with no location.
- **The state column is unreliable** ("Br", "Mumbai", "U P", "Kie"), so we take the state from the PIN directory.
  Only 43 records have a PIN in a different state from a valid listed state.
- **Records mix in text about other hospitals** scraped from directory pages ("Madras Medical Mission, Chennai is
  listed as a referral hospital…" inside Aravind Eye Hospital's record). Those sentences are excluded from evidence,
  and 772 records (~8%) whose claims name 3+ other facilities are flagged as possible merged records.
- **35 corrupted rows** with shifted columns (a latitude in `facilityTypeId`, a specialty list in
  `organization_type`), flagged and down-weighted.
- **71% of facilities** (7,198) have their own website among their sources, which we surface as a positive signal.
- Facilities with a direct mention of each service range from 134 (burn care) and 150 (TB) up to
  ~1,050 (dialysis) and ~5,400 (pediatrics).

## Live on Databricks Free Edition

- Git folder: `/Workspace/Users/<you>/carefinder-india` (synced from this repo)
- Tables: `workspace.carefinder.facilities_scored`, `facility_service_evidence` (42,515 rows), `services`
- App: `carefinder-india` (Compute → Apps), reading the Marketplace tables through the Serverless Starter Warehouse
- Genie space: **CareFinder India: find the right care** (Genie Agents). Tables `facility_service_evidence`,
  `facilities_scored`, `services`, `places`, plus the SQL function `workspace.carefinder.find_care(service, place)`,
  which ranks exactly like the app. Instructions: [genie/instructions.md](genie/instructions.md); sample questions:
  [genie/sample_questions.md](genie/sample_questions.md).
  - "Where can a patient get dialysis near Bakhtiyarpur, Bihar?" returns the same top 6 as the app, with quotes,
    phone numbers, caveats and a call-ahead warning.
  - "Which districts in Bihar have no High-confidence NICU?" returns 34 of 38 (only Darbhanga, Nawada, Patna and
    Saharsa have one), with the caveat that a missing claim is not proof of a missing NICU.

## Still to do

- Check the column mapping and the quality-check thresholds against the real data.
- Spot-check 20 recommendations by hand (open their source URLs) and tune the weights.
- Optional: NFHS-5 district context (e.g. district C-section rate) for planners.
- Demo script: rural Bihar dialysis, Maharashtra high-risk delivery, highway trauma.
