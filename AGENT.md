# Agent Architecture

## Overview

This agent is a Python CLI that connects to an LLM (Large Language Model) and answers questions using **tools** and an **agentic loop**. Unlike a simple chatbot, this agent can read project documentation files and provide sourced answers.

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

Backend API configuration is stored in `.env.docker.secret`:

```bash
LMS_API_KEY=my-secret-api-key
AGENT_API_BASE_URL=http://localhost:42002  # optional, defaults to localhost:42002
```

> **Note:** Two distinct keys: `LMS_API_KEY` (in `.env.docker.secret`) protects your backend LMS endpoints. `LLM_API_KEY` (in `.env.agent.secret`) authenticates with your LLM provider. Don't mix them up.

## Tools

The agent has three tools that extend its capabilities beyond simple chat:

### `query_api` (Task 3)

Calls the backend API to query data or check system behavior.

**Parameters:**

- `method` (string, required): HTTP method (GET, POST, PUT, DELETE, etc.)
- `path` (string, required): API path (e.g., `/items/`, `/analytics/completion-rate?lab=lab-01`)
- `body` (string, optional): JSON request body for POST/PUT requests

**Returns:** JSON string with `status_code` and `body` (or `error` on failure).

**Authentication:** Uses `LMS_API_KEY` from `.env.docker.secret` as a Bearer token.

**Example:**

```json
{
  "tool": "query_api",
  "args": {"method": "GET", "path": "/items/"},
  "result": "{\"status_code\": 200, \"body\": \"[...]\"}"
}
```

**Use cases:**

- Data queries: "How many items are in the database?"
- Status code checks: "What status code does /items/ return without auth?"
- Bug diagnosis: "Query /analytics/completion-rate and explain the error"

### `read_file`

Reads the contents of a file from the project repository.

**Parameters:**

- `path` (string, required): Relative path from project root (e.g., `wiki/git-workflow.md`)

**Returns:** File contents as a string, or an error message if the file doesn't exist.

**Security:**

- Validates paths to prevent directory traversal attacks (`..` is rejected)
- Rejects absolute paths
- Verifies resolved paths stay within project root

### `list_files`

Lists files and directories at a given path.

**Parameters:**

- `path` (string, required): Relative directory path from project root (e.g., `wiki`)

**Returns:** Newline-separated listing of entries (directories prefixed with `[DIR]`), or an error message.

**Security:**

- Same path validation as `read_file`
- Only lists directories within project root

### Tool Schemas

Tools are defined as OpenAI-compatible function schemas:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read contents of a file from the project repository...",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Relative path from project root"
        }
      },
      "required": ["path"]
    }
  }
}
```

## Agentic Loop

The agent uses an iterative loop to answer questions:

```
Question ──▶ LLM ──▶ tool call? ──yes──▶ execute tool ──▶ back to LLM
                         │
                         no
                         │
                         ▼
                    JSON output
```

### Loop Structure

1. **Initialize**: Create messages list with system prompt and user question
2. **Call LLM**: Send messages + tool schemas to LLM API
3. **Check response**:
   - If `tool_calls` present → execute each tool, append results as `tool` role messages, go to step 2
   - If no tool calls → parse final answer, output JSON, exit
4. **Max iterations**: Stop after 10 tool calls (prevents infinite loops)

### Message Format

Messages follow OpenAI chat format:

| Role | Purpose |
|------|---------|
| `system` | Instructions for the agent (set once) |
| `user` | User question or tool result |
| `assistant` | LLM response (may contain `tool_calls`) |
| `tool` | Result of a tool execution |

Example conversation flow:

```python
messages = [
    {"role": "system", "content": "You are a documentation assistant..."},
    {"role": "user", "content": "How do you resolve a merge conflict?"},
    # LLM responds with tool_calls
    {"role": "assistant", "content": "", "tool_calls": [...]},
    # Tool result
    {"role": "tool", "tool_call_id": "call_123", "content": "git-workflow.md\n..."},
    # LLM may call more tools or give final answer
    {"role": "assistant", "content": "To resolve a merge conflict..."}
]
```

### System Prompt Strategy

The system prompt instructs the LLM to:

1. Use `list_files` to discover wiki files when needed
2. Use `read_file` to read specific files and find answers
3. Look for section headers (lines starting with `#`, `##`, etc.)
4. Include source references (file path + section anchor) in answers
5. Be honest if the answer cannot be found

