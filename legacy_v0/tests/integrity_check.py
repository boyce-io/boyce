import sys
import os

# Simulate installing the package by adding src to path
sys.path.insert(0, os.path.abspath("src"))

print("--- Integrity Check ---")
try:
    import datashark
    print("✅ datashark package found")

    import datashark.semantic.parser
    print("✅ datashark.semantic found")

    import datashark.state.graph
    print("✅ datashark.state found")

    import datashark.agent_engine
    print("✅ datashark.agent_engine found")

    print("\nSUCCESS: All modules are unified under the 'datashark' namespace.")
except ImportError as e:
    print(f"\n❌ FAILURE: {e}")
    sys.exit(1)
