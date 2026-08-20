"""Utility services: cross-cutting concerns usable by any layer.

Security, configuration, diagnostics, the event bus, localisation. A utility must not
import a manager, engine, or resource access service — where it needs data, it receives
it as an argument.
"""
