from pathlib import Path

import chromadb

from src.finsight.rag.embeddings import validate_vectors


def get_vector_collection(vector_store_config):
    project_root = Path(__file__).resolve().parents[3]
    database_path = project_root / vector_store_config["path"]

    client = chromadb.PersistentClient(path=str(database_path))

    collection = client.get_or_create_collection(
        name=vector_store_config["collection_name"],
        embedding_function=None,
        configuration={
            "hnsw": {
                "space": "cosine",
            },
        },
    )

    return collection


def validate_filing_records(records):
    #Validate one complete report's records and return its source identity
    if not isinstance(records, list) or not records:
        raise ValueError("Records must be a non-empty list")

    identity = None
    seen_ids = set()
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Each record must be a dictionary")
        chunk_id = record.get("chunk_id")
        if not isinstance(chunk_id, str) or not chunk_id.strip():
            raise ValueError("Each chunk ID must be a non-empty string")
        if chunk_id in seen_ids:
            raise ValueError(f"Duplicate chunk ID: {chunk_id}")
        seen_ids.add(chunk_id)

        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Each record must contain non-empty text")
        metadata = record.get("metadata")
        if not isinstance(metadata, dict):
            raise ValueError("Each record must contain metadata")
        cik = metadata.get("cik")
        accession_number = metadata.get("accession_number")
        for value in (cik, accession_number):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Record metadata must contain a non-empty CIK and accession number")
        record_identity = (cik, accession_number)
        if identity is None:
            identity = record_identity
        elif record_identity != identity:
            raise ValueError("All records must belong to the same CIK and accession number")

    validate_vectors(
        [record.get("embedding") for record in records], expected_count=len(records)
    )
    return identity


def save_embedding_records(collection, records):
    """Synchronize a report using its COMPLETE, non-empty set of chunk records.

    Call once per report, not once per embedding batch. Writes precede deletions;
    failures propagate so the caller can retry. This is not a transaction and
    concurrent writers for the same report are not supported.
    """
    cik, accession_number = validate_filing_records(records)
    ids = [record["chunk_id"] for record in records]
    documents = [record["text"] for record in records]
    metadatas = [record["metadata"] for record in records]
    embeddings = [record["embedding"] for record in records]
    report_filter = {
        "$and": [{"cik": cik}, {"accession_number": accession_number}],
    }
    existing_ids = set(collection.get(where=report_filter, include=[])["ids"])
    occupied_ids = set(collection.get(ids=ids, include=[])["ids"])
    if occupied_ids - existing_ids:
        raise ValueError("A new chunk ID already belongs to another report")

    collection.upsert(
        ids=ids,
        documents=documents,
        metadatas=metadatas,
        embeddings=embeddings,
    )
    stale_ids = sorted(existing_ids - set(ids))
    if stale_ids:
        collection.delete(ids=stale_ids, where=report_filter)
    return len(records)
