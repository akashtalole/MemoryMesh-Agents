import json
import logging

logger = logging.getLogger(__name__)


def parse_llm_json_response(response_text: str) -> dict:
    """Parse a JSON object from an LLM response.

    Tolerant of the common shapes models emit: a bare JSON object, a Markdown
    code fence (```json ... ``` or plain ``` ... ```), or a JSON object embedded
    in surrounding prose. No specific fence or the word "json" is required.
    """
    candidate = response_text.strip()

    if candidate.startswith("```"):
        newline = candidate.find("\n")
        if newline != -1:
            candidate = candidate[newline + 1:]
        if candidate.rstrip().endswith("```"):
            candidate = candidate.rstrip()[:-3]
    candidate = candidate.strip()

    try:
        parsed_response = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        if start < 0:
            raise
        parsed_response, _ = json.JSONDecoder().raw_decode(candidate[start:])

    return parsed_response


def parse_agent_json_response(response_text):
    """Parse the response from the agent into a dict, or None if not JSON."""
    try:
        return parse_llm_json_response(response_text)
    except Exception as e:
        logger.warning(f"Could not parse JSON from agent response: {type(e).__name__}: {e}")
        return None


def safe_log_text(response) -> str:
    return "".join(
        c for c in str(response) if c.isascii() and (c.isprintable() or c.isspace())
    )
