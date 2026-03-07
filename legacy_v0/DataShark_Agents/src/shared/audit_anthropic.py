import os

import anthropic
from dotenv import load_dotenv


load_dotenv()


def probe_anthropic_models() -> None:
    print("--- 🕵️ Anthropic Model ID Probe ---")
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        print("❌ No ANTHROPIC_API_KEY found in environment.")
        return

    client = anthropic.Anthropic(api_key=key)

    # List of candidates to test
    candidates = [
        "claude-3-5-sonnet-20241022",  # Newest Sonnet
        "claude-3-5-sonnet-20240620",  # Previous Sonnet (Failed earlier, checking again)
        "claude-3-5-haiku-20241022",   # Newest Haiku
        "claude-3-opus-20240229",      # Opus
        "claude-3-sonnet-20240229",    # Legacy Sonnet
        "claude-3-haiku-20240307",     # Legacy Haiku
    ]

    print(f"Probing {len(candidates)} IDs with this API Key...")
    print(f"Key Prefix: {key[:8]}...")
    print("-" * 40)

    for model in candidates:
        print(f"Targeting: {model:<30} ... ", end="", flush=True)
        try:
            client.messages.create(
                model=model,
                max_tokens=1,
                messages=[{"role": "user", "content": "Hi"}],
            )
            print("✅ OPEN")
        except anthropic.NotFoundError:
            print("❌ 404 (Not Found)")
        except anthropic.AuthenticationError:
            print("⛔ AUTH FAIL (Check Key)")
            break  # Stop if key is bad
        except anthropic.BadRequestError as e:
            # Sometimes credit or quota issues show up here
            msg = getattr(getattr(e, "body", {}), "get", lambda *_: None)("message") or str(e)
            print(f"⚠️ BAD REQ: {msg}")
        except Exception as e:
            print(f"⚠️ ERROR: {e}")

    print("-" * 40)
    print("Probe complete.")


if __name__ == "__main__":
    probe_anthropic_models()

