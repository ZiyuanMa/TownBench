import asyncio
from inspect import signature
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from townbench_agents.common import build_default_instructions
from townbench_agents.langchain.agent import build_langchain_agent
from townbench_agents.langchain.config import LangChainAgentConfig
from townbench_agents.langchain.deepseek import DeepSeekChatOpenAI
from townbench_agents.langchain.runner import run_langchain_agent_episode, run_langchain_agent_episode_streamed
from townbench_agents.langchain.tools import build_townbench_tools
from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def _identity_tool(fn, **_kwargs):
    return fn


class FakeCompiledAgent:
    def __init__(self, model, tools, system_prompt):
        self.model = model
        self.tools = tools
        self.system_prompt = system_prompt


class FakeRunnableAgent:
    def __init__(self, tools=None):
        self.tools = tools or []

    def invoke(self, agent_input, config=None):
        assert config == {"recursion_limit": 4}
        assert "Opening briefing:" in agent_input["messages"][0]["content"]
        assert "Public rules:" in agent_input["messages"][0]["content"]
        assert "Current location: Plaza (plaza)" in agent_input["messages"][0]["content"]
        tools = {tool.__name__: tool for tool in self.tools}
        tools["move_to"]("workshop")
        tools["call_action"]("tea_station", "brew_tea")
        tools["call_action"]("completion_log", "record_order")
        return {"messages": [_FakeMessage("Order paid.")]}


class FakeRecursionLimitError(Exception):
    lc_error_code = "GRAPH_RECURSION_LIMIT"


class MaxTurnsRunnableAgent:
    def __init__(self, tools=None):
        self.tools = tools or []

    def invoke(self, agent_input, config=None):
        assert config == {"recursion_limit": 2}
        tools = {tool.__name__: tool for tool in self.tools}
        tools["move_to"]("workshop")
        raise FakeRecursionLimitError("Graph recursion limit reached")


class DefaultLimitRunnableAgent:
    def __init__(self, tools=None):
        self.tools = tools or []

    def invoke(self, agent_input, config=None):
        assert config == {"recursion_limit": 8}
        return {"messages": [_FakeMessage("Used explicit recursion limit.")]}


class FakeStreamRunnableAgent:
    def __init__(self, tools=None):
        self.tools = tools or []

    async def astream(self, agent_input, config=None, stream_mode=None, version=None):
        assert config == {"recursion_limit": 4}
        assert stream_mode == ["messages", "updates"]
        assert version == "v2"
        yield {"type": "messages", "data": (_FakeMessage("Order"), {"node": "model"})}
        yield {
            "type": "updates",
            "data": {"model": {"messages": [_FakeToolCallMessage()]}},
        }
        tools = {tool.__name__: tool for tool in self.tools}
        tools["move_to"]("workshop")
        yield {
            "type": "updates",
            "data": {"tools": {"messages": [_FakeMessage("Moved to `Workshop`.")]}},
        }
        tools["call_action"]("tea_station", "brew_tea")
        tools["call_action"]("completion_log", "record_order")
        yield {"type": "messages", "data": (_FakeMessage(" paid."), {"node": "model"})}
        yield {
            "type": "updates",
            "data": {"model": {"messages": [_FakeMessage("Order paid.")]}},
        }


class _FakeMessage:
    def __init__(self, text: str):
        self.content = text
        self.content_blocks = [{"type": "text", "text": text}]


class _FakeToolCallMessage:
    content = ""
    content_blocks = [{"type": "tool_call", "name": "move_to", "args": {"target_id": "workshop"}}]
    tool_calls = [{"name": "move_to", "args": {"target_id": "workshop"}}]


def _build_fake_agent(env, config, **_kwargs):
    tools = build_townbench_tools(env, tool_factory=_identity_tool)
    return FakeRunnableAgent(tools=tools)


def _build_fake_limit_agent(env, config, **_kwargs):
    tools = build_townbench_tools(env, tool_factory=_identity_tool)
    return MaxTurnsRunnableAgent(tools=tools)


def _build_fake_default_limit_agent(env, config, **_kwargs):
    tools = build_townbench_tools(env, tool_factory=_identity_tool)
    return DefaultLimitRunnableAgent(tools=tools)


def _build_fake_stream_agent(env, config, **_kwargs):
    tools = build_townbench_tools(env, tool_factory=_identity_tool)
    return FakeStreamRunnableAgent(tools=tools)


def test_build_townbench_tools_executes_env_steps():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    tools = {tool.__name__: tool for tool in build_townbench_tools(env, tool_factory=_identity_tool)}

    move_result = tools["move_to"]("workshop")
    brew_result = tools["call_action"]("tea_station", "brew_tea")
    payout_result = tools["call_action"]("completion_log", "record_order")

    assert isinstance(move_result, str)
    assert isinstance(brew_result, str)
    assert isinstance(payout_result, str)
    assert "Moved to `Workshop`." in move_result
    assert "You brewed a fresh pot of tea." in brew_result
    assert "You recorded the finished tea order and collected payment." in payout_result
    assert env.state.world_flags["tea_ready"] is False
    assert env.state.world_flags["order_logged"] is False
    assert env.state.world_flags["payment_posted"] is True
    assert env.state.agent.money == 21


def test_call_action_tool_exposes_object_id_and_optional_action_args():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    tools = {tool.__name__: tool for tool in build_townbench_tools(env, tool_factory=_identity_tool)}

    call_action_signature = signature(tools["call_action"])

    assert list(call_action_signature.parameters) == ["object_id", "action_name", "action_args"]
    assert call_action_signature.parameters["action_args"].default is None
    assert call_action_signature.return_annotation is str


