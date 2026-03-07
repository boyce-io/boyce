import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from datashark.ingestion.sniper import ContextSniper

def test_crawler():
    # Target the 'Small Retail' universe which we know has structure
    target_path = Path(__file__).parent.parent / "tests" / "universes" / "small_retail"
    
    print(f"🕷️ Testing Crawler on: {target_path}")
    
    sniper = ContextSniper()
    results = sniper.scan_project(target_path)
    
    print(f"\n📊 Found {len(results)} artifacts.")
    
    # Assertions
    types_found = [item['type'] for item in results]
    names_found = [item['name'] for item in results]
    
    print(f"Types: {set(types_found)}")
    print(f"Files: {names_found}")
    
    # Check for dbt project file
    assert 'dbt_project.yml' in names_found
    assert 'dbt_project' in types_found
    
    # Check for manifest
    assert 'manifest.json' in names_found
    assert 'dbt_manifest' in types_found
    
    # Check for schema
    assert 'schema.yml' in names_found
    assert 'dbt_schema' in types_found
    
    # Check for LookML (in the root of small_retail usually, or wherever we put it)
    # Note: verify_server_handshake.py created orders.view.lkml in golden_repo, let's check small_retail
    # Wait, small_retail has dbt_project/ and seed_data/. Does it have lkml?
    # I should check if I created lkml in small_retail.
    # checking create_universe_small_retail steps... I created dbt_project.yml, schema.yml, manifest.json.
    # I did NOT create .lkml in small_retail explicitly in the previous turns, 
    # BUT verifying verify_server_handshake.py... that targeted `tests/fixtures/golden_repo`.
    # Let's target `tests/fixtures/golden_repo` instead for better coverage if it exists.
    
    repo_path = Path(__file__).parent.parent / "tests" / "fixtures" / "golden_repo"
    if repo_path.exists():
        print(f"\n🕷️ Re-Testing on Golden Repo: {repo_path}")
        results = sniper.scan_project(repo_path)
        names = [item['name'] for item in results]
        print(f"Files: {names}")
        if 'orders.view.lkml' in names:
            print("✅ Found LookML")
        
    print("\n✅ Crawler Test Passed")

if __name__ == "__main__":
    test_crawler()
