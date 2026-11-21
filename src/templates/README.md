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
One research job runs at a time. Enter sends a message; Shift+Enter inserts a newline.
Replies stay in the same conversation. The sidebar groups messages by conversation.
History is stored atomically in `logs/conversations.json` and survives server/container
restarts through the existing logs bind mount. There is no automatic 50-job deletion.
Interrupted requests are marked failed on restart, never replayed automatically.

Follow-up questions include only their own conversation's opening turn and recent
turns (up to four prior turns, with bounded text). Old answers provide context, not
source evidence; the research workflow retrieves and verifies the new reply.
Source IDs are scoped to individual replies. Verified replies can be downloaded as
Markdown. The selected conversation ID is kept in browser localStorage; history itself
is kept on the local server. This remains a single-user local application.

Only verified prose is shown as a research note or exported. When verification fails,
the UI shows the issues and any retrieved financial rows separately. Source numbers
remain those of the original evidence. Model text is escaped before rendering.

The service binds only to 127.0.0.1 and is intended for local use, not public hosting.
Google Fonts are used with system fallbacks.
