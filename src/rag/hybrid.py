#Deterministic BM25 ranking and reciprocal-rank fusion over filtered chunks
from collections import Counter
import math
import re


def tokenize(text):
    return re.findall(r"\w+", text.casefold(), flags=re.UNICODE)


def bm25_rank(query, records, limit):
    terms = set(tokenize(query))
    documents = [Counter(tokenize(record["text"])) for record in records]
    lengths = [sum(document.values()) for document in documents]
    average = sum(lengths) / len(lengths) if lengths else 0
    if not average or not terms:
        return []
    frequency = {term: sum(term in document for document in documents) for term in terms}
    ranked = []
    for record, document, length in zip(records, documents, lengths, strict=True):
        score = 0.0
        for term in terms:
            count = document[term]
            idf = math.log(1 + (len(documents) - frequency[term] + 0.5) / (frequency[term] + 0.5))
            score += idf * count * 2.5 / (count + 1.5 * (0.25 + 0.75 * length / average))
        if score > 0:
            ranked.append({**record, "bm25_score": score})
    return sorted(ranked, key=lambda row: (-row["bm25_score"], row["chunk_id"]))[:limit]


def reciprocal_rank_fusion(dense, lexical, top_k, rank_constant=60):
    merged = {}
    for name, ranking in (("dense", dense), ("bm25", lexical)):
        for rank, row in enumerate(ranking, 1):
            entry = merged.setdefault(row["chunk_id"], {**row, "score": 0.0, "ranks": {}})
            entry["score"] += 1 / (rank_constant + rank)
            entry["ranks"][name] = rank
            if "distance" in row:
                entry["distance"] = row["distance"]
    return sorted(merged.values(), key=lambda row: (-row["score"], row["chunk_id"]))[:top_k]
