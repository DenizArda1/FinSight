"""Shared UTF-8 JSON, JSONL, and YAML file operations."""
import yaml
import json
from pathlib import Path
from tempfile import NamedTemporaryFile


def load_json(file_path):
    """Read a JSON file into Python objects."""
    with Path(file_path).open(encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(file_path):
    """Read non-blank JSONL lines, raising an error for invalid JSON."""
    records = []
    with Path(file_path).open(encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            records.append(json.loads(line))
    return records


def load_yaml(file_path):
    """Read a YAML file using the safe loader."""
    with Path(file_path).open(encoding="utf-8") as file:
        return yaml.safe_load(file)


def _write_text(file_path, text):
    """Replace the destination only after the complete text is written."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None

    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False,
        ) as file:
            temporary = Path(file.name)
            file.write(text)
        temporary.replace(path)
        
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def save_json(data, file_path):
    """Save Python objects as indented JSON, creating parent directories."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    _write_text(file_path, text)


def save_yaml(data, file_path):
    """Save Python objects as YAML, preserving dictionary order."""
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    _write_text(file_path, text)
