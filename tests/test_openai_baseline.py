import asyncio
from pathlib import Path

from agents.exceptions import MaxTurnsExceeded
from agents import AgentUpdatedStreamEvent, RawResponsesStreamEvent, RunItemStreamEvent
from openai.types.responses.response_text_delta_event import ResponseTextDeltaEvent

from baselines.openai_agents.agent import build_openai_agent
from baselines.openai_agents.config import OpenAIAgentsConfig
from baselines.openai_agents.runner import (
    run_openai_agents_episode,
    run_openai_agents_episode_streamed,
)
from baselines.openai_agents.tools import build_townbench_tools
from runtime.env import TownBenchEnv
from scenario.loader import load_scenario


def _identity_tool(fn):
    return fn


class FakeAgent:
    def __init__(self, **kwargs):
        self.name = kwargs["name"]
        self.instructions = kwargs["instructions"]
        self.tools = kwargs["tools"]
        self.model = kwargs.get("model")


class FakeRunResult:
    def __init__(self, final_output: str):
        self.final_output = final_output


class FakeRunner:
    @staticmethod
    def run_sync(agent, _input, max_turns, run_config=None):
        assert max_turns == 4
        assert run_config is not None
        assert "Opening briefing:" in _input
        assert "Public rules:" in _input
        tools = {tool.__name__: tool for tool in agent.tools}
        tools["move_to"]("workshop")
        tools["call_action"]("tea_station", "brew_tea")
        return FakeRunResult("Tea is ready.")


class MaxTurnsRunner:
    @staticmethod
    def run_sync(agent, _input, max_turns, run_config=None):
        tools = {tool.__name__: tool for tool in agent.tools}
        tools["move_to"]("workshop")
        raise MaxTurnsExceeded(f"Max turns ({max_turns}) exceeded")


class FakeStreamedRunResult:
    def __init__(self, agent, tools):
        self.final_output = "Tea is ready."
        self._agent = agent
        self._tools = tools

    async def stream_events(self):
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta="Tea",
                item_id="item_1",
                logprobs=[],
                output_index=0,
                sequence_number=0,
                type="response.output_text.delta",
            )
        )
        yield RawResponsesStreamEvent(
            data=ResponseTextDeltaEvent(
                content_index=0,
                delta=" ready.",
                item_id="item_1",
                logprobs=[],
                output_index=0,
                sequence_number=1,
                type="response.output_text.delta",
            )
        )
        yield AgentUpdatedStreamEvent(new_agent=self._agent)
        tools = {tool.__name__: tool for tool in self._tools}
        tools["move_to"]("workshop")
        yield RunItemStreamEvent(name="move_to", item=_FakeToolCallItem())
        tools["call_action"]("tea_station", "brew_tea")
        yield RunItemStreamEvent(name="call_action", item=_FakeToolOutputItem())


class FakeStreamRunner:
    @staticmethod
    def run_streamed(agent, _input, max_turns, run_config=None):
        assert max_turns == 4
        assert run_config is not None
        return FakeStreamedRunResult(agent, agent.tools)


class _FakeToolCallItem:
    type = "tool_call_item"


class _FakeToolOutputItem:
    type = "tool_call_output_item"
    output = '{"success": true}'


def test_build_townbench_tools_executes_env_steps():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()
    tools = {tool.__name__: tool for tool in build_townbench_tools(env, function_tool_decorator=_identity_tool)}

    move_result = tools["move_to"]("workshop")
    action_result = tools["call_action"]("tea_station", "brew_tea")

    assert move_result["success"] is True
    assert action_result["success"] is True
    assert env.state.world_flags["tea_ready"] is True


def test_build_openai_agent_uses_config_and_tools():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))
    env.reset()

    agent = build_openai_agent(
        env,
        OpenAIAgentsConfig(agent_name="Town Bench Test", model="test-model"),
        agent_cls=FakeAgent,
        function_tool_decorator=_identity_tool,
    )

    assert agent.name == "Town Bench Test"
    assert agent.model == "test-model"
    assert {tool.__name__ for tool in agent.tools} >= {"move_to", "call_action", "check_status"}


def test_run_openai_agents_episode_returns_score_and_trace():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    state = load_scenario(scenario_path)
    state.termination_config.success_world_flags = ["tea_ready"]
    env = TownBenchEnv(state)

    result = run_openai_agents_episode(
        env=env,
        config=OpenAIAgentsConfig(max_turns=4),
        agent_cls=FakeAgent,
        runner_cls=FakeRunner,
        function_tool_decorator=_identity_tool,
    )

    assert result.final_output == "Tea is ready."
    assert result.opening_briefing.startswith("You arrived in town")
    assert result.public_rules[0].startswith("Actions cost time")
    assert result.done is True
    assert result.termination_reason == "success:tea_ready"
    assert result.score.survived_days == 1
    assert result.score.final_money == 12
    assert len(result.trace) == 2


def test_run_openai_agents_episode_returns_partial_result_when_max_turns_exceeded():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    env = TownBenchEnv(load_scenario(scenario_path))

    result = run_openai_agents_episode(
        env=env,
        config=OpenAIAgentsConfig(max_turns=2),
        agent_cls=FakeAgent,
        runner_cls=MaxTurnsRunner,
        function_tool_decorator=_identity_tool,
    )

    assert result.runner_error == "Max turns (2) exceeded"
    assert result.done is False
    assert result.termination_reason is None
    assert len(result.trace) == 1


def test_run_openai_agents_episode_streamed_emits_text_and_returns_result():
    scenario_path = Path(__file__).resolve().parents[1] / "scenarios" / "demo_town" / "scenario.yaml"
    state = load_scenario(scenario_path)
    state.termination_config.success_world_flags = ["tea_ready"]
    env = TownBenchEnv(state)
    text_chunks = []
    events = []

    result = asyncio.run(
        run_openai_agents_episode_streamed(
            env=env,
            config=OpenAIAgentsConfig(max_turns=4),
            agent_cls=FakeAgent,
            runner_cls=FakeStreamRunner,
            function_tool_decorator=_identity_tool,
            on_text_delta=text_chunks.append,
            on_event=events.append,
        )
    )

    assert "".join(text_chunks) == "Tea ready."
    assert any(item.startswith("tool_output:") for item in events)
    assert result.final_output == "Tea is ready."
    assert result.done is True
