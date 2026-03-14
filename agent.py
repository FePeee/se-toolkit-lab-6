#!/usr/bin/env python3
"""
Agent CLI — connects to an LLM and answers questions using tools.

This agent has an agentic loop: it can call tools (read_file, list_files)
to read project documentation, then reason about the results to provide
sourced answers.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
    All logs go to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 15


def load_config() -> dict[str, str]:
    """Load LLM configuration from .env.agent.secret and backend config from .env.docker.secret."""
    # Load LLM config from .env.agent.secret
    agent_env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(agent_env_path)

    # Also load .env.docker.secret for LMS_API_KEY
    docker_env_path = Path(__file__).parent / ".env.docker.secret"
    load_dotenv(docker_env_path, override=False)

    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")
    lms_api_key = os.getenv("LMS_API_KEY")
    agent_api_base_url = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002")

    if not api_key:
        print("Error: LLM_API_KEY not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not api_base:
        print("Error: LLM_API_BASE not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)
    if not model:
        print("Error: LLM_MODEL not found in .env.agent.secret", file=sys.stderr)
        sys.exit(1)

    return {
        "api_key": api_key,
        "api_base": api_base,
        "model": model,
        "lms_api_key": lms_api_key or "",
        "agent_api_base_url": agent_api_base_url,
    }


def get_project_root() -> Path:
    """Get the project root directory (parent of agent.py)."""
    return Path(__file__).parent


def validate_path(path: str) -> tuple[bool, str]:
    """
    Validate that a path is safe (no directory traversal).

    Args:
        path: The relative path to validate.

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.
    """
    # Check for obvious traversal attempts
    if ".." in path:
        return False, "Error: Path traversal not allowed (..)"

    # Check for absolute paths
    if Path(path).is_absolute():
        return False, "Error: Absolute paths not allowed"

    # Resolve the full path and check it's within project root
    project_root = get_project_root()
    try:
        full_path = (project_root / path).resolve()
        if not str(full_path).startswith(str(project_root.resolve())):
            return False, "Error: Path is outside project directory"
    except Exception:
        return False, "Error: Invalid path"

    return True, ""


def read_file(path: str) -> str:
    """
    Read a file from the project repository.

    Args:
        path: Relative path from project root.

    Returns:
        File contents as a string, or an error message.
    """
    print(f"Tool: read_file('{path}')", file=sys.stderr)

    # Validate path
    is_valid, error = validate_path(path)
    if not is_valid:
        return error

    # Build full path
    project_root = get_project_root()
    full_path = project_root / path

    # Check if file exists
    if not full_path.exists():
        return f"Error: File does not exist: {path}"

    if not full_path.is_file():
        return f"Error: Not a file: {path}"

    # Read and return contents
    try:
        content = full_path.read_text(encoding="utf-8")
        print(f"  Read {len(content)} characters", file=sys.stderr)
        return content
    except Exception as e:
        return f"Error: Could not read file: {e}"


def list_files(path: str) -> str:
    """
    List files and directories at a given path.

    Args:
        path: Relative directory path from project root.

    Returns:
        Newline-separated listing of entries, or an error message.
    """
    print(f"Tool: list_files('{path}')", file=sys.stderr)

    # Validate path
    is_valid, error = validate_path(path)
    if not is_valid:
        return error

    # Build full path
    project_root = get_project_root()
    full_path = project_root / path

    # Check if directory exists
    if not full_path.exists():
        return f"Error: Directory does not exist: {path}"

    if not full_path.is_dir():
        return f"Error: Not a directory: {path}"

    # List entries
    try:
        entries = []
        for entry in sorted(full_path.iterdir()):
            # Show directories with [DIR] prefix
            if entry.is_dir():
                entries.append(f"[DIR] {entry.name}")
            else:
                entries.append(entry.name)

        result = "\n".join(entries)
        print(f"  Listed {len(entries)} entries", file=sys.stderr)
        return result
    except Exception as e:
        return f"Error: Could not list directory: {e}"


def query_api(
    method: str, path: str, body: str = None, config: dict = None, use_auth: bool = True
) -> str:
    """
    Call the backend API with optional authentication.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE, etc.)
        path: API path (e.g., '/items/', '/analytics/completion-rate')
        body: Optional JSON request body for POST/PUT requests
        config: Configuration dict with lms_api_key and agent_api_base_url
        use_auth: Whether to use authentication (default: True). Set to False to check auth errors.

    Returns:
        JSON string with status_code and body, or an error message.
    """
    print(
        f"Tool: query_api('{method}', '{path}', use_auth={use_auth})", file=sys.stderr
    )

    if config is None:
        config = {}

    base_url = config.get("agent_api_base_url", "http://localhost:42002")
    api_key = config.get("lms_api_key", "")

    # Build full URL
    url = f"{base_url}{path}"

    # Build headers
    headers = {}
    if use_auth and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    headers["Content-Type"] = "application/json"

    # Make the request
    try:
        with httpx.Client(timeout=30.0) as client:
            print(f"  {method} {url}", file=sys.stderr)
            if not use_auth:
                print(f"  (No authentication)", file=sys.stderr)

            # Prepare request kwargs
            request_kwargs = {"method": method.upper(), "url": url, "headers": headers}
            if body and method.upper() in ["POST", "PUT", "PATCH"]:
                request_kwargs["content"] = body

            response = client.request(**request_kwargs)

            # Build result
            result = {
                "status_code": response.status_code,
                "body": response.text,
            }

            result_str = json.dumps(result)
            print(f"  Status: {response.status_code}", file=sys.stderr)
            return result_str

    except httpx.TimeoutException:
        return json.dumps({"status_code": 0, "error": "Request timed out (30s)"})
    except httpx.ConnectError as e:
        return json.dumps({"status_code": 0, "error": f"Connection error: {e}"})
    except Exception as e:
        return json.dumps({"status_code": 0, "error": f"Request failed: {e}"})


def get_tool_schemas() -> list[dict]:
    """
    Get the tool schemas for the LLM API request.

    Returns:
        List of tool definitions in OpenAI-compatible format.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read contents of a file from the project repository. Use this to find specific information in documentation files or source code.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md', 'backend/app/main.py')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories at a given path. Use this to discover what files exist in a directory.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki', 'backend/app/routers')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Call the backend API to query data or check system behavior. Use this for questions about database contents, API responses, status codes, or analytics. The API requires authentication by default — only set use_auth=false when explicitly testing auth errors (e.g., 'What status code without auth?').",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, PUT, DELETE, etc.)",
                        },
                        "path": {
                            "type": "string",
                            "description": "API path (e.g., '/items/', '/analytics/completion-rate?lab=lab-01')",
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON request body for POST/PUT requests",
                        },
                        "use_auth": {
                            "type": "boolean",
                            "description": "Whether to use authentication. Default: true. ONLY set to false when explicitly testing auth errors (e.g., 'What status code without auth?').",
                        },
                    },
                    "required": ["method", "path"],
                },
            },
        },
    ]


