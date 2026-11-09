# FinSight research workspace

Run from the repository root:

```sh
.venv/bin/python -m src.web
```

Open http://127.0.0.1:8766. Use `--port` to choose another port.

The interface invokes the existing `run_mcp_orchestrator` with `configs/settings.yaml`.
Keep the configured local model services running and API credentials in the existing
local environment. No credentials are sent to browser JavaScript.

- `research.html`: page structure, dialogs, and icon symbols.
- `../static/research.css`: layout, typography, and responsive styles.
- `../static/research.js`: question submission, job polling, sources, and downloads.
- `../web.py`: localhost API, background execution, and result presentation.

Include the company name, ticker, or CIK in the single message field. Company preparation and supported filing coverage follow the existing backend.
One research job runs at a time. Reloading the page reconnects to in-memory jobs;
restarting the server clears that history. The latest 50 jobs are kept in memory.
Download verified notes as Markdown for a durable copy. Existing runtime diagnostic
traces continue to be saved locally. Bookmark IDs are stored in browser localStorage.

Only verified prose is shown as a research note or exported. When verification fails,
the UI shows the issues and any retrieved financial rows separately. Source numbers
remain those of the original evidence. Model text is escaped before rendering.

The service binds only to 127.0.0.1 and is intended for local use, not public hosting.
Google Fonts are used with system fallbacks.
