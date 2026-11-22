# CareFinder India — CMU Datathon 2026 (Databricks × Virtue Foundation)

Input: a **service** (dialysis, emergency C-section, NICU, …) and a **location** (city, district, village,
PIN code or `lat, lon`). Output: the best facilities, each with **quoted evidence from its own record**,
a **confidence label**, the **caveats** that lowered it, and a plain-language **"how we decided"** section.

## Layout

| Path | What |
|---|---|
| `carefinder/` | Core engine (pure pandas; same code runs in notebooks, the app and tests) |
| `carefinder/taxonomy.py` | 22 services and the words that count as evidence (incl. LSCS, SNCU, CTVS, PMNDP, DOTS) |
| `carefinder/evidence.py` | Finds mentions per field (dedicated or inside a long list), skips negated or "coming soon" ones |
| `carefinder/model.py` | Latent class model fitted by EM: learns how much each field's mention and each red flag is worth, with bootstrap intervals |
| `carefinder/access.py` | Travel-time model: P(arriving within the service's clinical time window) |
| `carefinder/quality.py` | Record checks: coordinates vs city/PIN, merged records, facility type, claim lists too long for the facility's size, duplicates |
| `carefinder/geo.py` | Location lookup from the India Post PIN directory + facility data (no external geocoder) |
| `carefinder/engine.py` | Ranking, explanations, method text, facility × service evidence table |
| `carefinder/coverage.py` | Planner view: NFHS-5 district need × where well-documented care is (district centres from India Post) |
| `notebooks/01_explore_data.py` | Profile the real data, check the column mapping, count data-quality problems |
| `notebooks/02_build_tables.py` | Write `facilities_scored`, `facility_service_evidence`, `services` Delta tables (for Genie / dashboards) |
| `notebooks/03_find_care.py` | Widget-driven demo: pick a service, type a place, Run all |
| `app.py`, `app.yaml` | Streamlit Databricks App: **Find care** (one patient) and **Plan coverage** (districts) tabs |
| `tests/` | Synthetic messy data + tests (`make_sample.py` is NOT real data) |

## How a recommendation is scored

No hand-set weights: the numbers are learned from the 10,088 records, and each one comes with its uncertainty.

1. **Does it offer the service? A latent class model.** There is no ground truth saying which facilities really
   offer dialysis, so a supervised classifier is not possible. Instead, each part of a record is a noisy witness:
   six fields (procedures, equipment, capabilities, description, name, specialties), each with no mention, a
   mention inside a long list, or a dedicated mention, plus three signals (only related words, the text says
   unavailable or planned, concrete detail such as machine counts). Following Dawid & Skene (1979), the label model
   behind Snorkel, the true answer Y is a hidden class and expectation-maximization learns, per service, how often
   each witness speaks up when Y = 1 and when Y = 0, from how the witnesses agree. The result is a likelihood ratio
   per witness (dialysis: a dedicated capabilities entry ×120, a mention inside a list ×15) and a base rate
   (dialysis: 8.1% of records), combined by Bayes' rule into P(offers it | its record).
2. **Red flags are learned too.** Record problems (a clinic claiming a hospital-level service, a pharmacy or
   dental listing, a possible merged record, a corrupted row, no source URL, no own website, too few beds) enter as
   covariates on the prior (latent class regression, Bandeen-Roche et al. 1997). Their odds ratios are learned
   (burn care: a clinic ×0.06; dialysis: no source URL ×0.19) and constrained to ≤ 1, so a flag can only lower
   confidence. Signal directions are constrained the same way, and a Dirichlet(1) prior keeps rare patterns finite.
3. **Correlated fields are not double counted.** Scraped fields can copy each other. We estimate the
   within-class correlation ρ between field mentions and divide the fields' combined log-likelihood ratio by the
   Kish design effect 1 + (k − 1)ρ (dialysis: ρ = 0.03, so the conditional-independence assumption roughly holds).
4. **Uncertainty.** The whole model is refitted on 100 bootstrap resamples of the facilities, giving a 90% interval
   for every probability (one Pune hospital that lists burns once: 0.49, interval 0.06–0.73). The app never prints
   1.00: it shows ≥0.99. Labels: High ≥ 0.80, Medium ≥ 0.50, else Low.
5. **Can the patient get there in time?** Travel time = 1.4 × straight-line km ÷ 35 km/h, log-normal with
   log-sd 0.35 plus location uncertainty (a facility placed at its city centre is ±8 km), and
   P(arrives in time) = P(travel time ≤ the service's clinical window): 2 h for C-sections and emergency obstetrics
   (Lancet Commission on Global Surgery), 1 h for trauma and emergencies (golden hour), 1 h one way for dialysis
   (DOPPS), 2 h for a cath lab (STEMI guidelines), 4–6 h for planned care (our assumption). The detour factor and
   speed are assumptions, shown in the app.
6. **Rank** = P(offers it | its record) × P(arrives in time). We always also report the *nearest* facility that
   mentions the service, if it ranked lower, and why.

Limitations: the model learns from agreement, so if every field of a record copies the same false claim it will
still look strong (that is what the record checks and the interval are for); conditional independence is only
approximately true; and the travel model has no road network.

## Run locally (synthetic data)

```bash
uv run --with pandas --with numpy --with pytest python -m pytest tests -q
```

```bash
CAREFINDER_LOCAL_CSV=tests/sample_facilities.csv CAREFINDER_LOCAL_PINS=tests/sample_pins.csv CAREFINDER_LOCAL_NFHS=tests/sample_nfhs.csv uv run --with streamlit==1.38.0 --with pandas --with numpy streamlit run app.py
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

## Plan coverage (for planners)

The app's second tab joins all three Marketplace tables. For a service and a state it places every NFHS-5 district
at the centre of its India Post post offices (Census-2011 names such as "Pashchim Champaran" are matched to India
Post names through direction words, known renames and fuzzy matching), then marks it:

- **Covered**: a High-confidence facility for the service the district centre can probably reach within the
  service's time window (P(arrives in time) ≥ 0.5),
- **Only weak claims**: only Medium-confidence ones within reach,
- **Gap**: neither. A gap means no well-documented claim in this dataset, not proof the service is missing.

Districts are listed gaps first, then by need, using the NFHS-5 indicator that fits the service (C-section rate for
emergency C-sections, institutional births for NICU/maternity, high blood sugar for dialysis, high blood pressure for
cardiac care, cervical screening for cancer, health insurance otherwise). The tab also summarises what the data
checks found across all 10,088 records.

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
- Re-run `notebooks/02_build_tables.py` so the Genie tables use the learned model (they still hold the older scores).
- Spot-check 20 recommendations by hand (open their source URLs) to estimate the model's precision.
- Demo script: rural Bihar dialysis, Maharashtra high-risk delivery, highway trauma.
