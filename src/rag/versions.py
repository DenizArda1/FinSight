#Select the newest available section, without treating partial amendments as full reports


def active_section_versions(metadatas):
    selected = {}
    for metadata in metadatas:
        key = (metadata["cik"], metadata["report_date"], metadata["section"])
        previous = selected.get(key)
        order = (metadata.get("filed", ""), metadata["accession_number"])
        if previous is None or order > (previous.get("filed", ""), previous["accession_number"]):
            selected[key] = metadata
    return selected


def active_records(records):
    versions = active_section_versions([record["metadata"] for record in records])
    return [record for record in records if record["metadata"]["accession_number"] == versions[
        (record["metadata"]["cik"], record["metadata"]["report_date"], record["metadata"]["section"])
    ]["accession_number"]]


def version_filter(records):
    pairs = sorted({(record["metadata"]["accession_number"], record["metadata"]["section"]) for record in records})
    conditions = [{"$and": [{"accession_number": accession}, {"section": section}]} for accession, section in pairs]
    return conditions[0] if len(conditions) == 1 else {"$or": conditions}
