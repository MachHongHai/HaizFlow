import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def runner():
    path = Path(__file__).resolve().parents[1] / "scripts/run-release-tests.py"
    spec = importlib.util.spec_from_file_location("release_test_runner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_collection_records_every_node_and_rejects_external_modules(tmp_path):
    module = runner()
    output = tmp_path / "inventory.json"
    collector = module.Inventory(output)
    path = Path(__file__).resolve()
    collector.pytest_collection_finish(SimpleNamespace(items=[
        SimpleNamespace(path=path, nodeid="case-a"), SimpleNamespace(path=path, nodeid="case-b")]))
    assert json.loads(output.read_text("utf-8")) == {"tests/test_release_test_runner.py": ["case-a", "case-b"]}
    with pytest.raises(ValueError, match="repository"):
        collector.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(path=tmp_path / "other.py")]))


@pytest.mark.parametrize("omit", [False, True])
def test_success_requires_exact_inventory_without_deselection(tmp_path, monkeypatch, omit):
    module = runner()
    name = "tests/test_release_test_runner.py"
    expected = {name: [name + "::first", name + "::second"]}

    def collect(command, **_kwargs):
        Path(command[command.index("--inventory") + 1]).write_text(json.dumps(expected), encoding="utf-8")
        return SimpleNamespace(returncode=0)

    class Child:
        returncode = 0

        def __init__(self, command, **_kwargs):
            actual = {name: expected[name][:-1] if omit else expected[name]}
            Path(command[command.index("--inventory") + 1]).write_text(json.dumps(actual), encoding="utf-8")

        def wait(self, **_kwargs):
            return self.returncode

    monkeypatch.setattr(module.subprocess, "run", collect)
    monkeypatch.setattr(module.subprocess, "Popen", Child)
    reports = tmp_path / "reports"
    result = module.run_suite(SimpleNamespace(temporary=tmp_path / "work", reports=reports,
                                             tests=module.ROOT / "tests", workers=1))
    assert result == (1 if omit else 0)
    data = json.loads((reports / "result.json").read_text("utf-8"))
    assert data["collected_cases"] == 2 and data["complete_modules"] == 1
    assert data["passed"] is (not omit)
    assert data["modules"][0]["exact_inventory"] is (not omit)
