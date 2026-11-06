#Pin index compatibility to the actual Ollama model digest, not a mutable tag
import requests


def embedding_identity(config):
    response = requests.get(config["base_url"].rstrip("/") + "/api/tags", timeout=config["timeout_seconds"])
    response.raise_for_status()
    name = config["model"]
    candidates = [model for model in response.json().get("models", [])
                  if model.get("name") in {name, name + ":latest"} or model.get("model") == name]
    if len(candidates) != 1 or not candidates[0].get("digest"):
        raise ValueError(f"Cannot resolve embedding model digest: {name}")
    digest = candidates[0]["digest"]
    if config.get("digest") and config["digest"] != digest:
        raise ValueError("Embedding model digest changed; rebuild the index with the intended model")
    return {"embedding_model": name, "embedding_digest": digest, "index_schema": 1}


def verify_collection_identity(collection, config, *, initialize=False):
    expected = embedding_identity(config)
    metadata = collection.metadata or {}
    if metadata.get("ready") is False and not initialize:
        raise ValueError("Index synchronization is incomplete; finish the embedding pipeline before querying")
    if not all(key in metadata for key in expected):
        if not initialize or collection.count() != 0:
            raise ValueError("Index has no verified embedding identity. Rebuild into a new collection; do not relabel old vectors.")
        collection.modify(metadata={**metadata, **expected})
    elif any(metadata[key] != value for key, value in expected.items()):
        raise ValueError("Index embedding identity does not match the query model; use the matching collection or rebuild")
    return expected
