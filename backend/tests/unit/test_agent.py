"""
Regression tests for agent.py CLI.

Tests verify that agent.py:
- Runs successfully with a question argument
- Outputs valid JSON to stdout
- JSON contains required fields: answer, tool_calls
"""

import json
import subprocess
from pathlib import Path


def test_agent_outputs_valid_json():
    """Test that agent.py outputs valid JSON with required fields."""
    # Path to agent.py in project root
    project_root = Path(__file__).parent.parent.parent.parent
    agent_path = project_root / "agent.py"

    # Run agent with a simple question
    result = subprocess.run(
        ["uv", "run", str(agent_path), "What is 2+2?"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(project_root),
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout}") from e

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check field types
    assert isinstance(output["answer"], str), "'answer' should be a string"
    assert isinstance(output["tool_calls"], list), "'tool_calls' should be an array"

    # Check answer is not empty
    assert len(output["answer"].strip()) > 0, "'answer' should not be empty"

    print(f"✓ Test passed: answer={output['answer'][:50]}...")


def test_agent_uses_read_file_for_merge_conflict():
    """Test that agent uses read_file tool to answer questions about git workflow."""
    # Path to agent.py in project root
    project_root = Path(__file__).parent.parent.parent.parent
    agent_path = project_root / "agent.py"

    # Run agent with a question about merge conflicts
    result = subprocess.run(
        ["uv", "run", str(agent_path), "How do you resolve a merge conflict?"],
        capture_output=True,
        text=True,
        timeout=120,  # Longer timeout for tool calls
        cwd=str(project_root),
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout}") from e

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"
    assert "source" in output, "Missing 'source' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check that read_file was used
    tool_names = [call.get("tool", "") for call in output["tool_calls"]]
    assert "read_file" in tool_names, (
        "Expected 'read_file' in tool_calls for this question"
    )

    # Check that source references a git-related file
    source = output.get("source", "")
    assert source, "Expected non-empty source"
    assert ".md" in source, f"Expected markdown file in source, got: {source}"
    # Source should reference a git-related file
    assert any(x in source.lower() for x in ["git", "merge", "conflict"]), (
        f"Expected git/merge/conflict reference in source, got: {source}"
    )

    print(f"✓ Test passed: answer={output['answer'][:50]}..., source={source}")


def test_agent_uses_list_files_for_wiki_listing():
    """Test that agent uses list_files tool to answer questions about wiki contents."""
    # Path to agent.py in project root
    project_root = Path(__file__).parent.parent.parent.parent
    agent_path = project_root / "agent.py"

    # Run agent with a question about wiki files
    result = subprocess.run(
        ["uv", "run", str(agent_path), "What files are in the wiki?"],
        capture_output=True,
        text=True,
        timeout=120,  # Longer timeout for tool calls
        cwd=str(project_root),
    )

    # Check exit code
    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    # Parse stdout as JSON
    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise AssertionError(f"Agent output is not valid JSON: {result.stdout}") from e

    # Check required fields
    assert "answer" in output, "Missing 'answer' field in output"
    assert "tool_calls" in output, "Missing 'tool_calls' field in output"

    # Check that list_files was used
    tool_names = [call.get("tool", "") for call in output["tool_calls"]]
    assert "list_files" in tool_names, (
        "Expected 'list_files' in tool_calls for this question"
    )

    print(
        f"✓ Test passed: answer={output['answer'][:50]}..., tool_calls={len(output['tool_calls'])}"
    )
