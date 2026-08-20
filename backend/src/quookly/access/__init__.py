"""Resource access services: access to a resource, expressed in domain verbs.

Interfaces speak the domain, not the storage model. SQLModel types live here and never
cross upward; what leaves this layer belongs to `quookly.contracts` (ADR-018).
"""
