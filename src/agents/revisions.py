"""Paragraph patches for bounded Writer revisions; no additional model calls."""

from copy import deepcopy
import re

from jsonschema import Draft202012Validator


def paragraph_parts(text):
    return re.split(r"(\n[ \t]*\n)", text)


def numbered_paragraphs(text):
    parts = paragraph_parts(text)
    return [{"paragraph_id": index // 2 + 1, "text": parts[index]}
            for index in range(0, len(parts), 2) if parts[index].strip()]


def targeted_review_schema(base_schema, paragraphs, evidence):
    schema = deepcopy(base_schema)
    paragraph_ids = [p["paragraph_id"] for p in paragraphs]
    source_ids = [s["source_id"] for s in evidence if not s.get("content_omitted")]
    schema["properties"]["repair_targets"] = {
        "type": "array", "maxItems": len(paragraphs),
        "items": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "paragraph_id": {"type": "integer", **({"enum": paragraph_ids} if paragraph_ids else {})},
                "source_ids": {"type": "array", "uniqueItems": True, "maxItems": len(source_ids), "items": {
                    "type": "integer", **({"enum": source_ids} if source_ids else {})},
                },
                "reason": {"type": "string", "minLength": 1},
            },
            "required": ["paragraph_id", "source_ids", "reason"],
        },
    }
    schema["required"].append("repair_targets")
    return schema


def patch_schema(targets):
    ids = [target["paragraph_id"] for target in targets]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("Repair targets must contain distinct paragraph IDs")
    return {
        "type": "object", "additionalProperties": False,
        "properties": {"patches": {
            "type": "array", "minItems": len(ids), "maxItems": len(ids),
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "paragraph_id": {"type": "integer", "enum": ids},
                    "text": {"type": "string", "minLength": 1},
                },
                "required": ["paragraph_id", "text"],
            },
        }},
        "required": ["patches"],
    }


def apply_paragraph_patches(composition, targets, response):
    """Preserve every unselected paragraph, separator, fact ID and answer kind."""
    Draft202012Validator(patch_schema(targets)).validate(response)
    ids = [patch["paragraph_id"] for patch in response["patches"]]
    if len(ids) != len(set(ids)):
        raise ValueError("A paragraph cannot be patched more than once")
    parts = paragraph_parts(composition["text"])
    allowed = {p["paragraph_id"] for p in numbered_paragraphs(composition["text"])}
    for patch in response["patches"]:
        replacement = patch["text"]
        if patch["paragraph_id"] not in allowed:
            raise ValueError("Unknown paragraph ID")
        if not replacement.strip() or len(paragraph_parts(replacement)) != 1:
            raise ValueError("Each replacement must be one non-empty paragraph")
        parts[(patch["paragraph_id"] - 1) * 2] = replacement
    updated = deepcopy(composition)
    updated["text"] = "".join(parts)
    return updated
