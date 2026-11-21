# Databricks notebook source
# MAGIC %md
# MAGIC # 1 · Explore the facility data
# MAGIC What columns do we have, how complete are they, and how messy is the data?
# MAGIC Run this first; it also checks that the column auto-detection found the right fields.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

display(TABLES)

# COMMAND ----------

raw_sdf = spark.table(FACILITY_TABLE)
print(f"{raw_sdf.count():,} rows, {len(raw_sdf.columns)} columns")
raw_sdf.printSchema()

# COMMAND ----------

# Share of non-empty values per column (empty strings, 'null' and [] count as missing).
from pyspark.sql import functions as F

def _filled(c, dtype):
    col = F.col(f"`{c}`")
    if dtype.startswith("array"):
        return F.when(col.isNotNull() & (F.size(col) > 0), 1).otherwise(0)
    if dtype == "string":
        return F.when(col.isNotNull() & ~F.lower(F.trim(col)).isin("", "null", "none", "[]", "nan"), 1).otherwise(0)
    return F.when(col.isNotNull(), 1).otherwise(0)

cov = raw_sdf.select([F.avg(_filled(c, t)).alias(c) for c, t in raw_sdf.dtypes]).toPandas().T
cov.columns = ["coverage"]
display(cov.sort_values("coverage", ascending=False).reset_index().rename(columns={"index": "column"}))

# COMMAND ----------

display(raw_sdf.limit(20))

# COMMAND ----------

# MAGIC %md ## Check the column mapping and run the quality checks

# COMMAND ----------

import pandas as pd
from carefinder import CareFinder

raw = raw_sdf.toPandas()
pins = spark.table(PIN_TABLE).toPandas() if PIN_TABLE else None
finder = CareFinder(raw, pin_directory=pins)
print("Column mapping (logical -> actual):")
for k, v in finder.mapping.items():
    print(f"  {k:16s} -> {v}")

# COMMAND ----------

f = finder.facilities
summary = {
    "facilities": len(f),
    "coordinates ok": int((f.coord_status == "ok").sum()),
    "coordinates swapped (fixed)": int((f.coord_status == "swapped").sum()),
    "coordinates missing / outside India": int(f.coord_status.isin(["missing", "outside_india"]).sum()),
    "coordinates wrong, fixed from address (city + PIN agree)": int((f.location_issue == "coords_fixed").sum()),
    "location unresolved (signals disagree)": int((f.location_issue == "coords_conflict").sum()),
    "address internally inconsistent (city or PIN off)": int((f.location_issue == "address_inconsistent").sum()),
    "coordinates shared by 3+ facilities (placeholder)": int((f.loc_quality == "shared coordinates").sum()),
    "PIN in wrong state": int(f.pin_state_mismatch.sum()),
    "possible merged records": int(f.merge_reasons.map(bool).sum()),
    "corrupted rows (shifted columns)": int(f.corrupted.sum()),
    "has its own website among sources": int(f.own_site.notna().sum()),
    "records with duplicates": int((f.dup_count > 0).sum()),
    "no location at all": int((f.loc_quality == "unknown").sum()),
}
display(pd.DataFrame(summary.items(), columns=["check", "facilities"]))
display(f["kind"].value_counts().reset_index())

# COMMAND ----------

# Examples of each problem, to eyeball whether the checks are right.
cols = ["name", "city", "state", "postcode", "lat", "lon", "location_issue", "location_detail", "merge_reasons", "kind"]
display(f[f.coords_conflict][cols].head(20))
display(f[f.merge_reasons.map(bool)][cols].head(20))
