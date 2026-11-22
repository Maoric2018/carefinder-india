# Databricks notebook source
# MAGIC %md
# MAGIC # 2 · Build the scored tables
# MAGIC Writes three Delta tables used by the Genie space, the dashboard and (optionally) the app:
# MAGIC - `facilities_scored`: every facility with its location quality and trust flags
# MAGIC - `facility_service_evidence`: one row per facility × service it claims, with evidence score, confidence and quoted citations
# MAGIC - `services`: the service list and the words that count as evidence for each

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

import json
import pandas as pd
from carefinder import CareFinder, SERVICES
from carefinder.engine import evidence_table, find_care_sql, places_table

raw = spark.table(FACILITY_TABLE).toPandas()
pins = spark.table(PIN_TABLE).toPandas() if PIN_TABLE else None
finder = CareFinder(raw, pin_directory=pins)

catalog, schema = TARGET.split(".")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")

# COMMAND ----------

f = finder.facilities.copy()
keep = ["id", "name", "kind", "facility_type", "address", "city", "district_n", "state", "state_n", "postcode",
        "lat", "lon", "coord_status", "loc_lat", "loc_lon", "loc_quality", "location_issue", "location_detail",
        "coord_shared_n", "pin_state_mismatch", "merge_reasons", "other_facilities", "corrupted", "own_site",
        "n_claims", "completeness", "dup_group", "dup_count", "capacity", "num_doctors", "year_established",
        "specialties", "capability", "procedure", "equipment", "description", "source_urls"]
out = f[keep].rename(columns={"district_n": "district", "state_n": "state_resolved"})
for c in ("merge_reasons", "other_facilities", "specialties", "capability", "procedure", "equipment", "source_urls"):
    out[c] = out[c].map(lambda v: json.dumps(list(v), ensure_ascii=False))
for c in ("lat", "lon", "loc_lat", "loc_lon", "capacity", "num_doctors", "year_established"):
    out[c] = pd.to_numeric(out[c], errors="coerce")
spark.createDataFrame(out).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{TARGET}.facilities_scored")
print(f"{TARGET}.facilities_scored: {len(out):,} rows")

# COMMAND ----------

ev = evidence_table(finder)  # takes a minute: every facility × every service
for c in ("lat", "lon"):
    ev[c] = pd.to_numeric(ev[c], errors="coerce")
spark.createDataFrame(ev).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{TARGET}.facility_service_evidence")
print(f"{TARGET}.facility_service_evidence: {len(ev):,} rows")
display(ev.groupby(["service_label", "confidence_label"]).size().unstack(fill_value=0))

# COMMAND ----------

from carefinder import access
svc = pd.DataFrame([{"service": s.key, "label": s.label, "core_terms": ", ".join(s.core),
                     "support_terms": ", ".join(s.support), "window_h": access.window(s.key)[0],
                     "window_basis": access.window(s.key)[1], "reach_km": round(access.reach_km(access.window(s.key)[0]), 1),
                     "needs_hospital": s.needs_hospital, "min_beds": s.min_beds} for s in SERVICES.values()])
spark.createDataFrame(svc).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{TARGET}.services")

# COMMAND ----------

# Place lookup (city / district / post office / PIN / state -> coordinates) and the ranking function for Genie.
places = places_table(finder)
spark.createDataFrame(places).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{TARGET}.places")
print(f"{TARGET}.places: {len(places):,} rows")
spark.sql(find_care_sql(TARGET))
display(spark.sql(f"SELECT option_rank, facility_name, city, distance_km, confidence_label, top_quote, caveats "
                  f"FROM {TARGET}.find_care('Dialysis', 'Bakhtiyarpur, Bihar')"))

# COMMAND ----------

# Column comments help Genie answer questions correctly.
comments = {
    "facility_service_evidence": {
        "evidence_score": "0-1. Probability the facility offers the service given only what its record text says (latent class model fitted by EM; field reliabilities learned from how often fields agree).",
        "trust": "Effect of record-quality flags (clinic for a hospital service, merged record, no sources, ...) on that probability, learned from the data: confidence / evidence_score.",
        "confidence": "Probability the facility offers the service given its record text and flags. High >= 0.80, Medium >= 0.50, otherwise Low. conf_lo-conf_hi is a 90% bootstrap interval.",
        "conf_lo": "Lower end of the 90% bootstrap interval for confidence.",
        "conf_hi": "Upper end of the 90% bootstrap interval for confidence.",
        "loc_sd_km": "How far off the facility location may be (km), from how it was placed.",
        "citations": "JSON list of quoted text from the facility record that supports the claim.",
        "caveats": "Record-quality flags with their learned odds multipliers, and location notes, separated by |.",
        "top_quote": "The strongest quote from the facility record that says it offers the service.",
        "district": "District (from the facility record, or from its PIN code via the India Post directory).",
        "state": "State, lower case (taken from the PIN code when the record's state field was not a real state).",
        "lat": "Latitude used for distances (facility coordinates if they agree with its address, else its PIN/city centre).",
    },
    "places": {
        "name": "Lower-case place name or 6-digit PIN code to look up.",
        "kind": "city, district, post office, pin or state.",
        "spread_km": "How spread out the place is; distances from it are approximate by about this much.",
    },
    "facilities_scored": {
        "loc_quality": "exact = facility coordinates agree with its address; PIN area / city centre = approximated.",
        "location_issue": "coords_fixed = coordinates contradicted city and PIN so the address was used; coords_conflict = unresolved; address_inconsistent = city or PIN disagrees.",
        "merge_reasons": "Signs the record merges more than one facility.",
        "corrupted": "True when the row's columns look shifted (e.g. a number in the facility type column).",
    },
}
for table, cols in comments.items():
    for col, text in cols.items():
        spark.sql(f"ALTER TABLE {TARGET}.{table} ALTER COLUMN {col} COMMENT '{text.replace(chr(39), '')}'")
