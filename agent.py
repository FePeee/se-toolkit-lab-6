#!/usr/bin/env python3
"""
Agent CLI — connects to an LLM and answers questions.

Usage:
    uv run agent.py "Your question here"

Output:
    JSON to stdout: {"answer": "...", "tool_calls": []}
    All logs go to stderr.
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


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


def call_llm(question: str, config: dict[str, str]) -> str:
    """
    Call the LLM API and return the answer.

    Args:
        question: The user's question.
        config: LLM configuration (api_key, api_base, model).

    Returns:
        The LLM's answer as a string.
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
        "messages": [
            {
                "role": "user",
                "content": question,
            }
        ],
    }

    url = f"{config['api_base']}/chat/completions"

    try:
        with httpx.Client(timeout=60.0) as client:
            print(f"POST {url}", file=sys.stderr)
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()

            data = response.json()
            print(f"Response status: {response.status_code}", file=sys.stderr)

            # Extract answer from OpenAI-compatible response
            choices = data.get("choices", [])
            if not choices:
                print("Error: No choices in LLM response", file=sys.stderr)
                sys.exit(1)

            answer = choices[0].get("message", {}).get("content", "")
            if not answer:
                print("Error: Empty content in LLM response", file=sys.stderr)
                sys.exit(1)

            return answer

    except httpx.TimeoutException:
        print("Error: LLM request timed out (60s)", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPStatusError as e:
        print(f"Error: HTTP error {e.response.status_code}: {e.response.text}", file=sys.stderr)
        sys.exit(1)
    except httpx.RequestError as e:
        print(f"Error: Request failed: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    # Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"Your question\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]
    print(f"Question: {question}", file=sys.stderr)

    # Load configuration
    config = load_config()
    print(f"Config loaded: model={config['model']}, api_base={config['api_base']}", file=sys.stderr)

    # Call LLM
    answer = call_llm(question, config)
    print(f"Answer received: {len(answer)} chars", file=sys.stderr)

    # Output result as JSON
    result = {
        "answer": answer,
        "tool_calls": [],
    }

    # Only valid JSON to stdout
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
