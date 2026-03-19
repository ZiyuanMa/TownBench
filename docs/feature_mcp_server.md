# Feature: MCP Server

## Summary

Expose TownBench as an MCP (Model Context Protocol) server so that any MCP-compatible agent can connect, discover the available tools, and play episodes without writing framework-specific adapter code.

## Motivation

The current baseline system (`baselines/openai_agents/`) couples the environment to a single agent framework. Each new agent framework that wants to use TownBench must:

- understand the internal `ActionSpec` and `ActionToolSpec` system
- write a custom tool-building layer similar to `baselines/openai_agents/tools.py`
- manage the `TownBenchEnv` lifecycle manually

MCP eliminates this coupling. A single MCP server exposes all environment operations as standard tools. Any MCP client — Claude Desktop, Cursor, Cline, LangChain, CrewAI, or a custom agent — can connect and interact immediately.

## Design Principle

The MCP server should be a thin protocol adapter over the existing `TownBenchEnv`. It must not duplicate engine logic, modify state models, or replace the role of `baselines/`.

- no changes to `engine/`, `runtime/`, `scenario/`, or `evaluation/`
- all MCP tools delegate to `TownBenchEnv.step()` and `TownBenchEnv.reset()`
- tool definitions are generated mechanically from `TOOL_ACTION_SPECS`

## Protocol Surface

The MCP server exposes three MCP primitive types: tools, resources, and prompts.

### Tools

Tools are the primary interaction surface. Each tool corresponds to an environment action.

#### Session Management Tools

| Tool | Description |
|------|-------------|
| `townbench/list_scenarios` | List available scenario IDs and their paths |
| `townbench/start_episode` | Load a scenario and start a new episode. Returns the initial observation |
| `townbench/get_score` | Compute and return the current episode score |

#### Action Tools (auto-generated from `TOOL_ACTION_SPECS`)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `townbench/move_to` | `target_id` | Move the agent to a linked location by location ID |
| `townbench/inspect` | `target_id` | Inspect the current location or an object present there |
| `townbench/open_resource` | `target_id` | Open a readable resource and return its content |
| `townbench/load_skill` | `target_id` | Load a skill document by skill ID and return its full content |
| `townbench/check_status` | (none) | Check the agent status including location, money, energy, inventory, and notes |
| `townbench/write_note` | `text` | Write a note into the agent notebook |
| `townbench/call_action` | `target_id`, `action_name` | Call an exposed action on an object in the current location |

All action tools include a `session_id` parameter to identify the active episode.

Every action tool returns the full `StepResult` as a JSON object, matching the existing `StepResult.model_dump()` format. This includes:

- `success` — whether the action succeeded
- `observation` — the new observation after the action
- `message` — human-readable result message
- `done` — whether the episode is finished
- `termination_reason` — why the episode ended, if applicable
- delta fields (`time_delta`, `money_delta`, `energy_delta`, `inventory_delta`)
- `triggered_events` and `warnings`

### Resources

Resources expose read-only data that MCP clients can subscribe to or poll.

| Resource URI | Description | Type |
|-------------|-------------|------|
| `townbench://scenarios` | List of available scenario IDs with metadata | Static |
| `townbench://sessions/{session_id}/observation` | Current observation for an active session | Dynamic |
| `townbench://sessions/{session_id}/trace` | Full trace entries for an active session | Dynamic |

### Prompts

Prompts provide reusable message templates that clients can expand.

| Prompt | Arguments | Description |
|--------|-----------|-------------|
| `townbench/agent_briefing` | `scenario_id` | Returns the scenario opening briefing, public rules, and initial observation as a structured message suitable for agent system prompts |

The briefing prompt is equivalent to what `baselines/base.py:build_episode_initial_input()` produces today, but exposed as a standard MCP prompt template.

## Session Management

MCP itself is a stateless protocol, but TownBench episodes are stateful. The server manages this through session IDs.

### Session Lifecycle

```
Client                              MCP Server
  │                                     │
  │  tools/call: start_episode          │
  │  { scenario_id, session_id }        │
  │ ──────────────────────────────────▶ │
  │                                     │  load_scenario()
  │                                     │  create TownBenchEnv
  │                                     │  env.reset()
  │  ◀────────────────────────────────  │
  │  initial Observation                │
  │                                     │
  │  tools/call: move_to               │
  │  { session_id, target_id }          │
  │ ──────────────────────────────────▶ │
  │                                     │  env.step(action)
  │  ◀────────────────────────────────  │
  │  StepResult                         │
  │                                     │
  │  ... more tool calls ...            │
  │                                     │
  │  tools/call: get_score              │
  │  { session_id }                     │
  │ ──────────────────────────────────▶ │
  │                                     │  score_episode()
  │  ◀────────────────────────────────  │
  │  EpisodeScore                       │
```

### Concurrency

Each session holds an independent `TownBenchEnv` instance. Multiple sessions can run in parallel. Access to each session is serialized through per-session locking to prevent race conditions from concurrent tool calls.

### Session Storage

Sessions are stored in a simple in-memory dictionary:

```python
_sessions: dict[str, TownBenchEnv] = {}
```

