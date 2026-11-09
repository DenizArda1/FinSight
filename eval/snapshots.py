#Record input and code fingerprints without copying private configuration
import hashlib
import json
from pathlib import Path

import chromadb


def hash_files(root, files):
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def capture_snapshot(project_root, settings):
    root = Path(project_root)
    files = []
    for directory in ("financial_data/raw", "financial_data/processed", "configs"):
        files.extend(path for path in (root / directory).rglob("*")
                     if path.is_file() and path.suffix in (".json", ".html", ".htm", ".yaml"))
    source_hash = hash_files(root, files)
    index_hash = None
    vector_config = settings.get("vector_store")
    if vector_config:
        index_path = root / vector_config["path"]
        if not (index_path / "chroma.sqlite3").is_file():
            raise FileNotFoundError("Configured vector index does not exist")
        client = chromadb.PersistentClient(path=str(index_path))
        collection = client.get_collection(vector_config["collection_name"])
        values = collection.get(include=["documents", "metadatas", "embeddings"])
        digest = hashlib.sha256()
        for index in sorted(range(len(values["ids"])), key=lambda i: values["ids"][i]):
            record = {
                "id": values["ids"][index], "text": values["documents"][index],
                "metadata": values["metadatas"][index],
                "embedding": values["embeddings"][index].tolist(),
            }
            digest.update(json.dumps(record, sort_keys=True, ensure_ascii=False, allow_nan=False).encode())
            digest.update(b"\0")
        digest.update(json.dumps(collection.metadata, sort_keys=True).encode())
        index_hash = digest.hexdigest()
    return {
        "source_sha256": source_hash,
        "index_sha256": index_hash,
        "code_sha256": hash_files(root, list((root / "src").rglob("*.py"))),
    }
