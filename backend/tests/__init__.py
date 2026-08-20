"""Tests are a package so two files may share a basename in different directories.

`engines/test_exchange.py` and `managers/test_exchange.py` test two sides of the same
feature and should be allowed to say so; without `__init__.py` both pytest and mypy
resolve them to one module name and refuse.
"""