**Section anchor format:**

- Convert section title to lowercase
- Replace spaces with hyphens
- Remove special characters
- Example: `## Resolving Merge Conflicts` → `#resolving-merge-conflicts`

## Output Format

**stdout** (only valid JSON):

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\nimages\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "# Git workflow\n\n## Resolving Merge Conflicts\n..."
    }
  ]
}
```

**Fields:**

- `answer` (string, required): The direct answer to the question
- `source` (string, required): File path + section anchor (e.g., `wiki/git-workflow.md#resolving-merge-conflicts`)
- `tool_calls` (array, required): All tool calls made. Each entry has `tool`, `args`, and `result`

**stderr** (all logs):

```
Question: How do you resolve a merge conflict?
Config loaded: model=nvidia/nemotron-3-nano-30b-a3b:free

--- Iteration 1 ---
Calling LLM: nvidia/nemotron-3-nano-30b-a3b:free...
POST https://openrouter.ai/api/v1/chat/completions
LLM requested 1 tool call(s)
Executing tool: list_files with args: {'path': 'wiki'}
Tool: list_files('wiki')
  Listed 72 entries

--- Iteration 2 ---
Calling LLM: nvidia/nemotron-3-nano-30b-a3b:free...
LLM requested 1 tool call(s)
Executing tool: read_file with args: {'path': 'wiki/git-workflow.md'}
Tool: read_file('wiki/git-workflow.md')
  Read 4521 characters

--- Iteration 3 ---
Calling LLM: nvidia/nemotron-3-nano-30b-a3b:free...
LLM provided final answer

Final answer: Edit the conflicting file, choose which changes...
Source: wiki/git-workflow.md#resolving-merge-conflicts
Tool calls: 2
```

## Architecture

### Data Flow

```
User question (CLI argument)
    ↓
Parse arguments (sys.argv)
    ↓
Load config from .env.agent.secret (python-dotenv)
    ↓
Run agentic loop
    ├── Initialize messages (system + user)
    ├── Loop (max 10 iterations)
    │   ├── Call LLM with messages + tools
    │   ├── If tool_calls: execute tools, append results, continue
    │   └── If no tool_calls: parse answer, break
    ↓
Output JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
```

### Components

| Component | Function | Purpose |
|-----------|----------|---------|
| CLI Parser | `main()` | Parse question from command line |
| Config Loader | `load_config()` | Load LLM credentials from `.env.agent.secret` and backend config from `.env.docker.secret` |
| Tool: read_file | `read_file()` | Read file contents with path validation |
| Tool: list_files | `list_files()` | List directory entries with path validation |
| Tool: query_api | `query_api()` | Call backend API with Bearer token authentication |
| Path Validator | `validate_path()` | Prevent directory traversal attacks |
| Tool Schemas | `get_tool_schemas()` | Define OpenAI-compatible tool definitions (3 tools) |
| Tool Executor | `execute_tool()` | Route tool calls to implementation, pass config for query_api |
| LLM Client | `call_llm()` | HTTP POST to LLM API via httpx |
| Answer Parser | `parse_final_answer()` | Extract answer and source from LLM response |
| Agentic Loop | `run_agentic_loop()` | Orchestrate tool calls and LLM interactions |
| Output Formatter | `main()` | Format result as JSON to stdout |

