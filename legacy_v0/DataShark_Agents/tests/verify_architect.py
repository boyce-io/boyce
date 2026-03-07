import os
from pathlib import Path

from anthropic import Anthropic
from openai import OpenAI

from src.agent.editor import default_editor
from src.agent.planner import MigrationPlanner


def _build_anthropic_client() -> Anthropic:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise ValueError("ANTHROPIC_API_KEY missing")
    return Anthropic(api_key=key)


def _build_openai_client() -> OpenAI:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise ValueError("OPENAI_API_KEY missing")
    return OpenAI(api_key=key)


def run_test(provider: str) -> None:
    """
    Run the Architect verification for a specific provider ("anthropic" or "openai").
    """
    provider = provider.lower()
    editor = default_editor()
    repo_root: Path = editor.workspace_root
    target_file = repo_root / "scenarios/dummy_fix.sql"

    # 1. Reset the dummy file for each run
    target_file.parent.mkdir(parents=True, exist_ok=True)
    target_file.write_text("SELECT * FROM u\n", encoding="utf-8")

    # 2. Build client
    if provider == "anthropic":
        client = _build_anthropic_client()
        print("\n🔌 Running Architect test with Anthropic (Claude 3.5 Sonnet)...")
    elif provider == "openai":
        client = _build_openai_client()
        print("\n🔌 Running Architect test with OpenAI (GPT-4o)...")
    else:
        raise ValueError(f"Unknown provider: {provider}")

    # 3. Plan
    planner = MigrationPlanner(client, editor, model_provider=provider)
    goal = "Rename table alias 'u' to 'users'"
    rel_path = "scenarios/dummy_fix.sql"
    plan = planner.generate_plan(goal, [rel_path])

    if not plan:
        raise RuntimeError("No plan generated (Empty JSON returned)")

    # 4. Execute plan via planner (uses FileEditor.apply_patch under the hood)
    logs = planner.execute_plan(plan)
    for line in logs:
        print(line)

    # 5. Verify
    content = target_file.read_text(encoding="utf-8")
    if "SELECT * FROM users" not in content:
        raise RuntimeError(f"Patch failed. Content found: {content!r}")


def main() -> None:
    print("=== DataShark Agent Verification ===\n")

    # Test 1: Anthropic
    print("1. Testing Anthropic (Sonnet)...")
    try:
        run_test("anthropic")
        print("✅ Anthropic: OPERATIONAL")
    except Exception as e:
        print(f"❌ Anthropic: FAILED ({e})")

    print("\n----------------------------------\n")

    # Test 2: OpenAI
    print("2. Testing OpenAI (GPT-4o)...")
    try:
        run_test("openai")
        print("✅ OpenAI: OPERATIONAL")
    except Exception as e:
        print(f"❌ OpenAI: FAILED ({e})")

    print("\n=== End Verification ===")


if __name__ == "__main__":
    main()

