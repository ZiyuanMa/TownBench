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

from baselines.openai_agents.config import OpenAIAgentsConfig
from baselines.openai_agents.runner import run_openai_agents_episode, run_openai_agents_episode_streamed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a TownBench baseline with OpenAI Agents SDK.")
    parser.add_argument(
        "--scenario",
        default=str(ROOT / "scenarios" / "demo_town" / "scenario.yaml"),
        help="Path to the scenario yaml.",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional path to write the structured result json.",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=8,
        help="Maximum OpenAI Agents runner turns. This is separate from the scenario's environment limits.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional override for OPENAI_AGENT_MODEL.",
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
    env_model = os.getenv("OPENAI_AGENT_MODEL")

    missing = [
        name
        for name in ("OPENAI_API_KEY", "OPENAI_AGENT_MODEL")
        if not ((args.model or env_model) if name == "OPENAI_AGENT_MODEL" else os.getenv(name))
    ]
    if missing:
        print(
            "Missing required environment values: " + ", ".join(missing) + ". Fill them in `.env` or pass overrides.",
            file=sys.stderr,
        )
        return 1

    config = OpenAIAgentsConfig.from_env()
    config.max_turns = args.max_turns
    if args.model is not None:
        config.model = args.model

    if args.no_stream:
        result = run_openai_agents_episode(
            scenario_path=args.scenario,
            config=config,
        )
    else:
        result = asyncio.run(
            run_openai_agents_episode_streamed(
                scenario_path=args.scenario,
                config=config,
                on_text_delta=_print_stream_delta,
                on_event=_print_stream_event,
            )
        )
        _end_stream_line()

    payload = result.model_dump()
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


def _print_stream_delta(delta: str) -> None:
    print(delta, end="", file=sys.stderr, flush=True)


def _print_stream_event(message: str) -> None:
    print(f"\n[{message}]", file=sys.stderr, flush=True)


def _end_stream_line() -> None:
    print(file=sys.stderr, flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