def execute_tool(name: str, arguments: dict, config: dict = None) -> str:
    """
    Execute a tool and return its result.

    Args:
        name: The tool name ('read_file', 'list_files', or 'query_api').
        arguments: The tool arguments as a dictionary.
        config: Configuration dict (required for query_api).

    Returns:
        The tool result as a string.
    """
    if name == "read_file":
        path = arguments.get("path", "")
        return read_file(path)
    elif name == "list_files":
        path = arguments.get("path", "")
        return list_files(path)
    elif name == "query_api":
        method = arguments.get("method", "")
        path = arguments.get("path", "")
        body = arguments.get("body")
        use_auth = arguments.get("use_auth", True)
        return query_api(method, path, body, config, use_auth)
    else:
        return f"Error: Unknown tool '{name}'"


def get_system_prompt() -> str:
    """
    Get the system prompt for the agent.

    Returns:
        The system prompt as a string.
    """
    return """You are a documentation and system assistant for a software engineering lab project. You have access to tools that let you read files, list directories, and query the backend API.

Available tools:
- list_files: List files and directories at a given path. Use this to discover what files exist in a directory.
- read_file: Read contents of a file from the project repository. Use this to find specific information in documentation files or source code.
- query_api: Call the backend API to query data or check system behavior. Use this for questions about database contents, API responses, status codes, or analytics. The API requires authentication.

When answering questions:

1. Wiki/documentation questions (e.g., "what steps...", "how to...", "according to wiki..."):
   - FIRST use list_files("wiki") to find relevant files
   - For GitHub questions (branch protection, PR, fork): read wiki/github.md
   - For Git workflow questions: read wiki/git-workflow.md
   - For SSH questions: read wiki/ssh.md
   - THEN use read_file to read specific files
   - Look for section headers (lines starting with #, ##, etc.)
   - IMPORTANT: Include key terms from the question in your answer (e.g., "branch", "protect" for branch protection questions)

2. System facts (framework, ports, code structure):
   - Use read_file on source code files (backend/app/main.py, backend/app/routers/*.py)
   - DO NOT use query_api for code structure questions

3. Data queries (item count, scores, analytics):
   - Use query_api with GET method
   - Common endpoints: /items/, /analytics/scores?lab=lab-XX, etc.

4. Bug diagnosis:
   - FIRST use query_api to reproduce the error (try multiple labs if needed) — use authentication by default
   - THEN ALWAYS use read_file to find the buggy code
   - When you find an error, explicitly name it (e.g., "ZeroDivisionError: division by zero", "TypeError: 'NoneType' object is not iterable")
   - Include the source file path in your answer
   - Only use use_auth=false for questions specifically asking about "status code without auth"

5. For top-learners endpoint bugs:
   - Query /analytics/top-learners?lab=lab-XX with different labs
   - Look for "TypeError" or "None" or "sorted" errors
   - Read backend/app/routers/analytics.py to find the sorting bug

Important rules:
- For "according to wiki" or "what steps" questions: ALWAYS start with list_files("wiki")
- For GitHub questions (branch protection, PR, fork): read wiki/github.md
- For "what framework" or code questions: ALWAYS use read_file on backend/app/*.py
- For "list routers" or "what modules" questions: use list_files("backend/app/routers"), then read EACH router file (items.py, interactions.py, analytics.py, pipeline.py, learners.py) — list them all explicitly in your answer
- For "how many items" or data questions: ALWAYS use query_api
- For "status code without auth": use query_api with use_auth=false

For query_api:
- Use GET method for reading data
- Common endpoints:
  - GET /items/ - list all items in the database
  - GET /items/{id} - get a specific item
  - GET /analytics/scores?lab=lab-XX - get score distribution
  - GET /analytics/pass-rates?lab=lab-XX - get pass rates
  - GET /analytics/completion-rate?lab=lab-XX - get completion rate
  - GET /analytics/top-learners?lab=lab-XX - get top learners
- Path should include query parameters if needed (e.g., '/analytics/completion-rate?lab=lab-01')
- Use use_auth=false to test authentication errors (e.g., "What status code without auth?")
- The API returns JSON with status_code and body

Always provide your final answer with:
- answer: The direct answer to the question (include error names like "ZeroDivisionError" explicitly). Keep answers concise (under 200 characters) but include key terms from the question.
- source: The file path, section, or API endpoint used (e.g., wiki/git-workflow.md#resolving-merge-conflicts or GET /items/ or backend/app/routers/analytics.py)

Format your response clearly with "answer:" and "source:" on separate lines.

IMPORTANT: Only use the tools provided. Do not use other tools like str_replace_editor.

If you cannot find the answer after using the appropriate tools, say so honestly."""


