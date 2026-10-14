#Descriptions and argument schemas exposed to the agent model

RESOLVE_TICKER_TOOL = {
    "type": "function",
    "function": {
        "name": "resolve_ticker_to_cik",
        "description": (
            "Resolve a US stock ticker to its company name and "
            "10-digit SEC CIK using the local ticker directory."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, for example NVDA.",
                },
            },
            "required": ["ticker"],
            "additionalProperties": False,
        },
    },
}

SEARCH_FILINGS_TOOL = {
    "type": "function",
    "function": {
        "name": "search_filings",
        "description": (
            "Search locally indexed annual filing sections for source-backed "
            "business, risk, and management commentary. Returns excerpts and "
            "source metadata. Use financial data tools for numerical metrics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol, for example NVDA.",
                },
                "query": {
                    "type": "string",
                    "description": "Question or topic to search for in annual filings.",
                },
                "fiscal_year": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Reported fiscal year. Omit to search all indexed years.",
                },
                "section": {
                    "type": "string",
                    "enum": ["Item 1", "Item 1A", "Item 7"],
                    "description": "Filing section. Omit to search all indexed sections.",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "default": 5,
                    "description": "Maximum number of excerpts to return.",
                },
            },
            "required": ["ticker", "query"],
            "additionalProperties": False,
        },
    },
}

GET_COMPANY_FACTS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_company_facts",
        "description": (
            "Retrieve prepared annual base financial metrics from locally cached SEC data. "
            "Uses configured XBRL selection and preserves source metadata. "
            "Returns reported values, not ratios or growth. Resolve the ticker to a CIK first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cik": {"type": "string", "pattern": "^[0-9]{10}$", "description": "10-digit SEC CIK."},
                "concept": {
                    "type": "string",
                    "enum": ["revenue", "net_income", "operating_income", "gross_profit"],
                    "description": "Base metric name from the metric contract, not an XBRL tag.",
                },
                "years": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5,
                          "description": "Number of latest downloaded annual reporting periods to inspect."},
                "unit": {"type": "string", "enum": ["USD"], "default": "USD"},
            },
            "required": ["cik", "concept"],
            "additionalProperties": False,
        },
    },
}

COMPUTE_METRICS_TOOL = {
    "type": "function",
    "function": {
        "name": "compute_metrics",
        "description": (
            "Calculate financial metrics in Python using locally prepared source records. "
            "Do not supply numerical values or formulas. Results include formulas and source inputs. "
            "Years means source reporting periods: five annual records provide four growth intervals. "
            "Growth and CAGR require at least two periods. Margins and growth are ratios, not percentages."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "cik": {"type": "string", "pattern": "^[0-9]{10}$", "description": "10-digit SEC CIK."},
                "metrics": {
                    "type": "array", "minItems": 1, "uniqueItems": True,
                    "items": {"type": "string", "enum": [
                        "gross_margin", "net_margin", "operating_margin", "revenue_growth", "revenue_cagr",
                    ]},
                    "description": "Calculated metric names from the metric contract.",
                },
                "years": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5,
                          "description": "Number of latest downloaded annual source periods."},
            },
            "required": ["cik", "metrics"],
            "additionalProperties": False,
        },
    },
}
