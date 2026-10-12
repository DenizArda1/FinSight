from pathlib import Path

from src.finsight.utils.utils import load_json, load_yaml
from src.finsight.rag.embeddings import embed_texts_in_batches
from src.finsight.rag.vector_store import (
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


def process_filing_embeddings(prepared_report, embedding_config):
    if prepared_report["status"] != "prepared":
        raise ValueError("Report is not prepared")

    project_root = Path(__file__).resolve().parents[3]
    processed_path = project_root / "financial_data" / "processed"
    chunks_path = processed_path / prepared_report["chunks_path"]

    chunks = load_json(chunks_path)
    texts = [chunk["text"] for chunk in chunks]
    vectors = embed_texts_in_batches(texts, embedding_config)
    records = build_embedding_records(chunks, vectors)
    return records


def main():
    project_root = Path(__file__).resolve().parents[3]
    settings = load_yaml(project_root / "configs" / "settings.yaml")
    summary_path = (
        project_root / "financial_data" / "processed"
        / "filing_preparation_summary.json"
    )
    summary = load_json(summary_path)
    prepared_reports = [report for report in summary["reports"] if report["status"] == "prepared"]

    if not prepared_reports:
        raise ValueError("No prepared reports found for embedding")


    collection = get_vector_collection(settings["vector_store"])
    for prepared_report in prepared_reports:
        records = process_filing_embeddings(prepared_report, settings["embedding"])
        #Synchronize once with the complete report, never a single embedding batch.
        saved_count = save_embedding_records(collection, records)
        print(
            f"{prepared_report['ticker']} {prepared_report['report_date']}: "
            f"synchronized {saved_count} records",
            flush=True,
        )



if __name__ == "__main__":
    main()
