def validate_selection(selection):
    forms = selection.get("forms")
    if not isinstance(forms, list) or not forms:
        raise ValueError("Forms must be a non-empty list")

    for form in forms:
        if form not in ("10-K", "10-K/A"):
            raise ValueError("Unsupported filing form")

    if selection.get("within_tag") != "latest_filed":
        raise ValueError("Unsupported within_tag policy")
    
    if selection.get("across_tags") != "first_available":
        raise ValueError("Unsupported across_tags policy")
    
    if selection.get("period_fields") != ["start", "end"]:
        raise ValueError("Unsupported period_fields")

    duration = selection.get("duration_days", {})
    min_days = duration.get("min")
    max_days = duration.get("max")

    if type(min_days) is not int or type(max_days) is not int:
        raise ValueError("Duration bounds must be integers")
    
    if min_days <= 0:
        raise ValueError("Minimum duration must be positive")
    
    if max_days < min_days:
        raise ValueError("Maximum duration must not be less than minimum")


def validate_calculations(calculations, metrics):
    supported_functions = {
        "calculate_margin": ("same_period", 2),
        "calculate_growth": ("consecutive_periods", 1),
        "calculate_cagr": ("full_range", 1),
    }

    if not isinstance(calculations, dict) or not calculations:
        raise ValueError("Calculations must be a non-empty dictionary")

    for calculation_name, definition in calculations.items():
        if not isinstance(definition, dict):
            raise ValueError(f"Definition must be a dictionary for {calculation_name}")

        function_name = definition.get("function")
        if not isinstance(function_name, str) or function_name not in supported_functions:
            raise ValueError(f"Unsupported function for {calculation_name}")

        expected_mode, expected_input_count = supported_functions[function_name]
        if definition.get("period_mode") != expected_mode:
            raise ValueError(f"Unsupported period_mode for {calculation_name}")

        inputs = definition.get("inputs")
        if not isinstance(inputs, list):
            raise ValueError(f"Inputs must be a list for {calculation_name}")
        if len(inputs) != expected_input_count:
            raise ValueError(f"Unexpected input count for {calculation_name}")

        for input_name in inputs:
            if not isinstance(input_name, str) or input_name not in metrics:
                raise ValueError(f"Unknown input metric for {calculation_name}: {input_name}")

        if len(set(inputs)) != len(inputs):
            raise ValueError(f"Duplicate input metrics for {calculation_name}")

        if definition.get("unit") != "ratio":
            raise ValueError(f"Unsupported unit for {calculation_name}")