def test_build_townbench_tools_returns_text_by_default():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    tools = {tool.__name__: tool for tool in build_townbench_tools(env, tool_factory=_identity_tool)}

    move_result = tools["move_to"]("workshop")

    assert isinstance(move_result, str)
    assert "Moved to `Workshop`." in move_result
    assert "Effects: time +12, energy -3" in move_result
    assert "Current snapshot:" in move_result
    assert "Location: Workshop (workshop)" in move_result


def test_observation_snapshot_omits_empty_action_lists():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    tools = {tool.__name__: tool for tool in build_townbench_tools(env, tool_factory=_identity_tool)}

    move_result = tools["move_to"]("workshop")

    assert "- Storage Shelf (storage_shelf)" in move_result
    assert "- Storage Shelf (storage_shelf) Actions:" not in move_result


def test_build_langchain_agent_uses_config_and_tools():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()

    agent = build_langchain_agent(
        env,
        LangChainAgentConfig(model="test-model"),
        create_agent_fn=lambda model, tools, system_prompt: FakeCompiledAgent(model, tools, system_prompt),
        model_factory=lambda config: {"model_name": config.model},
        tool_factory=_identity_tool,
    )

    assert agent.model == {"model_name": "test-model"}
    assert "economic state" in agent.system_prompt
    assert "## Town Map" in agent.system_prompt
    assert {tool.__name__ for tool in agent.tools} >= {"move_to", "call_action", "check_status"}


def test_deepseek_chat_model_preserves_reasoning_content_from_response():
    model = DeepSeekChatOpenAI(
        model="deepseek-v4-flash",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )
    response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "Need to inspect first.",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "inspect",
                                "arguments": "{\"target_id\":\"plaza\"}",
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {},
    }

    result = model._create_chat_result(response)

    message = result.generations[0].message
    assert message.additional_kwargs["reasoning_content"] == "Need to inspect first."
    assert message.tool_calls[0]["name"] == "inspect"


def test_deepseek_chat_model_passes_reasoning_content_back_in_payload():
    model = DeepSeekChatOpenAI(
        model="deepseek-v4-flash",
        api_key="test-key",
        base_url="https://api.deepseek.com",
    )
    assistant_message = AIMessage(
        content="",
        additional_kwargs={"reasoning_content": "Need to inspect first."},
        tool_calls=[
            {
                "id": "call_1",
                "name": "inspect",
                "args": {"target_id": "plaza"},
            }
        ],
    )

    payload = model._get_request_payload(
        [
            HumanMessage(content="Start the episode."),
            assistant_message,
            ToolMessage(content="Inspected Plaza.", tool_call_id="call_1"),
        ]
    )

    assert payload["messages"][1]["role"] == "assistant"
    assert payload["messages"][1]["reasoning_content"] == "Need to inspect first."
    assert payload["messages"][1]["tool_calls"][0]["id"] == "call_1"


def test_langchain_config_keeps_default_recursion_limit_when_env_is_unset(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_AGENT_RECURSION_LIMIT", raising=False)

    config = LangChainAgentConfig.from_env()

    assert config.recursion_limit == 25


def test_build_default_instructions_includes_town_map_and_omits_episode_state():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))

    instructions = build_default_instructions(env)

    assert "## Town Map" in instructions
    assert (
        "- Plaza (`plaza`): The town center with a public notice board. Connected to: `library`, `workshop`"
        in instructions
    )
    assert "Opening briefing:" not in instructions
    assert "Public rules:" not in instructions
    assert "Money: 12" not in instructions
    assert "tea_ready" not in instructions


def test_build_default_instructions_uses_same_area_reachability():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "multi_area_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))

    instructions = build_default_instructions(env)

    assert (
        "- Supply Shop (`supply_shop`): A narrow shop selling sleeves, parts and other operating supplies. "
        "Connected to: `fuel_counter`, `market`, `plaza`" in instructions
    )


def test_run_langchain_agent_episode_returns_score_and_trace():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))

    result = run_langchain_agent_episode(
        env=env,
        config=LangChainAgentConfig(model="test-model", recursion_limit=4),
        build_agent_fn=_build_fake_agent,
    )

    assert result.final_output == "Order paid."
    assert result.opening_briefing.startswith("You arrived in town")
    assert result.public_rules[0].startswith("Actions cost time")
    assert result.done is False
    assert result.termination_reason is None
    assert result.score.survived_days == 1
    assert result.score.final_money == 21
    assert len(result.trace) == 3


def test_run_langchain_agent_episode_returns_partial_result_when_limit_exceeded():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))

    result = run_langchain_agent_episode(
        env=env,
        config=LangChainAgentConfig(model="test-model", recursion_limit=2),
        build_agent_fn=_build_fake_limit_agent,
    )

    assert result.runner_error == "Graph recursion limit reached"
    assert result.done is False
    assert result.termination_reason is None
    assert len(result.trace) == 1


def test_run_langchain_agent_episode_uses_explicit_recursion_limit():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))

    result = run_langchain_agent_episode(
        env=env,
        config=LangChainAgentConfig(model="test-model", recursion_limit=8),
        build_agent_fn=_build_fake_default_limit_agent,
    )

    assert result.final_output == "Used explicit recursion limit."


def test_run_langchain_agent_episode_streamed_emits_text_and_returns_result():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    text_chunks = []
    events = []

    result = asyncio.run(
        run_langchain_agent_episode_streamed(
            env=env,
            config=LangChainAgentConfig(model="test-model", recursion_limit=4),
            build_agent_fn=_build_fake_stream_agent,
            on_text_delta=text_chunks.append,
            on_event=events.append,
        )
    )

    assert "".join(text_chunks) == "Order paid."
    assert "tool_called" in events
    assert any(item.startswith("tool_output:") for item in events)
    assert result.final_output == "Order paid."
    assert result.done is False
