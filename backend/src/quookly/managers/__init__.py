"""Manager services: the sequence of a use case family.

Managers hold workflow state and orchestrate. They do not compute — business rules
belong in engines. A manager must never import another manager; cross-manager
reactions go through the event bus (ADR-011).
"""
