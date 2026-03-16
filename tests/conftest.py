from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.state import AgentState, Location, Skill, WorldObject, WorldState


@pytest.fixture()
def minimal_world_state() -> WorldState:
    return WorldState(
        current_time="Day 1, 08:00",
        agent=AgentState(location_id="plaza", money=20, energy=100),
        locations={
            "plaza": Location(
                location_id="plaza",
                name="Plaza",
                description="The town center.",
                links=["market"],
                object_ids=["bulletin"],
                tags=["public"],
            ),
            "market": Location(
                location_id="market",
                name="Market",
                description="A small market hall.",
                links=["plaza"],
                object_ids=["counter"],
                tags=["shop"],
            ),
        },
        objects={
            "bulletin": WorldObject(
                object_id="bulletin",
                name="Bulletin Board",
                object_type="board",
                location_id="plaza",
                summary="A board with public notices.",
                visible_state={"notice_count": 2},
                action_ids=["inspect"],
            ),
            "counter": WorldObject(
                object_id="counter",
                name="Market Counter",
                object_type="counter",
                location_id="market",
                summary="A checkout counter for purchases.",
                visible_state={"open": True},
                action_ids=["inspect"],
            ),
        },
        skills={
            "safety_basics": Skill(
                skill_id="safety_basics",
                name="Safety Basics",
                description="Simple safety reminders for acting in the town.",
                content="Always check your location before acting.",
            )
        },
        scenario_id="m1_test",
        seed=7,
    )
