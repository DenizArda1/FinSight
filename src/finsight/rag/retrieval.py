from src.finsight.rag.embeddings import embed_text


def search_reports(query, collection, embedding_config, top_k=5, ticker=None, fiscal_year=None, section=None):
    if type(top_k) is not int or top_k <= 0:
        raise ValueError("top_k must be a positive integer")
    if ticker is not None:
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("Ticker must be a non-empty string")
        ticker = ticker.strip().upper()
    if fiscal_year is not None:
        if type(fiscal_year) is not int or fiscal_year <= 0:
            raise ValueError("Fiscal year must be a positive integer")
    if section is not None:
        if not isinstance(section, str) or not section.strip():
            raise ValueError("Section must be a non-empty string")
        section = section.strip()
    filters = []
    if ticker is not None:
        filters.append({"ticker": ticker})
    if fiscal_year is not None:
        filters.append({"fiscal_year": fiscal_year})
    if section is not None:
        filters.append({"section": section})

    if not filters:
        where = None
    elif len(filters) == 1:
        where = filters[0]
    else:
        where = {"$and": filters}

    query_vector = embed_text(query, embedding_config)
    results = collection.query(
        query_embeddings=[query_vector],
        n_results=top_k,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    return format_search_results(results)


def format_search_results(results):
    matches = []
    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]
    for chunk_id, text, metadata, distance in zip(ids, documents, metadatas, distances, strict=True):
        match = {
            "chunk_id": chunk_id,
            "text": text,
            "metadata": metadata,
            "distance": distance,
        }
        matches.append(match)
    return matches
