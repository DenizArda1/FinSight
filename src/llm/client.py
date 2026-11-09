import requests

from src.llm.errors import IncompleteResponseError
from src.llm.openai_client import send_response_request
from src.llm.usage import annotate_usage


def send_chat_request(messages, llm_config, tools=None, response_format=None, telemetry=None):
    provider = llm_config.get("provider", "ollama")
    if provider == "openai":
        if tools is not None:
            raise ValueError("OpenAI is configured only for Writer and Critic, without tools")
        return send_response_request(messages, llm_config, response_format, telemetry)
    if provider != "ollama":
        raise ValueError(f"Unknown LLM provider: {provider}")
    base_url = llm_config["base_url"]
    base_url = base_url.rstrip("/")
    payload = {
        "model": llm_config["model"],
        "messages": messages,
        "stream": False,
    }
    if tools is not None:
        payload["tools"] = tools
    if response_format is not None:
        payload["format"] = response_format
    if "options" in llm_config:
        payload["options"] = llm_config["options"]
    if "think" in llm_config:
        if type(llm_config["think"]) is not bool:
            raise ValueError("think must be a boolean")
        payload["think"] = llm_config["think"]
    response = requests.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=llm_config["timeout_seconds"],
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    if telemetry is not None:
        for source, target in (("prompt_eval_count", "input_tokens"), ("eval_count", "output_tokens")):
            value = data.get(source)
            if type(value) is int and value >= 0:
                telemetry[target] = value
        annotate_usage(telemetry, llm_config)
    if data.get("done") is False or data.get("done_reason") == "length":
        raise IncompleteResponseError("LLM response is incomplete or reached its token limit")
    message = data.get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM response must contain a message object")
    return message


def generate_response(messages, llm_config, response_format=None, telemetry=None):
    message = send_chat_request(messages, llm_config, response_format=response_format, telemetry=telemetry)
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("LLM response content must be a non-empty string")
    return text


def config_for_role(llm_config, role):
    """Role overrides are complete configurations, never inherited provider options."""
    return llm_config.get("roles", {}).get(role, llm_config)
