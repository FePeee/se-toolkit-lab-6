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
MAX_TOOL_CALLS = 10


def load_config() -> dict[str, str]:
    """Load LLM configuration from .env.agent.secret."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(env_path)

    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE")
    model = os.getenv("LLM_MODEL")

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
                "description": "Read contents of a file from the project repository. Use this to find specific information in documentation files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')",
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
                            "description": "Relative directory path from project root (e.g., 'wiki')",
                        }
                    },
                    "required": ["path"],
                },
            },
        },
    ]


def execute_tool(name: str, arguments: dict) -> str:
    """
    Execute a tool and return its result.

    Args:
        name: The tool name ('read_file' or 'list_files').
        arguments: The tool arguments as a dictionary.

    Returns:
        The tool result as a string.
    """
    if name == "read_file":
        path = arguments.get("path", "")
        return read_file(path)
    elif name == "list_files":
        path = arguments.get("path", "")
        return list_files(path)
    else:
        return f"Error: Unknown tool '{name}'"


def get_system_prompt() -> str:
    """
    Get the system prompt for the agent.

    Returns:
        The system prompt as a string.
    """
    return """You are a documentation assistant for a software engineering lab project. You have access to tools that let you read files and list directories in the project repository.

Available tools:
- list_files: List files and directories at a given path
- read_file: Read contents of a file

When answering questions:
1. First explore the wiki directory using list_files to find relevant files
2. Use read_file to read specific files and find the answer
3. Look for section headers in the files (lines starting with #, ##, etc.)
4. Include the source reference (file path + section anchor) in your answer

Section anchors are formed by:
- Converting the section title to lowercase
- Replacing spaces with hyphens
- Removing special characters
Example: "## Resolving Merge Conflicts" becomes "#resolving-merge-conflicts"

Always provide your final answer with:
- answer: The direct answer to the question
- source: The file path and section (e.g., wiki/git-workflow.md#resolving-merge-conflicts)

IMPORTANT: Only use the tools provided (list_files and read_file). Do not use other tools like str_replace_editor.

If you cannot find the answer in the documentation, say so honestly."""


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
        content = assistant_message.get("content", "")
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

                # Execute the tool
                result = execute_tool(tool_name, tool_args)

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
