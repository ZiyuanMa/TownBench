from __future__ import annotations

from engine.state import Location, WorldState
from runtime.env import TownBenchEnv


def build_default_instructions(env: TownBenchEnv) -> str:
    state = _resolve_prompt_state(env)
    return "\n\n".join((_build_core_instructions(), _render_town_map(state)))


def _build_core_instructions() -> str:
    return (
        "You are solving a TownBench episode. Your standing objective is to improve the agent's economic state, "
        "especially money, while respecting time and energy limits. Use the provided tools instead of inventing "
        "actions. Read tool outputs carefully, act only from the public context you are given, and prefer actions "
        "that create or preserve economic value. Do not assume the episode ends just because one task or order is "
        "finished. If the environment is still in progress, continue unless there is no clearly profitable next step. "
        "When timing matters, you may use wait to let time pass for opening windows or better payouts. Before "
        "concluding that you are done, check the current status."
    )


def _resolve_prompt_state(env: TownBenchEnv) -> WorldState:
    current_state = getattr(env, "_state", None)
    if current_state is not None:
        return current_state
    return getattr(env, "_initial_state")


def _render_town_map(state: WorldState) -> str:
    lines = ["## Town Map"]
    for location in sorted(state.locations.values(), key=lambda item: item.location_id):
        reachable_locations = _reachable_location_ids(state, location)
        connections = ", ".join(f"`{location_id}`" for location_id in reachable_locations) or "none"
        lines.append(
            f"- {location.name} (`{location.location_id}`): {location.description} Connected to: {connections}"
        )
    return "\n".join(lines)


def _reachable_location_ids(state: WorldState, location: Location) -> list[str]:
    nearby: set[str] = set(location.links)
    if location.area_id is not None:
        nearby.update(
            candidate.location_id
            for candidate in state.locations.values()
            if candidate.area_id == location.area_id
        )
    nearby.discard(location.location_id)
    return sorted(nearby)
