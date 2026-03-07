import os
import sys

from dotenv import load_dotenv
import openai
import anthropic


# 1. Load Environment
load_dotenv()


def check_keys() -> None:
    print("--- 🔑 Key Check ---")
    oa_key = os.getenv("OPENAI_API_KEY")
    an_key = os.getenv("ANTHROPIC_API_KEY")

    if oa_key:
        print(f"✅ OPENAI_API_KEY found (starts with {oa_key[:8]}...)")
    else:
        print("❌ OPENAI_API_KEY NOT found")

    if an_key:
        print(f"✅ ANTHROPIC_API_KEY found (starts with {an_key[:8]}...)")
    else:
        print("❌ ANTHROPIC_API_KEY NOT found")
    print("")


def check_openai() -> None:
    print("--- 🤖 OpenAI Connectivity (gpt-4o) ---")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("⏭️ Skipping OpenAI check (no key)")
        return

    client = openai.OpenAI(api_key=api_key)
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Return the word 'PONG'."}],
            max_tokens=10,
        )
        content = response.choices[0].message.content.strip()
        print(f"✅ OpenAI Response: {content}")
    except Exception as e:
        print(f"❌ OpenAI Connection Failed: {e}")
    print("")


def check_anthropic() -> None:
    print("--- 🧠 Anthropic Connectivity (claude-3-5-sonnet-20240620) ---")
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("⏭️ Skipping Anthropic check (no key)")
        return

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=10,
            messages=[{"role": "user", "content": "Return the word 'PONG'."}],
        )
        content = response.content[0].text.strip()
        print(f"✅ Anthropic Response: {content}")
    except Exception as e:
        print(f"❌ Anthropic Connection Failed: {e}")
    print("")


if __name__ == "__main__":
    check_keys()
    check_openai()
    check_anthropic()

