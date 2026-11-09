#Errors shared by the supported LLM providers


class IncompleteResponseError(ValueError):
    """The model stopped before completing its response."""
