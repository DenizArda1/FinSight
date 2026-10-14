import json

from src.finsight.llm.client import generate_response
from src.finsight.llm.prompts import build_verification_messages

def parse_verification_response(text):
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Verification response must be a JSON object")

    supported = data.get("supported")
    if type(supported) is not bool:
        raise ValueError("Supported must be a boolean")
    issues = data.get("issues")
    if not isinstance(issues, list):
        raise ValueError("Issues must be in list format")
    for issue in issues:
        if not isinstance(issue, str) or not issue.strip():
            raise ValueError("Each issue must be a non-empty string")

    if supported and issues:
        raise ValueError("Supported responses must not contain issues")
    if not supported and not issues:
        raise ValueError("Unsupported responses must contain at least one issue")

    return {"supported": supported, "issues": issues}

def verify_report_answer(question, answer, context, llm_config):
    message = build_verification_messages(question, answer, context)
    json_text = generate_response(message, llm_config, response_format="json")
    validated_message = parse_verification_response(json_text)
    return validated_message
