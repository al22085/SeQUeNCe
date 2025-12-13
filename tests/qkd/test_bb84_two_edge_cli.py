import importlib.util
from pathlib import Path


def _load_cli_module():
    cli_path = Path(__file__).resolve().parents[2] / "example" / "bb84_two_edge_cli.py"
    spec = importlib.util.spec_from_file_location("bb84_two_edge_cli", cli_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_bb84_two_edge_cli_sets_roles_and_runs():
    cli = _load_cli_module()
    result = cli.run_bb84_two_edge(runtime=1e7, distance=1e3, key_length=64, key_num=1, seed=123)

    # Roles must be assigned before timeline.init to avoid assertion in QKDNode.init.
    assert result["alice_role"] == 0
    assert result["bob_role"] == 1

    # Simulation should complete without throwing; basic output sanity.
    assert isinstance(result["throughput"], float)
