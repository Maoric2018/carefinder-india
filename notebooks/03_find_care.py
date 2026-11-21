# Databricks notebook source
# MAGIC %md
# MAGIC # 3 · Find care
# MAGIC Pick a service, type a location (city, district, village, PIN code or `lat, lon`), then **Run all**.
# MAGIC Every recommendation shows the quoted evidence and how sure we are.

# COMMAND ----------

# MAGIC %run ./_setup

# COMMAND ----------

from carefinder import SERVICES, CareFinder
from carefinder.engine import method_markdown

dbutils.widgets.dropdown("service", "Dialysis", [s.label for s in SERVICES.values()], "Service")
dbutils.widgets.text("location", "Patna", "Location")
dbutils.widgets.text("top_k", "5", "How many results")

try:
    finder  # reuse if already loaded in this session
except NameError:
    raw = spark.table(FACILITY_TABLE).toPandas()
    pins = spark.table(PIN_TABLE).toPandas() if PIN_TABLE else None
    finder = CareFinder(raw, pin_directory=pins)

# COMMAND ----------

from carefinder.render import md_to_html


def show_md(text):
    displayHTML(md_to_html(text))


res = finder.search(dbutils.widgets.get("service"), dbutils.widgets.get("location"),
                    top_k=int(dbutils.widgets.get("top_k") or 5))
show_md(res.to_markdown())

# COMMAND ----------

if len(res.results):
    display(res.results[["rank", "name", "city", "state", "distance_km", "confidence_label", "confidence",
                         "evidence_score", "trust", "evidence_fields", "location_quality"]])

# COMMAND ----------

show_md(method_markdown(res.service))
