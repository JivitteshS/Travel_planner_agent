# Real-World Multi-Agent Travel Planner

A LangGraph-based multi-agent system that plans a trip end to end: it interprets a
free-text travel request, fans work out to specialist agents (flights, hotels,
weather, budget), drafts an itinerary, pauses for human approval, and then produces
a final polished plan. Agents get live data through MCP (Model Context Protocol)
servers rather than hallucinating it.

For the list of bugs found and fixed to get this running, see [CHANGES.md](CHANGES.md).

---

## 1. How the agent works

A single user request flows through a **LangGraph state graph** (`graph.py`) built
around one shared state object (`TravelState`) that every node reads from and writes
back into.

1. The user submits a free-text request (e.g. *"Plan a 5-day trip to Tokyo under
   $2500 for two people, include weather info"*) via the Streamlit UI (`frontend.py`)
   or directly via `graph.app.invoke(...)`.
2. **`supervisor_agent`** runs an input guardrail (rejects non-travel requests),
   then asks the LLM to extract structured `trip_constraints` (destination, origin,
   duration, budget, etc.) and decide which specialist agents are actually needed
   for this request.
3. The graph **dynamically routes** to only the selected specialist agents, in a
   fixed order (flight → hotel → weather → budget), skipping any that weren't
   selected.
4. Every specialist agent that ran writes its findings into the shared state.
   **`itinerary_agent`** always runs last and synthesizes everything (flight,
   hotel, weather, budget results) into a draft itinerary.
5. The graph **pauses** at `human_approval_agent` via LangGraph's `interrupt()` —
   execution stops and the draft itinerary is returned to the caller for review.
   This is what makes the Postgres checkpointer necessary (see §4): the paused
   state has to be persisted somewhere so the graph can resume later, potentially
   in a different process.
6. The user approves or requests changes. The caller resumes the graph with
   `Command(resume={"approved": ..., "feedback": ...})`.
7. **`final_response_agent`** produces the polished final plan (incorporating
   feedback if the draft was rejected) and the graph ends.

Each specialist agent call increments `llm_calls` in the state, and every node
appends an `AIMessage` to `state["messages"]` so the run has a readable trace.

---

## 2. Agents and their uses

All agents live in [agent.py](agent.py) and are wired into the graph in [graph.py](graph.py).

| Agent | Purpose |
|---|---|
| **`supervisor_agent`** | Entry point. Runs an LLM guardrail to reject non-travel requests, then extracts `trip_constraints` (destination, origin, duration, budget, travel style, preferences) from the free-text query and decides which of the four specialist agents below are needed. |
| **`flight_agent`** | Looks up destination airports and a sample of airlines via the AviationStack MCP server, then asks the LLM to produce flight guidance (likely airports, relevant airlines, fare range, peak-season warning, booking advice). *Note: currently destination-only — see known limitations in CHANGES.md.* |
| **`hotel_agent`** | Uses the Tavily MCP server to web-search for hotel/neighborhood recommendations matching the request and returns the raw search results (no separate LLM summarization step). |
| **`weather_agent`** | Fetches current weather and a forecast for the destination city from the local Weather MCP server (OpenWeather-backed) and returns them as-is. |
| **`budget_agent`** | Given the flight, hotel, and weather results so far, asks the LLM for a feasibility/cost assessment: cost categories, risk areas, money-saving suggestions, and whether the plan fits the stated budget. |
| **`itinerary_agent`** | Synthesizes every specialist agent's output (whichever ran) into a structured, day-by-day draft itinerary, and prepares the approval request shown to the human. Always runs, even if no specialist agents were selected. |
| **`human_approval_agent`** | Pauses the graph with `interrupt()`, surfacing the draft itinerary and waiting for a human decision (`approved: bool`, optional `feedback`). Nothing downstream runs until the graph is resumed. |
| **`final_response_agent`** | Produces the final, user-facing travel plan — either polishing the approved draft, or revising it based on the human's rejection feedback. |

---

## 3. MCP servers used

The agents never call third-party APIs directly — all live data comes through MCP
servers wired up via `langchain_mcp_adapters.MultiServerMCPClient` in
[mcp_client.py](mcp_client.py):

| Server | Transport | Backing API | Used by |
|---|---|---|---|
| **`tavily`** | `streamable_http` (remote, `mcp.tavily.com`) | Tavily web search | `hotel_agent` (`tavily_search`) |
| **`aviationstack`** | `stdio` (local subprocess) | [AviationStack](https://aviationstack.com/) flight/airport/airline data | `flight_agent` (`list_airports`, `list_airlines`) |
| **`weather`** | `stdio` (local subprocess, [weather_mcp_server.py](weather_mcp_server.py)) | OpenWeather current conditions + forecast | `weather_agent` (`current_weather`, `forecast`) |

The `aviationstack` server is a vendored copy of the third-party
[Pradumnasaraf/aviationstack-mcp](https://github.com/Pradumnasaraf/aviationstack-mcp)
project, included in this repo as a **git submodule** (`aviationstack-mcp/`) with
its own `uv`-managed virtual environment. The `weather` server is a small custom
FastMCP server written for this project (`get_current_weather` / `get_forecast`
tools over the OpenWeather API).

`mcp_client.py` also exposes a `call_tool()` helper that looks up a tool by name
from whichever MCP server exposes it, so agent code never has to know which
server a given tool lives on.

---

## 4. Database used

**PostgreSQL**, used exclusively as a **LangGraph checkpointer** (`graph.py`, via
`langgraph.checkpoint.postgres.PostgresSaver`) — not as an application database.

Its job is to persist the graph's state at every step, keyed by `thread_id`. This
is what makes the human-in-the-loop pause in step 5 above actually work: when
`human_approval_agent` calls `interrupt()`, LangGraph needs somewhere durable to
save "the graph is paused here, with this state" so that a later, unrelated
request (`Command(resume=...)`) can pick the same thread back up — including
across process restarts, since the state isn't just kept in memory.

If `DATABASE_URL` isn't set, `graph.py` falls back to an in-memory-only compiled
graph (no persistence across restarts, and human-in-the-loop resume only works
within the same process run).

Connection string: `DATABASE_URL` in `.env`, e.g.
`postgresql://postgres:postgres@localhost:5432/langgraph_memory`. The
`langgraph_memory` database must exist beforehand — `PostgresSaver.setup()` only
creates the checkpoint tables inside it, not the database itself.

---

## 5. State graph explained

Defined in [graph.py](graph.py), built with LangGraph's `StateGraph(TravelState)`.

**State schema** (`state.py`, `TravelState`, a `TypedDict`): holds the running
conversation (`messages`), the user's query and derived `trip_constraints`, the
supervisor's agent selection, each specialist agent's results
(`flight_results`, `hotel_results`, `weather_results`, `budget_results`), the
draft `itinerary`, the human approval fields (`approval_request`,
`human_feedback`, `approved`), and the `final_response`.

**Nodes:** `supervisor`, `flight_agent`, `hotel_agent`, `weather_agent`,
`budget_agent`, `itinerary_agent`, `human_approval`, `final_response` — each
backed by the corresponding function in `agent.py`.

**Routing logic:**
- `START → supervisor` unconditionally.
- `supervisor → {selected agent}` via `route_from_supervisor`: picks the *first*
  specialist agent from a fixed priority order
  (`flight → hotel → weather → budget`) that the supervisor selected; if none
  were selected, it skips straight to `itinerary_agent`.
- After each specialist agent runs, `route_after_agent(current_agent)` looks
  further down that same priority order for the *next* selected agent to run
  next; once there are none left, it routes to `itinerary_agent`. This is how
  the graph "fans out" to only the agents that are actually relevant to the
  request instead of always running all four.
- `itinerary_agent → human_approval` (always).
- `human_approval → final_response` (always, whether approved or not — the
  branching on approval happens *inside* `final_response_agent`, not as a graph
  edge).
- `final_response → END`.

```
START
  └─▶ supervisor ──▶ [flight_agent] ──▶ [hotel_agent] ──▶ [weather_agent] ──▶ [budget_agent]
                          (each step only runs if the supervisor selected it)
                                                 │
                                                 ▼
                                          itinerary_agent
                                                 │
                                                 ▼
                                            human_approval  ⟸ interrupt() waits here
                                                 │
                                    (resumed via Command(resume=...))
                                                 ▼
                                          final_response
                                                 │
                                                 ▼
                                                END
```

**Persistence:** if `DATABASE_URL` is configured, the compiled graph is given a
`PostgresSaver` checkpointer (see §4), so the pause/resume cycle survives across
separate `invoke()` calls (and processes).

---

## 6. Running it

### Prerequisites
- A local PostgreSQL server reachable at the address in `DATABASE_URL`, with the
  target database already created (default: `langgraph_memory`).
- A `.env` file in the project root — copy `.env.example` and fill in real values
  for `AVIATION_STACK_API_KEY`, `TAVILY_API_KEY`, `OPENWEATHER_API_KEY`,
  `GROQ_API_KEY` (and/or the Azure OpenAI variables, if using that instead — see
  `config.py`), and `DATABASE_URL`.
- The project venv (`multi_agent/`) with dependencies installed.
- The `aviationstack-mcp` submodule checked out with its own venv set up:
  ```
  git submodule update --init --recursive
  cd aviationstack-mcp
  uv sync
  ```

### Run the app (Streamlit UI)

```
E:\Travelplanneragent\multi_agent\Scripts\streamlit.exe run E:\Travelplanneragent\frontend.py
```

Open the URL Streamlit prints (defaults to `http://localhost:8501`), enter a
travel request, click **Create Draft Plan**, review the draft itinerary, then
approve or request changes to get the final plan.

### Headless backend test (no UI)

```
cd E:\Travelplanneragent
E:\Travelplanneragent\multi_agent\Scripts\python.exe -c "from graph import app; import uuid; r = app.invoke({'user_id':'test','user_query':'Plan a 3-day trip to Paris under $1500'}, config={'configurable':{'thread_id':str(uuid.uuid4())}}); print(list(r.keys()))"
```

This runs the graph up to the human-approval interrupt and prints the resulting
state keys — a quick way to confirm the LLM, all three MCP servers, and the
Postgres checkpointer are all working without going through the UI.
