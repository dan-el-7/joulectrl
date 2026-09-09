"""Tests for the CLI `layouts` subcommand and topology→CoreClassMap conversion."""

from __future__ import annotations

import json

import pytest

from cli.main import build_parser, class_map_from_topology, list_layouts


TOPOLOGY = {
    "schema": "joulectrl.topology/1",
    "ncpu": 16,
    "n_cores": 8,
    "smt_groups": {"0": [0, 8], "1": [1, 9], "2": [2, 10], "3": [3, 11],
                    "4": [4, 12], "5": [5, 13], "6": [6, 14], "7": [7, 15]},
    "sockets": {"0": list(range(16))},
    "core_classes": {
        "source": "per-cpu cpuinfo_max_freq",
        "classes": {
            "class_0": {"cpus": [0, 2, 4, 6, 8, 10, 12, 14], "hw_max_freq": 5090910, "label": "fast"},
            "class_1": {"cpus": [1, 3, 5, 7, 9, 11, 13, 15], "hw_max_freq": 3506494, "label": "efficient"},
        },
    },
}


def test_class_map_from_topology():
    cm = class_map_from_topology(TOPOLOGY)
    assert cm.fast_class == "fast"
    assert cm.efficient_class == "efficient"
    assert cm.is_heterogeneous
    assert cm.classes["fast"] == [0, 2, 4, 6, 8, 10, 12, 14]
    assert cm.layouts["B"] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert cm.layouts["C"] == list(range(16))


def test_class_map_single_class_is_not_heterogeneous():
    doc = json.loads(json.dumps(TOPOLOGY))
    doc["core_classes"]["classes"] = {
        "class_0": {"cpus": list(range(16)), "hw_max_freq": 5090910, "label": "all"}
    }
    cm = class_map_from_topology(doc)
    assert not cm.is_heterogeneous
    assert cm.fast_class == "all" and cm.efficient_class == ""


def run_cli(argv: list[str], capsys) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.handler(args)


def test_layouts_command_table(tmp_path, capsys):
    topo = tmp_path / "topology.json"
    topo.write_text(json.dumps(TOPOLOGY))
    assert run_cli(["layouts", "--topology", str(topo)], capsys) == 0
    out = capsys.readouterr().out
    assert "layout_A_fast_4c" in out
    assert "heterogeneous=True" in out
    assert "cpus=[0,2,4,6]" in out


def test_layouts_command_json(tmp_path, capsys):
    topo = tmp_path / "topology.json"
    topo.write_text(json.dumps(TOPOLOGY))
    assert run_cli(["layouts", "--topology", str(topo), "--json"], capsys) == 0
    data = json.loads(capsys.readouterr().out)
    ids = {c["id"] for c in data}
    assert ids == {"layout_A_fast_4c", "layout_B_all_physical", "layout_C_all_logical", "layout_D_efficient_4c"}


def test_layouts_missing_fixture_fails_cleanly(tmp_path, capsys):
    assert run_cli(["layouts", "--topology", str(tmp_path / "nope.json")], capsys) == 2
    assert "not found" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# check-calibration subcommand
# ---------------------------------------------------------------------------

from tests.unit.test_sweep_check import C1_DOC, c2_doc, good_rows  # noqa: E402


def test_check_calibration_absent_fixture_returns_3(tmp_path, capsys):
    assert run_cli(["check-calibration", "--c2", str(tmp_path / "nope.json")], capsys) == 3
    assert "not found" in capsys.readouterr().out


def test_check_calibration_good_fixture_returns_0(tmp_path, capsys):
    (tmp_path / "c2.json").write_text(json.dumps(c2_doc(good_rows())))
    (tmp_path / "c1.json").write_text(json.dumps(C1_DOC))
    code = run_cli(
        ["check-calibration", "--c2", str(tmp_path / "c2.json"), "--c1", str(tmp_path / "c1.json")],
        capsys,
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "OK" in out
    assert "class fast" in out


def test_check_calibration_problems_return_1(tmp_path, capsys):
    doc = c2_doc(good_rows())
    doc["summary"]["fast"]["scaling_efficiency"] = 1.5  # superlinear -> problem
    (tmp_path / "c2.json").write_text(json.dumps(doc))
    (tmp_path / "c1.json").write_text(json.dumps(C1_DOC))
    code = run_cli(
        ["check-calibration", "--c2", str(tmp_path / "c2.json"), "--c1", str(tmp_path / "c1.json")],
        capsys,
    )
    assert code == 1
    assert "PROBLEMS FOUND" in capsys.readouterr().out


def test_doctor_command_renders_or_degrades_cleanly(capsys):
    # On Linux: exit 0 with a rendered report. On Windows: either a rendered
    # degraded report (exit 0) or a clean error (exit 2) — never a traceback.
    code = run_cli(["doctor"], capsys)
    assert code in (0, 2)
    captured = capsys.readouterr()
    assert "Traceback" not in captured.out + captured.err
