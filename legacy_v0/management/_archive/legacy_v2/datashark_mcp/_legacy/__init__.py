"""Legacy Code Quarantine.

This directory contains legacy modules that have been superseded by the
Safety Kernel architecture. These modules are preserved for reference
but should not be used in new code.

Legacy Modules:
- context/: Old implicit trust API (superseded by kernel/air_gap_api.py)
- agentic/: Old runtime (superseded by kernel/engine.py)
- semantic/: Old semantic graph (superseded by kernel/types.py)

All code in this directory violates the Air Gap architecture and should
not be imported by active code.
"""

__all__ = []





