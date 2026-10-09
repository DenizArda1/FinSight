from langchain_text_splitters import RecursiveCharacterTextSplitter


def split_text(text, max_chars=1500, overlap=200):
    if not isinstance(text, str):
        raise ValueError("Text must be a string")
    if type(max_chars) is not int or max_chars <= 0:
        raise ValueError("Maximum character length must be a positive integer")
    if type(overlap) is not int or not 0 <= overlap < max_chars:
        raise ValueError("Overlap must be an integer between zero and max_chars - 1")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=overlap,
        length_function=len,
        add_start_index=True,
    )
    documents = splitter.create_documents([text])
    chunks = []

    for document in documents:
        start = document.metadata["start_index"]
        chunk_text = document.page_content
        end = start + len(chunk_text)

        if start < 0 or text[start:end] != chunk_text:
            raise ValueError("Chunk position does not match the source text")

        chunks.append({
            "start": start,
            "end": end,
            "text": chunk_text,
        })

    return chunks

def build_document_chunks(document):
    chunks = split_text(document["text"])
    results = []
    accession_number = document["filing"]["accessionNumber"]
    for i, chunk in enumerate(chunks):
        chunk_id = f"{accession_number}:{i}"
        results.append({
            "chunk_id": chunk_id,
            "text": chunk["text"],
            "metadata": {
                "ticker": document["company"]["ticker"],
                "cik": document["company"]["cik"],
                "accession_number": accession_number,
                "report_date": document["filing"]["reportDate"],
                "source_url": document["filing"]["url"],
                "start": chunk["start"],
                "end": chunk["end"],
            },
        })
    return results

