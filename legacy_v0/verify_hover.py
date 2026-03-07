# File: verify_hover.py
import sys
import os

# Ensure we can import datashark (src/ on path)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from datashark.interface.server import create_server, hover
from datashark.state.graph import NodeGraph, Node, SchemaInfo, Dependency
from lsprotocol.types import HoverParams, TextDocumentIdentifier

def run_check():
    print("🦈 Initializing DataShark Dry Run...")

    # 1. Setup the Brain (Graph)
    graph = NodeGraph()
    
    # 2. Mock a Node with Meaning (Description + Caveats)
    # NOTE: I am explicitly trying to use 'columns' here to check for regression
    try:
        schema = SchemaInfo(schema_name="analytics", table_name="stg_users")
        # If columns exist in your code, we'd add them here. 
        # For now, let's see if the hover logic breaks or just omits them.
    except Exception as e:
        print(f"❌ SchemaInfo Error: {e}")
        return

    dummy_node = Node(
        name="stg_users",
        file_path="/abs/path/to/test_caveat.sql",
        schema_info=schema,
        dependencies=[Dependency(ref_id="raw_users", source_file="N/A")],
        raw_content="SELECT * ...",
        description="The MAIN users table.",
        caveats=["Excludes test accounts.", "Do not join with leads."]
    )
    
    # Add to graph using the normalized path logic
    graph.add_node(dummy_node)
    
    # 3. Setup the Mouth (Server)
    server = create_server("datashark-test", "0.1")
    server.datashark_graph = graph

    # 4. Simulate the Hover Request
    # We pretend the user is hovering over 'test_caveat.sql'
    params = HoverParams(
        text_document=TextDocumentIdentifier(uri="file:///abs/path/to/test_caveat.sql"),
        position=None # Position doesn't matter for our current logic, just the file uri
    )

    print("\n👇 Sending Hover Request...")
    result = hover(server, params)

    if result and result.contents:
        print("\n✅ SUCCESS! Received Markdown Output:\n")
        print("---------------------------------------------------")
        print(result.contents.value)
        print("---------------------------------------------------")
        
        # Check for Caveats
        if "⚠️ CAVEATS" in result.contents.value:
            print("\n🟢 MEANING LAYER DETECTED.")
        else:
            print("\n🔴 MEANING LAYER MISSING.")
            
    else:
        print("\n❌ FAILURE: No hover content returned.")

if __name__ == "__main__":
    run_check()
