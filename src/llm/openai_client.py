#Responses API adapter for the existing Writer/Critic text contract
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

from src.llm.errors import IncompleteResponseError
from src.llm.usage import annotate_usage


def api_schema(value):
    if isinstance(value, dict):
        return {key: api_schema(item) for key, item in value.items() if key != "uniqueItems"}
    if isinstance(value, list):
        return [api_schema(item) for item in value]
    return value


def send_response_request(messages, config, response_format=None, telemetry=None):
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ValueError("OPENAI_API_KEY is missing; add it to the local .env file")
    payload = {
        "model": config["model"], "input": messages, "store": False,
        "reasoning": {"effort": config.get("reasoning_effort", "low")},
        "max_output_tokens": config.get("max_output_tokens", 8192),
    }
    if isinstance(response_format, dict):
        payload["text"] = {"format": {
            "type": "json_schema", "name": "finsight_response", "strict": True,
            "schema": api_schema(response_format),
        }}
    elif response_format == "json":
        payload["text"] = {"format": {"type": "json_object"}}
    response = requests.post(
        "https://api.openai.com/v1/responses", json=payload,
        headers={"Authorization": f"Bearer {key}"}, timeout=config["timeout_seconds"],
    )
    if not response.ok:
        # Avoid persisting response bodies or authenticated request objects in traces.
        raise RuntimeError(f"OpenAI request failed (HTTP {response.status_code})")
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("OpenAI response must be an object")
    usage = data.get("usage") or {}
    if telemetry is not None:
        for name in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(name)
            if type(value) is int and value >= 0:
                telemetry[name] = value
        telemetry["cached_input_tokens"] = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
        telemetry["reasoning_tokens"] = (usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0)
        telemetry["response_id"] = data.get("id")
        annotate_usage(telemetry, config)
    if data.get("status") != "completed":
        raise IncompleteResponseError("OpenAI response is incomplete or failed")
    parts = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "refusal":
                raise ValueError("OpenAI refused the generation request")
            if part.get("type") == "output_text":
                parts.append(part["text"])
    text = "".join(parts)
    if not text.strip():
        raise ValueError("OpenAI response contains no output text")
    return {"role": "assistant", "content": text}
