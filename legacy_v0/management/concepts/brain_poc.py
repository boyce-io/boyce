import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

# Load Env
load_dotenv()

# Import Brain
try:
    from datashark.agent.brain import DataSharkBrain
except ImportError as e:
    print(f"❌ Import Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

def main():
    print("🧠 DataShark Brain POC (In-House RAG)")
    print("-------------------------------------")

    # 1. Initialize
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY not found in .env")
        return

    try:
        brain = DataSharkBrain(api_key=api_key)
        print("✅ Brain Initialized (ChromaDB + OpenAI)")
    except Exception as e:
        print(f"❌ Initialization Failed: {e}")
        return

    # 2. Train
    print("\n📚 Training...")
    finance_ddl = """
    CREATE TABLE finance_metrics (
        date DATE,
        revenue DECIMAL(10, 2),
        cogs DECIMAL(10, 2),
        region VARCHAR(50)
    );
    """
    try:
        brain.train(finance_ddl)
        print("✅ Trained on Finance DDL")
    except Exception as e:
        print(f"❌ Training Failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # 3. Ask
    question = "What was the total profit last month?"
    print(f"\n🗣️ Question: {question}")
    
    try:
        sql = brain.ask(question)
        print("\n📝 Generated SQL:")
        print(sql)
        
        if "revenue" in sql.lower() and "cogs" in sql.lower():
             print("\n✅ Verification: SQL uses Revenue and COGS.")
        else:
             print("\n⚠️ Verification: SQL might be missing columns.")
             
    except Exception as e:
        print(f"❌ Generation Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
