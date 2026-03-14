# Agent Architecture

## Overview

This agent is a Python CLI that connects to an LLM (Large Language Model) and answers questions. It serves as the foundation for the more advanced agent with tools and agentic loop that will be built in Tasks 2–3.

## LLM Provider

**Provider:** OpenRouter  
**Model:** `nvidia/nemotron-3-nano-30b-a3b:free`  
**API:** OpenAI-compatible chat completions API

### Why OpenRouter?

- Free tier: 50 requests per day without credit card
- OpenAI-compatible API — easy to switch providers
- Multiple free models available (Nvidia, Qwen, Llama)

### Configuration

LLM credentials are stored in `.env.agent.secret` (gitignored):

```bash
LLM_API_KEY=sk-or-v1-...
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL=nvidia/nemotron-3-nano-30b-a3b:free
```

> **Note:** This is NOT the same as `LMS_API_KEY` in `.env.docker.secret`. That key protects your backend LMS endpoints. This key authenticates with your LLM provider.

## Architecture

### Data Flow

```
User question (CLI argument)
    ↓
Parse arguments (argparse via sys.argv)
    ↓
Load config from .env.agent.secret (python-dotenv)
    ↓
Build HTTP request (httpx)
    ↓
POST to LLM API (https://openrouter.ai/api/v1/chat/completions)
    ↓
Parse JSON response
    ↓
Extract answer from choices[0].message.content
    ↓
Output JSON to stdout: {"answer": "...", "tool_calls": []}
```

### Components

| Component | File/Module | Purpose |
|-----------|-------------|---------|
| CLI Parser | `sys.argv` | Parse question from command line |
| Config Loader | `load_config()` | Load LLM credentials from `.env.agent.secret` |
| LLM Client | `call_llm()` | HTTP POST to LLM API via httpx |
| Response Parser | `call_llm()` | Extract answer from OpenAI-compatible JSON |
| Output Formatter | `main()` | Format result as JSON to stdout |

### Output Format

**stdout** (only valid JSON):

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

**stderr** (all logs):

```
Question: What does REST stand for?
Config loaded: model=meta-llama/llama-3.3-70b-instruct:free
Calling LLM: meta-llama/llama-3.3-70b-instruct:free...
POST https://openrouter.ai/api/v1/chat/completions
Response status: 200
Answer received: 42 chars
```

## Usage

### Run the agent

```bash
uv run agent.py "What does REST stand for?"
```

### Expected output

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

### Exit codes

- `0` — Success
- `1` — Error (missing config, HTTP error, timeout, etc.)

## Dependencies

| Package | Purpose |
|---------|---------|
| `httpx` | HTTP client for LLM API calls |
| `python-dotenv` | Load environment variables from `.env.agent.secret` |

Both are already in `pyproject.toml`.

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `LLM_API_KEY` | Log to stderr, exit 1 |
| HTTP timeout (>60s) | Log to stderr, exit 1 |
| HTTP error (4xx/5xx) | Log response to stderr, exit 1 |
| Empty LLM response | Log to stderr, exit 1 |

## Limitations (Task 1)

- No tools support (`tool_calls` is always `[]`)
- No agentic loop (single LLM call)
- No domain knowledge (no `read_file` tool yet)
- Minimal system prompt

These will be added in Tasks 2–3.

## Testing

Run the regression test:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

The test runs `agent.py` as a subprocess and verifies:

- Exit code is 0
- stdout is valid JSON
- JSON has `answer` and `tool_calls` fields

## Future Work (Tasks 2–3)

- Add tools: `read_file`, `list_files`, `query_api`
- Implement agentic loop (plan → act → observe)
- Add system prompt with domain knowledge
- Support multi-turn conversations
