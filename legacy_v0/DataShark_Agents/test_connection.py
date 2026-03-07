# test_connection.py
import os
from dotenv import load_dotenv
from anthropic import Anthropic
from src.shared.usage import UsageTracker

load_dotenv()

# 1. Initialize
tracker = UsageTracker()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

print("📡 Ping Anthropic...")

# 2. Fire Request
response = client.messages.create(
    model="claude-sonnet-4-5-20250929",  # <--- UPDATED HERE
    max_tokens=100,
    messages=[{"role": "user", "content": "Are you online?"}]
)

# 3. Log Telemetry
input_tok = response.usage.input_tokens
output_tok = response.usage.output_tokens
tracker.log_request(response.model, input_tok, output_tok)

# 4. Report
print(f"🤖 Response: {response.content[0].text}")
tracker.print_summary()
