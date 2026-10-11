from pathlib import Path

from src.finsight.utils.utils import load_json
from src.finsight.rag.embeddings import embed_texts_in_batches

def build_embedding_records(chunks, vectors):
    if len(chunks) != len(vectors):
        raise ValueError("Total number of chunks and vectors must be equal")
    
    records = []
    for chunk, vector in zip(chunks,vectors):
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