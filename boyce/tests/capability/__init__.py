"""
Capability Tests — "Does it think like a staff-level data engineer?"

These tests validate judgment, not just correctness. Engineering tests confirm that
parse() returns the right fields; capability tests confirm that the system warns you
when an equality filter silently drops 30% of your rows.

Each test scenario encodes a real-world trap that a junior analyst would miss
but a senior data engineer would catch.
"""
