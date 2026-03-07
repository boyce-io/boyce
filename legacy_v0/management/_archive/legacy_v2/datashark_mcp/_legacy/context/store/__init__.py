# Store package - re-exports GraphStore from parent store.py
import sys
from pathlib import Path

# Import GraphStore from parent store.py
parent_dir = Path(__file__).parent.parent
store_py = parent_dir / "store.py"

if store_py.exists():
    # Import GraphStore from the parent store.py file
    import importlib.util
    spec = importlib.util.spec_from_file_location("datashark_mcp.context.store_module", store_py)
    store_module = importlib.util.module_from_spec(spec)
    sys.modules["datashark_mcp.context.store_module"] = store_module
    spec.loader.exec_module(store_module)
    GraphStore = store_module.GraphStore
    __all__ = ["GraphStore"]
else:
    raise ImportError("store.py not found")
