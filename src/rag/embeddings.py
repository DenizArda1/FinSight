import math

import requests


def validate_vectors(vectors, expected_count, expected_dimension=None):
    #Validate embedding values and return their shared dimension
    if type(expected_count) is not int or expected_count <= 0:
        raise ValueError("Expected vector count must be a positive integer")
    if expected_dimension is not None:
        if type(expected_dimension) is not int or expected_dimension <= 0:
            raise ValueError("Expected vector dimension must be a positive integer")

    if not isinstance(vectors, list):
        raise ValueError("Embeddings must be a list")
    if len(vectors) != expected_count:
        raise ValueError("The number of vectors and texts do not match")

    dimension = expected_dimension
    for vector_index, vector in enumerate(vectors):
        if not isinstance(vector, list) or not vector:
            raise ValueError(f"Vector {vector_index} must be a non-empty list")
        if dimension is None:
            dimension = len(vector)
        if len(vector) != dimension:
            raise ValueError(
                f"Vector {vector_index} has dimension {len(vector)}; expected {dimension}"
            )

        for value_index, value in enumerate(vector):
            if type(value) not in (int, float):
                raise ValueError(
                    f"Vector {vector_index}, value {value_index} must be a number, not a boolean"
                )
            try:
                finite = math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError(
                    f"Vector {vector_index}, value {value_index} must be a finite representable number"
                )

    return dimension


def embed_texts(texts, embedding_config):
    if embedding_config.get("digest"):
        from src.rag.index_identity import embedding_identity
        embedding_identity(embedding_config)
    if not isinstance(texts, list) or not texts:
        raise ValueError("Text must be a non-empty list")
    
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Each text must be a non-empty string")

    base_url = embedding_config["base_url"].rstrip("/")

    response = requests.post(
        f"{base_url}/api/embed",
        json={
            "model": embedding_config["model"],
            "input": texts,
            "truncate": False,
        },
        timeout=embedding_config["timeout_seconds"],
    )

    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("Embedding response must be a JSON object")

    vectors = data.get("embeddings")
    validate_vectors(vectors, expected_count=len(texts))
    if embedding_config.get("digest"):
        embedding_identity(embedding_config)
    return vectors


def embed_text(text, embedding_config):
    vectors = embed_texts([text], embedding_config)
    return vectors[0]


def embed_texts_in_batches(texts, embedding_config):
    if not isinstance(texts, list) or not texts:
        raise ValueError("Text must be a non-empty list")
    
    batch_size = embedding_config["batch_size"]
    if type(batch_size) is not int or batch_size <= 0:
        raise ValueError("Batch size must be a positive integer")
    
    all_vectors = []
    expected_dimension = None
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        batch_vectors = embed_texts(batch, embedding_config)
        expected_dimension = validate_vectors(
            batch_vectors, expected_count=len(batch), expected_dimension=expected_dimension
        )
        all_vectors.extend(batch_vectors)
    return all_vectors