Sessions are created on `start_episode` and remain until the server shuts down. A future enhancement could add explicit `end_episode` cleanup and optional session TTL.

## Transport Modes

The server should support both MCP transport modes:

| Mode | Use Case | How To Start |
|------|----------|-------------|
| **stdio** | Local development, Claude Desktop integration | `python scripts/run_mcp_server.py --transport stdio` |
| **SSE** | Remote access, multi-client scenarios | `python scripts/run_mcp_server.py --transport sse --port 8080` |

Default is `stdio` to match the most common MCP integration pattern.

## Mapping From ActionSpec To MCP Tool

The mapping from existing `ActionSpec` definitions to MCP `Tool` objects is mechanical. For each spec in `TOOL_ACTION_SPECS`:

```
ActionToolSpec.name        →  MCP Tool name (prefixed with "townbench/")
ActionToolSpec.description →  MCP Tool description
ActionToolSpec.parameters  →  MCP Tool inputSchema properties
ActionToolSpec.build_action → used internally to construct Action from tool arguments
```

The server iterates `TOOL_ACTION_SPECS` at startup and registers one MCP tool per spec. If new action types are added to the engine in the future, they automatically appear as MCP tools without any MCP-specific code changes.

## File Structure

```
mcp_server/
├── __init__.py          module init
├── server.py            MCP Server core: tool, resource, and prompt registration
└── session.py           session manager: create, get, list sessions

scripts/
└── run_mcp_server.py    CLI entry point
```

Estimated new code: approximately 250 lines plus the CLI entry point.

## Dependencies

One new dependency:

```
mcp>=1.0
```

Added to `requirements.txt`. The `mcp` package provides the server framework, tool/resource/prompt decorators, and transport handling.

## Relationship To Existing Baselines

The MCP server does not replace `baselines/`. They serve different roles:

| | MCP Server | baselines/openai_agents/ |
|---|---|---|
| **Role** | Environment interface | Complete agent implementation |
| **What it provides** | Standard tool access to TownBenchEnv | Agent strategy, runner loop, streaming |
| **Framework dependency** | None (protocol-level) | OpenAI Agents SDK |
| **Who uses it** | Any MCP client or agent framework | Developers running the OpenAI baseline |

The baseline system remains useful as a reference implementation that demonstrates how to build a complete agent strategy on top of the environment. The MCP server is the framework-agnostic way to access the same environment.

## Client Configuration Examples

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "townbench": {
      "command": "python",
      "args": ["scripts/run_mcp_server.py", "--transport", "stdio"],
      "cwd": "/path/to/TownBench"
    }
  }
}
```

### Cursor / Cline

Configure MCP server in settings with the same command. The tools will appear in the agent tool palette automatically.

### Custom Python Client

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(
    command="python",
    args=["scripts/run_mcp_server.py"],
    cwd="/path/to/TownBench",
)

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()

        # discover tools
        tools = await session.list_tools()

        # start an episode
        result = await session.call_tool(
            "townbench/start_episode",
            {"scenario_id": "demo_town", "session_id": "s1"},
        )

        # play
        result = await session.call_tool(
            "townbench/move_to",
            {"session_id": "s1", "target_id": "workshop"},
        )
```

## Testing

Tests go in `tests/test_mcp_server.py` and cover:

- tool listing returns all expected action tools plus session management tools
- `start_episode` creates a session and returns a valid observation
- each action tool dispatches correctly to `TownBenchEnv.step()`
- calling a tool with an invalid `session_id` returns a clear error
- calling an action tool after episode termination returns the `episode_done` warning
- `get_score` returns a valid `EpisodeScore`
- resource listing and reading return expected data
- prompt expansion produces the expected briefing format

Tests should use direct Python calls to the server handlers (without spawning a subprocess) to keep execution fast and deterministic.

## Implementation Phases

### Phase 1: Core Server

- implement `mcp_server/server.py` with tool registration
- implement `mcp_server/session.py` with session management
- implement `scripts/run_mcp_server.py` CLI entry point
- register `start_episode`, all 7 action tools, and `get_score`
- support `stdio` transport

### Phase 2: Resources And Prompts

- add `townbench://scenarios` resource
- add `townbench://sessions/{session_id}/observation` resource
- add `townbench://sessions/{session_id}/trace` resource
- add `townbench/agent_briefing` prompt template
- add `sse` transport option

### Phase 3: Testing And Documentation

- write `tests/test_mcp_server.py`
- update `docs/architecture.md` to describe the MCP server layer
- add MCP setup instructions to the project README or a dedicated guide

## Scope Boundary

This feature intentionally does not include:

- multi-agent support within a single episode
- authentication or access control
- persistent session storage across server restarts
- WebSocket transport
- automatic scenario discovery from remote sources
- streaming partial observations

These can be added as future enhancements if needed.

## Success Condition

The feature is complete when:

- a developer can start the MCP server with one command
- any MCP client can connect and discover all TownBench tools
- an agent can play a full `demo_town` episode through MCP tool calls alone
- the episode produces the same trace and score as running through `TownBenchEnv` directly
- all tests pass
