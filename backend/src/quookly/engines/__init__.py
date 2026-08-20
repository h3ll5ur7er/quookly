"""Engine services: stateless business activities.

Rule engines (measure, suitability, nutrition, planning, replenishment, scoring,
execution, onboarding) are pure functions and must not perform I/O — reference data
arrives as arguments. Capability engines (interpretation, generation, ranking) mediate
one external capability each and may call resource access.
"""
