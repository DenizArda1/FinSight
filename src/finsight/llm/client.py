import requests


def send_chat_request(messages, llm_config, tools=None, response_format=None):
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
    response = requests.post(
        f"{base_url}/api/chat",
        json=payload,
        timeout=llm_config["timeout_seconds"],
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("LLM response must be a JSON object")
    message = data.get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM response must contain a message object")
    return message


def generate_response(messages, llm_config, response_format=None):
    message = send_chat_request(messages, llm_config, response_format=response_format)
    text = message.get("content")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("LLM response content must be a non-empty string")
    return text