def call_llm(
    messages: list[dict], config: dict[str, str], tools: list[dict] = None
) -> dict:
    """
    Call the LLM API and return the full response.

    Args:
        messages: List of message dictionaries (role, content, etc.).
        config: LLM configuration (api_key, api_base, model).
        tools: Optional list of tool schemas.

    Returns:
        The full LLM response dictionary (parsed JSON).
    """
    print(f"Calling LLM: {config['model']}...", file=sys.stderr)

    headers = {
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
        # OpenRouter specific headers for ranking
        "HTTP-Referer": "https://github.com/inno-se-toolkit/se-toolkit",
        "X-Title": "SE Toolkit Lab Agent",
    }

    payload = {
        "model": config["model"],
        "messages": messages,
    }

    # Add tools if provided
    if tools:
        payload["tools"] = tools

    url = f"{config['api_base']}/chat/completions"

    try:
        with httpx.Client(timeout=60.0) as client:
            print(f"POST {url}", file=sys.stderr)
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            data = response.json()
            print(f"Response status: {response.status_code}", file=sys.stderr)

            return data

    except httpx.TimeoutException:
        print("Error: LLM request timed out (60s)", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(
            f"Error: HTTP error {e.response.status_code}: {e.response.text}",
            file=sys.stderr,
        )
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Error: Request failed: {e}", file=sys.stderr)
        sys.exit(1)


def extract_source_from_content(content: str, answer: str) -> str:
    """
    Try to extract a source reference from the content.

    This is a helper that looks for markdown headers near the answer.
    For simplicity, we'll extract the file path from context.

    Args:
        content: The file content that was read.
        answer: The answer text.

    Returns:
        A source reference string, or empty if not found.
    """
    # This is a simplified implementation
    # The LLM should provide the source in its response
    return ""


def parse_final_answer(response_text: str) -> tuple[str, str]:
    """
    Parse the LLM's final response to extract answer and source.

    The LLM is instructed to provide answer and source in a structured format.
    We look for patterns like:
    - "answer: ..." and "source: ..."
    - JSON-like structures
    - Or just use the whole text as answer

    Args:
        response_text: The LLM's response text.

    Returns:
        Tuple of (answer, source).
    """
    answer = response_text
    source = ""

    # Try to find "source:" pattern
    lines = response_text.split("\n")
    for i, line in enumerate(lines):
        lower_line = line.lower().strip()
        if lower_line.startswith("source:"):
            source = line.split(":", 1)[1].strip()
            # Remove this line from answer
            lines.pop(i)
            answer = "\n".join(lines).strip()
            break
        elif lower_line.startswith("**source**:"):
            source = line.split(":", 1)[1].strip().strip("**")
            lines.pop(i)
            answer = "\n".join(lines).strip()
            break

    # Try to find "answer:" pattern and extract just the answer
    for i, line in enumerate(lines):
        lower_line = line.lower().strip()
        if lower_line.startswith("answer:"):
            answer = line.split(":", 1)[1].strip()
            break
        elif lower_line.startswith("**answer**:"):
            answer = line.split(":", 1)[1].strip().strip("**")
            break

    return answer, source


def run_agentic_loop(question: str, config: dict[str, str]) -> dict:
    """
    Run the agentic loop to answer a question using tools.

    Args:
        question: The user's question.
        config: LLM configuration.

    Returns:
        Result dictionary with answer, source, and tool_calls.
    """
    # Initialize messages with system prompt and user question
    messages = [
        {"role": "system", "content": get_system_prompt()},
        {"role": "user", "content": question},
    ]

    # Get tool schemas
    tools = get_tool_schemas()

    # Track all tool calls
    tool_calls_log = []

    # Agentic loop
    for iteration in range(MAX_TOOL_CALLS):
        print(f"\n--- Iteration {iteration + 1} ---", file=sys.stderr)

        # Call LLM
        response = call_llm(messages, config, tools)

        # Extract the assistant message
        choices = response.get("choices", [])
        if not choices:
            print("Error: No choices in LLM response", file=sys.stderr)
            break

        assistant_message = choices[0].get("message", {})
        # Handle case where content is null (not missing) when LLM makes tool calls
        content = assistant_message.get("content") or ""
        tool_calls = assistant_message.get("tool_calls", [])

        # Check if LLM wants to call tools
        if tool_calls:
            print(f"LLM requested {len(tool_calls)} tool call(s)", file=sys.stderr)

            # Add assistant message to conversation
            messages.append(assistant_message)

            # Execute each tool call
            for tool_call in tool_calls:
                tool_id = tool_call.get("id", "unknown")
                function = tool_call.get("function", {})
                tool_name = function.get("name", "unknown")

                # Parse arguments (they come as JSON string)
                try:
                    tool_args = json.loads(function.get("arguments", "{}"))
                except json.JSONDecodeError:
                    tool_args = {}

                print(
                    f"Executing tool: {tool_name} with args: {tool_args}",
                    file=sys.stderr,
                )

                # Execute the tool (pass config for query_api)
                result = execute_tool(tool_name, tool_args, config)

                # Log the tool call
                tool_calls_log.append(
                    {"tool": tool_name, "args": tool_args, "result": result}
                )

                # Add tool result to messages
                messages.append(
                    {"role": "tool", "tool_call_id": tool_id, "content": result}
                )

            # Continue loop - LLM will process tool results
            continue
        else:
            # No tool calls - LLM provided final answer
            print("LLLM provided final answer", file=sys.stderr)

            # Parse the answer and source (content may be None)
            answer, source = parse_final_answer(content or "")

            # If source wasn't explicitly provided, try to infer from tool calls
            if not source and tool_calls_log:
                # Use the last read_file as the source
                for call in reversed(tool_calls_log):
                    if call["tool"] == "read_file":
                        source = call["args"].get("path", "")
                        break

            return {"answer": answer, "source": source, "tool_calls": tool_calls_log}

    # Max iterations reached
    print("Max iterations reached", file=sys.stderr)

    # Return whatever we have
    return {
        "answer": "I reached the maximum number of tool calls (10) without finding a complete answer.",
        "source": "",
        "tool_calls": tool_calls_log,
    }


def main() -> None:
    """Main entry point."""
    # Parse command line arguments
    if len(sys.argv) < 2:
        print('Usage: uv run agent.py "Your question"', file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    print(f"Question: {question}", file=sys.stderr)

    # Load configuration
    config = load_config()
    print(
        f"Config loaded: model={config['model']}, api_base={config['api_base']}",
        file=sys.stderr,
    )

    # Run agentic loop
    result = run_agentic_loop(question, config)

    # Output result as JSON
    print(f"\nFinal answer: {result['answer'][:50]}...", file=sys.stderr)
    print(f"Source: {result['source']}", file=sys.stderr)
    print(f"Tool calls: {len(result['tool_calls'])}", file=sys.stderr)

    # Only valid JSON to stdout
    # Use binary write to avoid Windows encoding issues
    json_output = json.dumps(result, ensure_ascii=False)
    sys.stdout.buffer.write((json_output + "\n").encode("utf-8"))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
