from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def resolve_output_path(
    *,
    root: Path,
    runner_name: str,
    scenario_path: str | Path,
    output_dir: str | Path | None,
) -> Path:
    if output_dir:
        output_dir_path = Path(output_dir).expanduser()
    else:
        scenario_file = Path(scenario_path)
        scenario_name = scenario_file.parent.name or scenario_file.stem or "scenario"
        output_dir_path = root / "artifacts" / "runs" / runner_name / scenario_name

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return output_dir_path / f"{timestamp}.json"


def save_result_payload(payload: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path
