# Task 2 Plan: The Documentation Agent

## Overview

This plan describes how to extend the Task 1 agent with tools (`read_file`, `list_files`) and an agentic loop, enabling the agent to read project documentation and provide sourced answers.

## Tool Definitions

### Schema Design

Tools will be defined as OpenAI-compatible function schemas in the LLM API request. Each tool has:
- `name`: The tool identifier (`read_file` or `list_files`)
- `description`: What the tool does and when to use it
- `parameters`: JSON Schema defining required arguments

**read_file schema:**
```json
{
  "name": "read_file",
  "description": "Read contents of a file from the project repository. Use this to find specific information in documentation files.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
      }
    },
    "required": ["path"]
  }
}
```

**list_files schema:**
```json
{
  "name": "list_files",
  "description": "List files and directories at a given path. Use this to discover what files exist in a directory.",
  "parameters": {
    "type": "object",
    "properties": {
      "path": {
        "type": "string",
        "description": "Relative directory path from project root (e.g., 'wiki')"
      }
    },
    "required": ["path"]
  }
}
```

### Tool Implementation

Both tools will be Python functions that:
1. Validate the path to prevent directory traversal attacks
2. Perform the file system operation
3. Return results as strings (or error messages)

**Security: Path Validation**
- Resolve the full path using `Path.resolve()`
- Check that the resolved path starts with the project root
- Reject any path containing `..` or absolute paths
- Return an error message if validation fails

## Agentic Loop

### Loop Structure

```python
messages = [system_prompt, user_question]
tool_calls_log = []
max_iterations = 10

for iteration in range(max_iterations):
    response = call_llm(messages, tools)
    
    if response has tool_calls:
        for tool_call in tool_calls:
            result = execute_tool(tool_call)
            tool_calls_log.append({tool, args, result})
            messages.append(tool_response_message)
    else:
        # LLM sent final answer
        extract answer and source from response
        return JSON result
```

### Message Format

Messages follow the OpenAI chat format:
- `user`: User question or tool result
- `assistant`: LLM response (may contain tool_calls)
- `tool`: Result of a tool execution

When a tool is called, the response includes `tool_calls` array. Each tool call has:
- `id`: Unique identifier for matching requests/responses
- `function.name`: Tool name
- `function.arguments`: JSON string with arguments

### System Prompt Strategy

The system prompt will instruct the LLM to:
1. Use `list_files` to discover wiki files when needed
2. Use `read_file` to read specific files and find answers
3. Always include a source reference (file path + section anchor) in the answer
4. Call tools iteratively until confident in the answer
5. Output the final answer in a structured format

Example system prompt:
```
You are a documentation assistant. You have access to tools that let you read files and list directories.

When answering questions:
1. First explore the wiki directory using list_files to find relevant files
2. Use read_file to read specific files and find the answer
3. Include the source reference (file path + section anchor) in your answer
4. If you cannot find the answer, say so

Always provide your final answer with:
- answer: The direct answer to the question
- source: The file path and section (e.g., wiki/git-workflow.md#resolving-merge-conflicts)
```

## JSON Output Format

The final output must be valid JSON with three required fields:

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "git-workflow.md\n..."},
    {"tool": "read_file", "args": {"path": "wiki/git-workflow.md"}, "result": "..."}
  ]
}
```

## Implementation Steps

1. **Add tool functions** (`read_file`, `list_files`) with path validation
2. **Define tool schemas** for the LLM API request
3. **Update `call_llm`** to accept tools and return full response (including tool_calls)
4. **Implement agentic loop** in `main()`:
   - Initialize messages list
   - Loop up to 10 iterations
   - Execute tools and append results
   - Break when LLM returns text answer
5. **Parse final answer** to extract answer text and source reference
6. **Output JSON** with all three fields
7. **Write tests** for tool-calling behavior
8. **Update AGENT.md** documentation

## Error Handling

| Error | Handling |
|-------|----------|
| Path traversal attempt | Return error message: "Error: Invalid path" |
| File not found | Return error message: "Error: File does not exist" |
| LLM timeout | Log to stderr, exit 1 |
| HTTP error | Log to stderr, exit 1 |
| Max iterations reached | Use whatever answer is available |

## Testing Strategy

Two regression tests will verify tool-calling behavior:

**Test 1: "How do you resolve a merge conflict?"**
- Expected: `read_file` in tool_calls
- Expected: `wiki/git-workflow.md` in source field
- Verifies: Agent reads files to find answers

**Test 2: "What files are in the wiki?"**
- Expected: `list_files` in tool_calls
- Verifies: Agent uses directory listing tool

Tests will run `agent.py` as a subprocess and check:
- Exit code is 0
- stdout is valid JSON
- `tool_calls` array contains expected tool names
- `source` field contains expected file path
