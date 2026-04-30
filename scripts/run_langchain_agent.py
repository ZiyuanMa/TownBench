from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_result_utils import resolve_output_path, save_result_payload
from townbench_agents.langchain.config import LangChainAgentConfig
from townbench_agents.langchain.runner import run_langchain_agent_episode, run_langchain_agent_episode_streamed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a TownBench agent with LangChain.")
    parser.add_argument(
        "--scenario",
        default=str(ROOT / "scenarios" / "demo_town" / "scenario.yaml"),
        help="Path to the scenario yaml.",
    )
    parser.add_argument(
        "--output-dir",
        default="",
        dest="output_dir",
        help="Directory to write the structured result json. Defaults to artifacts/runs/langchain/<scenario>/.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional override for LANGCHAIN_AGENT_MODEL.",
    )
    parser.add_argument(
        "--recursion-limit",
        type=int,
        default=None,
        help="Optional override for the LangGraph recursion limit.",
    )
    parser.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable streaming text output and wait for the final structured result.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    env_model = os.getenv("LANGCHAIN_AGENT_MODEL")

    if not (args.model or env_model):
        print(
            "Missing required environment value: LANGCHAIN_AGENT_MODEL. Fill it in `.env` or pass --model.",
            file=sys.stderr,
        )
        return 1
    if not os.getenv("OPENAI_API_KEY"):
        print(
            "Missing required environment value: OPENAI_API_KEY. Fill it in `.env` before running the agent.",
            file=sys.stderr,
        )
        return 1

    config = LangChainAgentConfig.from_env()
    if args.model is not None:
        config.model = args.model
    if args.recursion_limit is not None:
        config.recursion_limit = args.recursion_limit

    if args.no_stream:
        result = run_langchain_agent_episode(
            scenario_path=args.scenario,
            config=config,
        )
    else:
        result = asyncio.run(
            run_langchain_agent_episode_streamed(
                scenario_path=args.scenario,
                config=config,
                on_text_delta=_print_stream_delta,
                on_event=_print_stream_event,
            )
        )
        _end_stream_line()

    payload = result.model_dump()
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    output_path = resolve_output_path(
        root=ROOT,
        runner_name="langchain",
        scenario_path=args.scenario,
        output_dir=args.output_dir or None,
    )
    save_result_payload(payload, output_path)
    print(f"Saved result to {output_path}", file=sys.stderr)

    return 0


def _print_stream_delta(delta: str) -> None:
    print(delta, end="", file=sys.stderr, flush=True)


def _print_stream_event(message: str) -> None:
    print(f"\n[{message}]", file=sys.stderr, flush=True)


def _end_stream_line() -> None:
    print(file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
