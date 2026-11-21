# Databricks notebook source
# Shared setup, pulled into the other notebooks with %run ./_setup
import os
import sys

# Make the carefinder package (one folder up from notebooks/) importable.
_repo_root = os.path.abspath(os.path.join(os.getcwd(), ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

dbutils.widgets.text("source_catalog", "", "Marketplace catalog (blank = auto-detect)")
dbutils.widgets.text("target", "workspace.carefinder", "Where to write our tables")


def _find_source_catalog():
    given = dbutils.widgets.get("source_catalog").strip()
    if given:
        return given
    cats = [r[0] for r in spark.sql("SHOW CATALOGS").collect()]
    hits = [c for c in cats if "virtue" in c.lower() or "dais" in c.lower()]
    if not hits:
        raise ValueError(f"Couldn't find the Virtue Foundation catalog among {cats}. "
                         "Click 'Get instant access' on the Marketplace listing, or type the catalog name in the widget.")
    return hits[0]


SOURCE_CATALOG = _find_source_catalog()
TABLES = spark.sql(f"""
    SELECT table_schema, table_name FROM {SOURCE_CATALOG}.information_schema.tables
    WHERE table_schema <> 'information_schema'
""").toPandas()


def find_table(*keywords):
    for kw in keywords:
        m = TABLES[TABLES["table_name"].str.lower().str.contains(kw)]
        if len(m):
            r = m.iloc[0]
            return f"{SOURCE_CATALOG}.{r.table_schema}.{r.table_name}"
    return None


FACILITY_TABLE = find_table("facilit", "vf_", "virtue", "india")
PIN_TABLE = find_table("pincode", "pin_code", "pin")
NFHS_TABLE = find_table("nfhs")
TARGET = dbutils.widgets.get("target").strip()
print(f"facilities: {FACILITY_TABLE}\nPIN directory: {PIN_TABLE}\nNFHS-5: {NFHS_TABLE}\nwriting to: {TARGET}")
