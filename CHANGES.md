# Changes — Backend Debugging & Fixes (2026-08-24)

This document records everything that was found and fixed to get the multi-agent
travel planner backend (LangGraph + MCP servers + Streamlit UI) running end to end.

## Summary

The backend did not run at all before this session — it failed at multiple points
in sequence (LLM config, missing modules, broken paths, missing dependencies,
missing database, encoding crashes). Each issue below was found by actually
attempting to run the pipeline and fixing whatever broke next, until a full
`app.invoke(...)` call completed successfully end to end.

## Issues found and fixed

1. **Groq model never actually used** (`config.py`)
   Two `get_llm()` functions were defined back to back. Python silently let the
   second definition (Azure OpenAI) shadow the first (Groq) — the Groq function
   was dead code even though it wasn't commented out. Fixed by commenting out the
   Azure version so Groq is active.

2. **`AVIATION_STACK_API_KEY` env var name mismatch** (`.env`)
   `.env` defined `AVIATIONSTACK_API_KEY` (no underscore) but the code everywhere
   (`config.py`, `mcp_client.py`) read `os.getenv("AVIATION_STACK_API_KEY")`
   (with underscore). This resolved to `None`, which — once passed into the
   `env` dict used to spawn the aviationstack MCP subprocess — would have crashed
   the subprocess at launch. Renamed the `.env` key to match.

3. **Stale, non-existent MCP server paths** (`config.py`, `mcp_client.py`)
   Both files hardcoded absolute paths to a different, no-longer-existing project
   directory (`E:\Multi_agent_system_with_MCP\...`, `E:\multi_agent_system_demo\...`).
   Repointed to the actual paths under this project (`E:\Travelplanneragent\...`).

4. **Wrong module name in `graph.py`**
   `from agents import (...)` — no such module exists; the file is `agent.py`
   (singular). Fixed the import.

5. **`graph.py` never exposed a compiled `app`**
   `frontend.py` does `from graph import app`, but `graph.py` only defined
   `build_graph()` and never called it at module level. Added `app = build_graph()`.

6. **Postgres database didn't exist**
   `DATABASE_URL` in `.env` pointed at a database (`langgraph_memory`) that had
   never been created on the local Postgres server. Created it.

7. **Postgres checkpointer setup crashed — missing `autocommit=True`**
   `PostgresSaver.setup()` runs `CREATE INDEX CONCURRENTLY`, which Postgres
   refuses to run inside a transaction block. `psycopg.connect(DATABASE_URL)`
   needed `autocommit=True`.

8. **Missing Python packages in the project venv (`multi_agent/`)**
   `langgraph-checkpoint-postgres` and `langchain-groq` were imported by the code
   but not installed. Installed both.

9. **Groq default model no longer exists**
   The hardcoded default model `llama-3.3-70b-versatile` has been removed from
   Groq's catalog for this API key (404 `model_not_found`). Switched the default
   to `openai/gpt-oss-120b`.

10. **`aviationstack-mcp` venv had a broken editable install**
    `aviationstack-mcp/.venv` was created against a *third*, even older project
    location (`E:\MultiAgentSystemLangraph\...`) that no longer exists, so
    `import aviationstack_mcp` failed inside its own venv. Re-synced with
    `uv sync` from the current project location, which reinstalled it correctly.

11. **Windows console encoding crash on Unicode output** (`agent.py`)
    The many debug `print()` statements in `agent.py` would crash with
    `UnicodeEncodeError` whenever an LLM response contained certain Unicode
    punctuation (e.g. non-breaking hyphens, smart quotes, em dashes) because the
    default Windows console codepage (`cp1252`) can't encode them. Fixed by
    reconfiguring `sys.stdout`/`sys.stderr` to UTF-8 at the top of `agent.py`, so
    this no longer depends on setting `PYTHONUTF8=1` externally.

## Known limitation (not fixed, by design — flagged for awareness)

- **`flight_agent` only considers the destination, never the origin.**
  `trip_constraints` has an `origin` field that the supervisor attempts to
  extract from the user's query, but `flight_agent` (`agent.py`) never reads
  `constraints["origin"]` — it only looks up airports/context for the
  destination. Flight guidance is currently one-sided: it doesn't resolve or
  search for a departure airport even if the user states where they're flying
  from.

- **`list_airlines` is called with an empty search string** (`agent.py`,
  `flight_agent`), so it returns an unfiltered/default sample of airlines from
  the AviationStack API rather than airlines actually relevant to the
  destination.

- **`config.py` contains a dead, duplicated copy** of the MCP client, `get_tools`,
  `call_tool`, and all five tool wrapper functions. `agent.py` actually imports
  these from `mcp_client.py`, not `config.py` — the copy in `config.py` is never
  executed. Left in place; flagged in case it causes confusion later.

## Verified working

Ran the compiled graph directly (no UI) with multiple sample queries
(a Paris trip with flights+hotel, a Tokyo trip with weather, a Rome
weekend trip). In each case the supervisor correctly selected agents based on
the query, each downstream agent (flight/hotel/weather/budget/itinerary)
produced real output using live API calls (Groq LLM, Tavily search,
AviationStack, OpenWeather), and the graph correctly paused at the
`human_approval` interrupt as designed.

## Local setup notes

- Project Python venv: `multi_agent/` (already has all required packages after
  this session's installs).
- `aviationstack-mcp/` is a local clone of the third-party
  [Pradumnasaraf/aviationstack-mcp](https://github.com/Pradumnasaraf/aviationstack-mcp)
  MCP server, with its own `.venv` (managed via `uv sync`).
- `.env` is required locally (see `.env.example` for the expected keys) and is
  intentionally excluded from version control since it holds live API keys and
  a database connection string.
- Postgres must be running locally with a `langgraph_memory` database
  (used by the LangGraph checkpointer) reachable via `DATABASE_URL`.

### Run the app

```
$env:PYTHONUTF8="1"   # optional as of fix #11, but harmless to set
E:\Travelplanneragent\multi_agent\Scripts\streamlit.exe run E:\Travelplanneragent\frontend.py
```

### Headless backend smoke test (no UI)

```
E:\Travelplanneragent\multi_agent\Scripts\python.exe -c "from graph import app; import uuid; r = app.invoke({'user_id':'test','user_query':'Plan a 3-day trip to Paris under $1500'}, config={'configurable':{'thread_id':str(uuid.uuid4())}}); print(list(r.keys()))"
```
