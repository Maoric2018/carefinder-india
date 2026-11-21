# Databricks notebook source
# MAGIC %md
# MAGIC # 0 · Diagnostics (plain-text output for calibrating the quality checks)

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

import importlib
import numpy as np
import pandas as pd
import carefinder, carefinder.parse, carefinder.taxonomy, carefinder.evidence, carefinder.geo, carefinder.quality, carefinder.schema, carefinder.engine
for m in (carefinder.parse, carefinder.taxonomy, carefinder.evidence, carefinder.geo, carefinder.quality,
          carefinder.schema, carefinder.engine, carefinder):
    importlib.reload(m)
from carefinder import CareFinder

raw = spark.table(FACILITY_TABLE).toPandas()
pins = spark.table(PIN_TABLE).toPandas()
finder = CareFinder(raw, pin_directory=pins)
f = finder.facilities
pd.set_option("display.width", 250, "display.max_columns", 30, "display.max_colwidth", 80)

# COMMAND ----------

print("=== RAW FORMAT SAMPLES ===")
for col in ("specialties", "procedure", "equipment", "capability", "description", "source_urls", "facilityTypeId",
            "operatorTypeId", "organization_type", "capacity", "numberDoctors", "yearEstablished", "coordinates",
            "cluster_id", "recency_of_page_update", "address_city", "address_stateOrRegion", "address_zipOrPostcode"):
    vals = raw[col].dropna().astype(str)
    vals = vals[~vals.str.lower().isin(["", "null", "[]"])]
    print(f"\n-- {col}: {len(vals)} non-empty, {vals.nunique()} distinct")
    for v in vals.head(3):
        print("   ", v[:300])
for col in ("facilityTypeId", "operatorTypeId", "organization_type"):
    print(f"\n-- value counts {col}:\n", raw[col].value_counts(dropna=False).head(12).to_string())
print("\ncluster_id unique:", raw["cluster_id"].nunique(), "of", len(raw))
print("PIN dir rows:", len(pins), "geocoded PINs:", len(finder.pin_dir.pins), "districts:", len(finder.pin_dir.districts),
      "offices:", len(finder.pin_dir.offices))

# COMMAND ----------

print("=== LOCATION CONFLICTS ===")
c = f[f.coords_conflict]
by_city = c.conflict_detail.str.contains(" from (?!its PIN)", regex=True)
by_pin = c.conflict_detail.str.contains("from its PIN")
print("total", len(c), "| city-based", int(by_city.sum()), "| PIN-based", int(by_pin.sum()),
      "| both", int((by_city & by_pin).sum()))
print("km_from_city percentiles (all with a value):",
      np.nanpercentile(f.km_from_city.dropna().astype(float), [50, 75, 90, 95, 98, 99]).round(1))
pin_d = []
for r in f.itertuples():
    p = finder.pin_dir.pins.get(r.postcode)
    if p is not None and r.coord_status == "ok":
        pin_d.append(float(carefinder.geo.haversine_km(r.lat, r.lon, p.lat, p.lon)))
print("km from own PIN centre percentiles:", np.percentile(pin_d, [50, 75, 90, 95, 98, 99]).round(1), "n=", len(pin_d))
print("PIN spread_km percentiles:", np.percentile([p.spread_km for p in finder.pin_dir.pins.values()], [50, 90, 99]).round(1))
print(c[["name", "city", "state", "postcode", "lat", "lon", "conflict_detail"]].sample(25, random_state=1).to_string())

# COMMAND ----------

print("=== PIN / STATE MISMATCH ===")
m = f[f.pin_state_mismatch]
print(m[["name", "city", "state", "state_n", "postcode"]].head(20).to_string())
print("\nstate_n values not in PIN directory states:")
known = set(finder.pin_dir.rows.state.dropna())
print(f.state_n[~f.state_n.isin(known)].value_counts().head(20).to_string())

# COMMAND ----------

print("=== CLAIM LIST SIZES ===")
print(f.groupby("kind")["n_claims"].describe(percentiles=[.5, .75, .9, .95, .99]).round(0).to_string())
for col in ("specialties", "procedure", "equipment", "capability"):
    print(col, "items per record percentiles:", np.percentile(f[col].map(len), [50, 90, 99]).round(0))
print(f.sort_values("n_claims", ascending=False)[["name", "kind", "capacity", "num_doctors", "n_claims"]].head(10).to_string())

# COMMAND ----------

print("=== MERGED / DUPLICATES ===")
print(f[f.merge_reasons.map(bool)][["name", "city", "state", "merge_reasons"]].head(15).to_string())
print(f[f.dup_count > 0].sort_values("dup_group")[["name", "city", "postcode", "dup_group"]].head(15).to_string())

# COMMAND ----------

print("=== SEARCHES ===")
for svc, loc in [("dialysis", "Patna"), ("emergency c-section", "Nagpur"), ("NICU", "Lucknow"),
                 ("trauma", "Jaipur"), ("cardiac surgery", "Bhubaneswar"), ("MRI", "Gaya"), ("dialysis", "Bakhtiyarpur"),
                 ("burn care", "411001")]:
    res = finder.search(svc, loc, top_k=3)
    print("\n" + "#" * 100)
    print(res.to_markdown()[:3500])

# COMMAND ----------

print("=== SERVICE COVERAGE (facilities with a direct mention / High confidence) ===")
from carefinder.engine import confidence_label
for s in carefinder.SERVICES.values():
    evs = finder.evidence_for(s)
    n = sum(e.has_core for e in evs)
    print(f"{s.label:35s} {n:6d}")
