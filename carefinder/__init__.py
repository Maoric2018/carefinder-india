"""CareFinder: recommend Indian healthcare facilities for a service + location, with cited evidence.

The package is pure Python (pandas + numpy) so the same code runs in a Databricks notebook,
a Databricks App, and local tests.
"""

from .engine import CareFinder, SearchResult
from .taxonomy import SERVICES, find_service

__all__ = ["CareFinder", "SearchResult", "SERVICES", "find_service"]
