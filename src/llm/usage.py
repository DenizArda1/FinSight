"""Token-level API cost estimates; local hardware/electricity costs are excluded."""
LUNA_PRICING_DATE = "2026-11-06"


def annotate_usage(event, config):
    event["model"] = config.get("model")
    event["provider"] = config.get("provider", "ollama")
    if event["provider"] == "ollama":
        event["estimated_cost_usd"] = 0.0
    elif config.get("model") == "gpt-6-luna" and "input_tokens" in event and "output_tokens" in event:
        count = event["input_tokens"]
        cached = event.get("cached_input_tokens", 0)
        input_multiplier, output_multiplier = (2, 1.5) if count > 272000 else (1, 1)
        event["estimated_cost_usd"] = (
            ((count - cached) * 0.10 + cached * 0.01) * input_multiplier
            + event["output_tokens"] * 0.50 * output_multiplier
        ) / 1_000_000
        event["pricing_date"] = LUNA_PRICING_DATE


def summarize_usage(trace):
    calls = [event for event in trace if "input_tokens" in event or "output_tokens" in event]
    return {
        "model_calls_with_usage": len(calls),
        "model_calls_without_usage": sum(event.get("type") == "model" and "input_tokens" not in event and "output_tokens" not in event for event in trace),
        "tool_calls": sum(event.get("type") == "tool" for event in trace),
        "input_tokens": sum(event.get("input_tokens", 0) for event in calls),
        "output_tokens": sum(event.get("output_tokens", 0) for event in calls),
        "estimated_cost_usd": sum(event.get("estimated_cost_usd", 0) for event in calls),
        "calls_without_cost_estimate": sum("estimated_cost_usd" not in event for event in calls),
        "note": "API token estimate, excluding taxes and local hardware costs; missing usage is not zero usage.",
    }
