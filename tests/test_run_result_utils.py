from pathlib import Path

from scripts.run_result_utils import resolve_output_path, save_result_payload


def test_resolve_output_path_uses_explicit_output_dir(tmp_path):
    explicit_dir = tmp_path / "custom"

    resolved = resolve_output_path(
        root=tmp_path,
        runner_name="openai",
        scenario_path="scenarios/demo_town/scenario.yaml",
        output_dir=explicit_dir,
    )

    assert resolved.parent == explicit_dir
    assert resolved.suffix == ".json"


def test_resolve_output_path_generates_default_artifact_path(tmp_path):
    resolved = resolve_output_path(
        root=tmp_path,
        runner_name="langchain",
        scenario_path="scenarios/multi_area_town/scenario.yaml",
        output_dir=None,
    )

    assert resolved.parent == tmp_path / "artifacts" / "runs" / "langchain" / "multi_area_town"
    assert resolved.suffix == ".json"
    assert resolved.name.endswith(".json")


def test_save_result_payload_writes_json(tmp_path):
    output_path = tmp_path / "artifacts" / "runs" / "openai" / "demo_town" / "result.json"
    payload = {"scenario_id": "demo_town", "final_output": "Order paid."}

    written_path = save_result_payload(payload, output_path)

    assert written_path == output_path
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8") == '{\n  "scenario_id": "demo_town",\n  "final_output": "Order paid."\n}'