### Components Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        agent.py                             │
├─────────────────────────────────────────────────────────────┤
│  main()                                                     │
│    │                                                        │
│    ▼                                                        │
│  run_agentic_loop() ◄───────┐                               │
│    │                        │                               │
│    ▼                        │                               │
│  call_llm()                 │                               │
│    │                        │                               │
│    ▼                        │                               │
│  [LLM API] ──tool_calls─────┤                               │
│    │                        │                               │
│    ▼                        │                               │
│  execute_tool() ◄───config──┤                               │
│    │                        │                               │
│    ├──► read_file()         │                               │
│    │       └──► validate_path()                             │
│    │                        │                               │
│    ├──► list_files()        │                               │
│    │       └──► validate_path()                             │
│    │                        │                               │
│    └──► query_api()         │                               │
│            ├──► httpx request                               │
│            └──► Bearer auth (LMS_API_KEY)                   │
│                                                             │
│  parse_final_answer()                                       │
│    │                                                        │
│    ▼                                                        │
│  JSON output                                                │
└─────────────────────────────────────────────────────────────┘
```

## Usage

### Run the agent

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

### Expected output

```json
{
  "answer": "Edit the conflicting file, remove the conflict markers, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

### Exit codes

- `0` — Success
- `1` — Error (missing config, HTTP error, timeout, etc.)

## Dependencies

| Package | Purpose |
|---------|---------|
| `httpx` | HTTP client for LLM API calls |
| `python-dotenv` | Load environment variables from `.env.agent.secret` |

## Error Handling

| Error | Behavior |
|-------|----------|
| Missing `LLM_API_KEY` | Log to stderr, exit 1 |
| HTTP timeout (>60s) | Log to stderr, exit 1 |
| HTTP error (4xx/5xx) | Log response to stderr, exit 1 |
| Empty LLM response | Log to stderr, exit 1 |
| Path traversal attempt | Return error message in tool result |
| File not found | Return error message in tool result |
| Max iterations (10) reached | Return partial answer with tool_calls log |

## Security

### Path Validation

All tool paths are validated to prevent accessing files outside the project:

1. **Check for `..`**: Reject any path containing parent directory references
2. **Check for absolute paths**: Reject paths starting with `/` or drive letters
3. **Resolve and verify**: Use `Path.resolve()` to get canonical path, verify it starts with project root

Example attack attempts (all blocked):

```
read_file("../.env.agent.secret")  # Rejected: contains ..
read_file("/etc/passwd")           # Rejected: absolute path
list_files("../../")               # Rejected: contains ..
```

## Testing

Run the regression tests:

```bash
uv run pytest backend/tests/unit/test_agent.py -v
```

Tests verify:

- Exit code is 0
- stdout is valid JSON
- JSON has `answer`, `source`, and `tool_calls` fields
- Tool calls contain expected tools for specific questions

## Limitations

- Maximum 10 tool calls per question (prevents infinite loops but may limit complex queries)
- Source extraction is heuristic-based (LLM must provide source in response)
- No multi-turn conversation support (each question is independent)
- No caching of file reads (same file may be read multiple times in one session)
- API rate limits on free LLM tier (50 requests/day on OpenRouter free tier)

## Task 3: The System Agent - Lessons Learned

### Implementation

Adding the `query_api` tool required:

1. **Environment variable handling**: Load `LMS_API_KEY` from `.env.docker.secret` and `AGENT_API_BASE_URL` with a default fallback
2. **Tool schema design**: Clear description telling the LLM when to use `query_api` vs `read_file`
3. **Authentication**: Bearer token in the `Authorization` header
4. **Error handling**: Timeout, connection errors, and HTTP errors all return structured JSON

### System Prompt Strategy

The key insight is guiding the LLM to choose the right tool:

- **Wiki/documentation questions** → `read_file` + `list_files`
- **System facts** (framework, ports) → `read_file` on source code
- **Data queries** (item count, scores) → `query_api`
- **Bug diagnosis** → `query_api` first, then `read_file` to find the bug

### Benchmark Results

The 10-question benchmark tests:

- 4 wiki/documentation questions (read_file)
- 2 system fact questions (read_file or query_api)
- 2 data query questions (query_api)
- 2 reasoning questions (multi-step tool chaining)

### Key Debugging Insights

1. **Tool selection**: The LLM sometimes uses `read_file` for data questions. Fixed by improving the tool description to emphasize "database contents" and "API responses"
2. **Content may be null**: When the LLM makes tool calls, `content` field is `null` (not missing). Use `(msg.get("content") or "")` instead of `msg.get("content", "")`
3. **API authentication**: Without `LMS_API_KEY`, the API returns 401. The tool handles this gracefully and returns the error in the result

### Final Score

After iteration, the agent passes all 10 local questions in `run_eval.py`.

## Future Work

- Improve source extraction with better header detection
- Add conversation history for multi-turn support
- Implement file content caching within a session
- Add more sophisticated error recovery for API failures
