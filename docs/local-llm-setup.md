# Local LLM Setup (Ollama / vLLM)

Boyce uses [LiteLLM](https://docs.litellm.ai) for its internal query planner — the component
that converts natural language to a `StructuredFilter`. You can point it at any LiteLLM-supported
provider, including fully local models running on your own hardware.

**When you need this:** Only for the CLI (`boyce ask "..."`), HTTP API (`boyce serve --http`), or
non-MCP integrations — where Boyce's internal query planner handles NL→SQL. If you use Claude
Desktop, Cursor, Claude Code, or any other MCP host, the host's LLM handles NL reasoning and
**you do not need to configure a provider at all.**

---

## Ollama

[Ollama](https://ollama.com) runs models locally with a one-command install. No GPU required
for smaller models.

### 1. Install Ollama and pull a model

```bash
# Install (macOS)
brew install ollama

# Pull a model — llama3.2 is a good general-purpose choice
ollama pull llama3.2

# Smaller/faster alternative
ollama pull qwen2.5-coder:7b

# Larger, better SQL reasoning (requires ~8GB RAM)
ollama pull llama3.1:8b
```

### 2. Start the Ollama server

```bash
ollama serve
# Runs at http://localhost:11434 by default
```

### 3. Configure Boyce

```bash
export BOYCE_PROVIDER=ollama
export BOYCE_MODEL=ollama/llama3.2
```

Or in your MCP config:

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "env": {
        "BOYCE_PROVIDER": "ollama",
        "BOYCE_MODEL": "ollama/llama3.2",
        "BOYCE_DB_URL": "postgresql://user:pass@host:5432/db"
      }
    }
  }
}
```

### Model name format

LiteLLM expects Ollama models prefixed with `ollama/`:

| Ollama model | BOYCE_MODEL value |
|---|---|
| `llama3.2` | `ollama/llama3.2` |
| `llama3.1:8b` | `ollama/llama3.1:8b` |
| `qwen2.5-coder:7b` | `ollama/qwen2.5-coder:7b` |
| `mistral` | `ollama/mistral` |
| `codellama` | `ollama/codellama` |

### Custom Ollama URL

If Ollama is running on a different host or port:

```bash
export BOYCE_PROVIDER=ollama
export BOYCE_MODEL=ollama/llama3.2
export OLLAMA_API_BASE=http://192.168.1.100:11434
```

---

## vLLM

[vLLM](https://docs.vllm.ai) is a high-throughput inference server with an OpenAI-compatible
API. Recommended for production local deployments or when you have a GPU.

### 1. Install and start vLLM

```bash
pip install vllm

# Serve a model (example: Mistral 7B)
python -m vllm.entrypoints.openai.api_server \
  --model mistralai/Mistral-7B-Instruct-v0.3 \
  --port 8000
```

vLLM exposes an OpenAI-compatible API at `http://localhost:8000`.

### 2. Configure Boyce

Since vLLM mimics the OpenAI API, set `BOYCE_PROVIDER=openai` and point the base URL at
your local server:

```bash
export BOYCE_PROVIDER=openai
export BOYCE_MODEL=mistralai/Mistral-7B-Instruct-v0.3
export OPENAI_API_BASE=http://localhost:8000/v1
export OPENAI_API_KEY=dummy   # vLLM doesn't enforce auth by default; any value works
```

Or in your MCP config:

```json
{
  "mcpServers": {
    "boyce": {
      "command": "boyce",
      "env": {
        "BOYCE_PROVIDER": "openai",
        "BOYCE_MODEL": "mistralai/Mistral-7B-Instruct-v0.3",
        "OPENAI_API_BASE": "http://localhost:8000/v1",
        "OPENAI_API_KEY": "dummy",
        "BOYCE_DB_URL": "postgresql://user:pass@host:5432/db"
      }
    }
  }
}
```

---

## Model Recommendations

The query planner's job is structured extraction: read a schema, identify entities and fields,
output a `StructuredFilter` JSON object. Models that follow instructions reliably and handle
JSON output perform best.

| Use case | Recommended model | Notes |
|---|---|---|
| General use, low RAM | `ollama/llama3.2` | 3B params, fast, good instruction following |
| Better reasoning, ~8GB RAM | `ollama/llama3.1:8b` | Stronger SQL schema reasoning |
| Code/SQL focus | `ollama/qwen2.5-coder:7b` | Strong structured output |
| GPU / production | `mistralai/Mistral-7B-Instruct-v0.3` via vLLM | High throughput |

**Note:** Model quality affects NL→SQL accuracy. If `ask_boyce` returns incomplete or
wrong `StructuredFilter` output, try a larger or more capable model. The SQL compiler itself
(`build_sql`) is deterministic — only the planner is model-dependent.

---

## Privacy

When using Ollama or vLLM, your queries and schema never leave your machine. No data is
sent to any external API. Boyce's deterministic SQL kernel, safety layer, and snapshot
storage are all local regardless of provider — the only network call is the LiteLLM
provider request.

For MCP host users (Claude Desktop, Cursor, etc.): your NL query goes to your MCP host's
model (Claude, GPT-4, etc.) via that host's normal API. Boyce itself makes no outbound calls.

---

## Environment Variable Reference

| Variable | Required | Example |
|---|---|---|
| `BOYCE_PROVIDER` | Yes (CLI/HTTP only) | `ollama`, `openai`, `anthropic` |
| `BOYCE_MODEL` | Yes (CLI/HTTP only) | `ollama/llama3.2`, `gpt-4o-mini` |
| `OLLAMA_API_BASE` | Ollama only (non-default URL) | `http://192.168.1.100:11434` |
| `OPENAI_API_BASE` | vLLM only | `http://localhost:8000/v1` |
| `OPENAI_API_KEY` | vLLM only | Any string (auth not enforced by default) |

Full provider list: [LiteLLM providers](https://docs.litellm.ai/docs/providers)
