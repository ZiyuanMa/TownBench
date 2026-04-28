import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from runtime.env import TownBenchEnv
from scenario.loader import load_scenario
from townbench_agents.openai.agent import build_openai_agent
from townbench_agents.openai.config import OpenAIAgentConfig
from townbench_agents.openai.deepseek import (
    DeepSeekOpenAIProvider,
    _prepare_deepseek_input_items,
)
from townbench_agents.openai.runner import (
    _build_run_config,
    run_openai_agent_episode,
    run_openai_agent_episode_streamed,
)
from townbench_agents.openai.tools import build_townbench_tools


def _fake_tool_factory(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeAgent:
    def __init__(self, **kwargs):
        self.name = kwargs["name"]
        self.instructions = kwargs["instructions"]
        self.tools = kwargs["tools"]
        self.model = kwargs["model"]
        self.model_settings = kwargs["model_settings"]


class FakeModelSettings:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class FakeRunner:
    @staticmethod
    def run_sync(agent, agent_input, *, max_turns=None, run_config=None):
        assert max_turns == 4
        assert run_config is not None
        assert "Opening briefing:" in agent_input
        assert "Public rules:" in agent_input
        assert "Current location: Plaza (plaza)" in agent_input
        tools = {tool.name: tool for tool in agent.tools}
        asyncio.run(tools["move_to"].on_invoke_tool(None, json.dumps({"target_id": "workshop"})))
        asyncio.run(
            tools["call_action"].on_invoke_tool(
                None,
                json.dumps({"object_id": "tea_station", "action_name": "brew_tea"}),
            )
        )
        asyncio.run(
            tools["call_action"].on_invoke_tool(
                None,
                json.dumps({"object_id": "completion_log", "action_name": "record_order"}),
            )
        )
        return SimpleNamespace(final_output="Order paid.")


class MaxTurnsExceeded(Exception):
    pass


class FakeLimitRunner:
    @staticmethod
    def run_sync(agent, agent_input, *, max_turns=None, run_config=None):
        tools = {tool.name: tool for tool in agent.tools}
        asyncio.run(tools["move_to"].on_invoke_tool(None, json.dumps({"target_id": "workshop"})))
        raise MaxTurnsExceeded("Max turns exceeded")


class FakeStreamResult:
    final_output = "Order paid."

    def __init__(self, agent):
        self.agent = agent

    async def stream_events(self):
        yield SimpleNamespace(type="raw_response_event", data=SimpleNamespace(delta="Order"))
        yield SimpleNamespace(
            type="run_item_stream_event",
            name="tool_called",
            item=SimpleNamespace(type="tool_call_item"),
        )
        tools = {tool.name: tool for tool in self.agent.tools}
        move_output = await tools["move_to"].on_invoke_tool(None, json.dumps({"target_id": "workshop"}))
        yield SimpleNamespace(
            type="run_item_stream_event",
            name="tool_output",
            item=SimpleNamespace(type="tool_call_output_item", output=move_output),
        )
        await tools["call_action"].on_invoke_tool(
            None,
            json.dumps({"object_id": "tea_station", "action_name": "brew_tea"}),
        )
        await tools["call_action"].on_invoke_tool(
            None,
            json.dumps({"object_id": "completion_log", "action_name": "record_order"}),
        )
        yield SimpleNamespace(type="raw_response_event", data=SimpleNamespace(delta=" paid."))


class FakeStreamRunner:
    @staticmethod
    def run_streamed(agent, agent_input, *, max_turns=None, run_config=None):
        assert max_turns == 4
        assert run_config is not None
        return FakeStreamResult(agent)


def _build_fake_agent(env, config, **_kwargs):
    return FakeAgent(
        name="TownBench Agent",
        instructions="fake instructions",
        tools=build_townbench_tools(env, tool_factory=_fake_tool_factory),
        model=config.model,
        model_settings=FakeModelSettings(parallel_tool_calls=False),
    )


def _scenario_path() -> Path:
    return Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"


def test_build_openai_tools_execute_env_steps():
    env = TownBenchEnv(load_scenario(_scenario_path()))
    env.reset()
    tools = {tool.name: tool for tool in build_townbench_tools(env, tool_factory=_fake_tool_factory)}

    move_result = asyncio.run(tools["move_to"].on_invoke_tool(None, json.dumps({"target_id": "workshop"})))
    brew_result = asyncio.run(
        tools["call_action"].on_invoke_tool(
            None,
            json.dumps({"object_id": "tea_station", "action_name": "brew_tea"}),
        )
    )
    payout_result = asyncio.run(
        tools["call_action"].on_invoke_tool(
            None,
            json.dumps({"object_id": "completion_log", "action_name": "record_order"}),
        )
    )

    assert "Moved to `Workshop`." in move_result
    assert "You brewed a fresh pot of tea." in brew_result
    assert "You recorded the finished tea order and collected payment." in payout_result
    assert env.state.agent.money == 21


def test_openai_tool_schemas_include_required_and_optional_args():
    env = TownBenchEnv(load_scenario(_scenario_path()))
    env.reset()
    tools = {tool.name: tool for tool in build_townbench_tools(env, tool_factory=_fake_tool_factory)}

    assert tools["move_to"].params_json_schema["required"] == ["target_id"]
    assert tools["wait"].params_json_schema["properties"]["minutes"]["type"] == "integer"
    call_action_schema = tools["call_action"].params_json_schema
    assert call_action_schema["required"] == ["object_id", "action_name"]
    assert "action_args" in call_action_schema["properties"]
    assert call_action_schema["properties"]["action_args"]["default"] is None


def test_build_openai_agent_uses_config_prompt_tools_and_sequential_tool_calls():
    env = TownBenchEnv(load_scenario(_scenario_path()))
    env.reset()

    agent = build_openai_agent(
        env,
        OpenAIAgentConfig(model="test-model", temperature=0.2, max_tokens=512),
        agent_factory=FakeAgent,
        model_settings_factory=FakeModelSettings,
        tool_factory=_fake_tool_factory,
    )

    assert agent.name == "TownBench Agent"
    assert agent.model == "test-model"
    assert "economic state" in agent.instructions
    assert "## Town Map" in agent.instructions
    assert {tool.name for tool in agent.tools} >= {"move_to", "call_action", "check_status"}
    assert agent.model_settings.kwargs == {
        "temperature": 0.2,
        "max_tokens": 512,
        "parallel_tool_calls": False,
    }


def test_run_openai_agent_episode_returns_score_and_trace():
    env = TownBenchEnv(load_scenario(_scenario_path()))

    result = run_openai_agent_episode(
        env=env,
        config=OpenAIAgentConfig(model="test-model", max_turns=4),
        build_agent_fn=_build_fake_agent,
        runner=FakeRunner,
    )

    assert result.final_output == "Order paid."
    assert result.done is False
    assert result.score.final_money == 21
    assert len(result.trace) == 3


def test_run_openai_agent_episode_returns_partial_result_when_max_turns_exceeded():
    env = TownBenchEnv(load_scenario(_scenario_path()))

    result = run_openai_agent_episode(
        env=env,
        config=OpenAIAgentConfig(model="test-model", max_turns=2),
        build_agent_fn=_build_fake_agent,
        runner=FakeLimitRunner,
    )

    assert result.runner_error == "Max turns exceeded"
    assert result.done is False
    assert len(result.trace) == 1


def test_run_openai_agent_episode_streamed_emits_text_and_returns_result():
    env = TownBenchEnv(load_scenario(_scenario_path()))
    text_chunks = []
    events = []

    result = asyncio.run(
        run_openai_agent_episode_streamed(
            env=env,
            config=OpenAIAgentConfig(model="test-model", max_turns=4),
            build_agent_fn=_build_fake_agent,
            runner=FakeStreamRunner,
            on_text_delta=text_chunks.append,
            on_event=events.append,
        )
    )

    assert "".join(text_chunks) == "Order paid."
    assert "tool_called" in events
    assert any(item.startswith("tool_output:") for item in events)
    assert result.final_output == "Order paid."
    assert result.score.final_money == 21
    assert len(result.trace) == 3


def test_openai_agents_sdk_import_is_not_shadowed():
    from agents import Agent

    assert Agent.__module__.startswith("agents.")


def test_openai_run_config_uses_chat_completions_for_deepseek_endpoint():
    config = OpenAIAgentConfig(
        model="deepseek-v4-flash",
        base_url="https://api.deepseek.com",
    )

    run_config = _build_run_config(config)

    assert run_config.tracing_disabled is True
    assert run_config.reasoning_item_id_policy == "omit"
    assert isinstance(run_config.model_provider, DeepSeekOpenAIProvider)
    assert run_config.model_provider._stored_base_url == "https://api.deepseek.com"
    assert run_config.model_provider._use_responses is False


def test_openai_run_config_keeps_responses_api_for_openai_defaults():
    config = OpenAIAgentConfig(model="gpt-4.1", base_url=None)

    run_config = _build_run_config(config)

    assert run_config.tracing_disabled is False
    assert run_config.reasoning_item_id_policy is None


def test_deepseek_input_preparation_keeps_reasoning_with_text_and_tool_call():
    items = [
        {
            "type": "reasoning",
            "id": "fake-id",
            "summary": [{"type": "summary_text", "text": "need current status"}],
        },
        {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "I will check."}],
        },
        {
            "type": "function_call",
            "call_id": "call_status",
            "name": "check_status",
            "arguments": "{}",
        },
    ]

    prepared = _prepare_deepseek_input_items(items)

    assert [item["type"] for item in prepared] == ["message", "reasoning", "function_call"]
    assert "id" not in prepared[1]

    from agents.models.chatcmpl_converter import Converter

    messages = Converter.items_to_messages(prepared, model="deepseek-v4-flash")
    assert messages == [
        {
            "role": "assistant",
            "content": "I will check.",
            "tool_calls": [
                {
                    "id": "call_status",
                    "type": "function",
                    "function": {"name": "check_status", "arguments": "{}"},
                }
            ],
            "reasoning_content": "need current status",
        }
    ]
