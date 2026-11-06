from pathlib import Path
import argparse

from src.utils.utils import load_json, load_yaml
from src.rag.embeddings import embed_texts_in_batches
from src.rag.index_identity import verify_collection_identity
from src.rag.vector_store import (
    get_vector_collection,
    save_embedding_records,
)


def build_embedding_records(chunks, vectors):
    if len(chunks) != len(vectors):
        raise ValueError("Total number of chunks and vectors must be equal")

    records = []
    for chunk, vector in zip(chunks, vectors):
        record = {
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "metadata": chunk["metadata"],
            "embedding": vector
        }
        records.append(record)
    return records


def process_filing_embeddings(prepared_report, embedding_config, collection=None):
    if prepared_report["status"] != "prepared":
        raise ValueError("Report is not prepared")

    project_root = Path(__file__).resolve().parents[2]
    processed_path = project_root / "financial_data" / "processed"
    chunks_path = processed_path / prepared_report["chunks_path"]

    chunks = load_json(chunks_path)
    if collection is not None:
        existing = collection.get(ids=[chunk["chunk_id"] for chunk in chunks], include=["documents", "embeddings"])
        saved = {chunk_id: (text, vector) for chunk_id, text, vector in zip(
            existing["ids"], existing["documents"] or [], existing["embeddings"] if existing["embeddings"] is not None else [], strict=True)}
        if all(chunk["chunk_id"] in saved and saved[chunk["chunk_id"]][0] == chunk["text"] for chunk in chunks):
            return build_embedding_records(chunks, [[float(value) for value in saved[chunk["chunk_id"]][1]] for chunk in chunks])
    texts = [chunk["text"] for chunk in chunks]
    vectors = embed_texts_in_batches(texts, embedding_config)
    records = build_embedding_records(chunks, vectors)
    return records


def main():
    parser = argparse.ArgumentParser(description="Build a model-identified filing index")
    parser.add_argument("--collection", help="Build into a new collection without replacing the active index")
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[2]
    settings = load_yaml(project_root / "configs" / "settings.yaml")
    if args.collection:
        settings["vector_store"]["collection_name"] = args.collection
    summary_path = (
        project_root / "financial_data" / "processed"
        / "filing_preparation_summary.json"
    )
    summary = load_json(summary_path)
    if summary.get("failed_count") or summary.get("company_errors"):
        raise ValueError("Resolve filing preparation failures before indexing; an incomplete corpus cannot be published")
    prepared_reports = [report for report in summary["reports"] if report["status"] == "prepared"]

    if not prepared_reports:
        raise ValueError("No prepared reports found for embedding")


    collection = get_vector_collection(settings["vector_store"])
    identity = verify_collection_identity(collection, settings["embedding"], initialize=True)
    collection.modify(metadata={**collection.metadata, "ready": False})
    embedding_config = {**settings["embedding"], "digest": identity["embedding_digest"]}
    expected_ids = set()
    for prepared_report in prepared_reports:
        records = process_filing_embeddings(prepared_report, embedding_config, collection)
        expected_ids.update(record["chunk_id"] for record in records)
        #Synchronize once with the complete report, never a single embedding batch.
        saved_count = save_embedding_records(collection, records)
        print(
            f"{prepared_report['ticker']} {prepared_report['report_date']}: "
            f"synchronized {saved_count} records",
            flush=True,
        )
    stale_ids = set(collection.get(include=[])["ids"]) - expected_ids
    if stale_ids:
        collection.delete(ids=sorted(stale_ids))
    verify_collection_identity(collection, settings["embedding"], initialize=True)
    collection.modify(metadata={**collection.metadata, "ready": True})



if __name__ == "__main__":
    main()
