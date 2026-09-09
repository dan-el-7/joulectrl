"""Safe CLI for the approved fixed-compute workload.

There is deliberately no arbitrary command option.  Privileged operations are
limited to the helper's frozen API and restoration is attempted on every exit.
"""

from __future__ import annotations

import argparse
import json
import sys
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from core.experiment import ExperimentStateMachine
from core.models import Configuration, CoreClassMap
from core.runner import WorkloadRunner
from core.store import Store
from core.validation import dedupe_configurations, layout_configurations
from helper.client import HelperClient
from workloads.fixed_compute import FixedComputeWorkload


class HelperEnergyBackend:
    name = "helper:package-0"

    def __init__(self, helper: HelperClient, max_range_uj: int) -> None:
        self.helper = helper
        self.range_uj = max_range_uj

    def read_uj(self) -> Optional[int]:
        response = self.helper.read_energy()
        return int(response["uj"]) if response.get("ok") and response.get("uj") is not None else None

    def max_range_uj(self) -> int:
        return self.range_uj


def _capability(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def class_map_from_topology(doc: dict) -> CoreClassMap:
    """Convert A's topology fixture (core_classes block) to a CoreClassMap."""
    classes_block = doc.get("core_classes") or {}
    raw = classes_block.get("classes") or {}
    classes: dict[str, list[int]] = {}
    label_by_class: dict[str, str] = {}
    for key, entry in raw.items():
        label = entry.get("label") or key
        classes[label] = list(entry.get("cpus") or [])
        label_by_class[key] = label
    fast = ""
    efficient = ""
    # Fast class = highest hardware max frequency among labeled classes.
    def hw_max(entry: dict) -> int:
        return int(entry.get("hw_max_freq") or 0)

    labeled = sorted(raw.values(), key=hw_max, reverse=True)
    if labeled:
        fast = labeled[0].get("label") or ""
        if len(labeled) > 1:
            efficient = labeled[-1].get("label") or ""
    # Layout masks from smt groups: B = one CPU per physical core, C = all logical.
    smt_groups = doc.get("smt_groups") or {}
    layout_b = sorted(int(first) for first in (g[0] for g in smt_groups.values()) if first is not None) if smt_groups else []
    layout_c = sorted(
        cpu for cpus in (doc.get("sockets") or {}).values() for cpu in cpus
    )
    layouts: dict[str, list[int]] = {}
    if layout_b:
        layouts["B"] = layout_b
    if layout_c:
        layouts["C"] = layout_c
    return CoreClassMap(
        classes=classes,
        layouts=layouts,
        fast_class=fast,
        efficient_class=efficient,
        is_heterogeneous=bool(fast and efficient and fast != efficient),
        details={"source": classes_block.get("source", "")},
    )


def list_layouts(args: argparse.Namespace) -> int:
    path = Path(args.topology)
    if not path.exists():
        print(f"topology fixture not found: {path}", file=sys.stderr)
        return 2
    doc = json.loads(path.read_text(encoding="utf-8"))
    class_map = class_map_from_topology(doc)
    configs = dedupe_configurations(layout_configurations(class_map))
    if args.json:
        print(json.dumps([c.to_dict() for c in configs], indent=2))
        return 0
    print(f"class map: fast={class_map.fast_class!r} efficient={class_map.efficient_class!r} "
          f"heterogeneous={class_map.is_heterogeneous}")
    for config in configs:
        cpus = ",".join(str(c) for c in config.cpu_affinity)
        description = config.metadata.get("description", "")
        print(f"{config.id:<28} layout={config.layout} workers={config.worker_count:<3} cpus=[{cpus}]  {description}")
    return 0


def check_calibration(args: argparse.Namespace) -> int:
    """Run the sweep sanity cross-check; exit 0 = clean, 1 = problems, 3 = absent."""
    from core.sweep_check import check_calibration_files

    report = check_calibration_files(args.c2, args.c1)
    if report is None:
        print(f"C2 fixture not found: {args.c2} (nothing to check yet)")
        return 3
    if report.ok:
        print("calibration sweep cross-check: OK")
    else:
        print("calibration sweep cross-check: PROBLEMS FOUND")
    for problem in report.problems:
        print(f"  problem: {problem}")
    for warning in report.warnings:
        print(f"  warning: {warning}")
    for cname, info in report.classes.items():
        print(f"  class {cname}: stock={info['n_stock']} sweep={info['n_sweep']} "
              f"caps={len(info['median_throughput_per_cap'])}")
    return 0 if report.ok else 1


def run_fixed_compute(args: argparse.Namespace) -> int:
    capability = _capability(Path(args.capabilities))
    energy = capability.get("package_energy", {})
    max_range = int(energy.get("max_energy_range_uj", 0))
    if max_range <= 0:
        raise RuntimeError("capability report has no verified package counter range")

    helper = HelperClient(socket_path=args.socket)
    store = Store(args.db)
    experiment_id = f"exp_{uuid.uuid4().hex[:12]}_fixed_compute"
    store.create_experiment(experiment_id, "fixed_compute", runtime_budget_s=args.timeout)
    machine = ExperimentStateMachine(store, experiment_id)
    session_started = False
    try:
        response = helper.begin_session()
        if not response.get("ok"):
            raise RuntimeError(f"helper begin_session failed: {response}")
        session_started = True
        control = {"boost": False}
        if args.cap_khz is not None:
            n_policies = int(capability.get("cpufreq", {}).get("n_policies", 0))
            control["policy_freq_caps_khz"] = {
                f"policy{i}": args.cap_khz for i in range(n_policies)
            }
        applied = helper.apply_configuration(control)
        if not applied.get("ok"):
            raise RuntimeError(f"helper apply_configuration failed: {applied}")

        configuration = Configuration(
            id="fixed_compute_cli",
            layout="all",
            worker_count=args.workers,
            freq_cap_khz=args.cap_khz,
            boost=False,
            policy_freq_caps_khz=control.get("policy_freq_caps_khz", {}),
        )
        backend = HelperEnergyBackend(helper, max_range)
        with tempfile.TemporaryDirectory(prefix="joulectrl_cli_") as workdir:
            workload = FixedComputeWorkload(chunks=args.chunks, iters=args.iters)
            runner = WorkloadRunner(backend, store=store, working_dir=workdir)
            record = machine.run_profile_point(
                runner, workload, configuration, 1, timeout_s=args.timeout
            )
        print(json.dumps({"experiment_id": experiment_id, "run": record.to_dict()}, indent=2))
        return 0 if record.status == "success" and record.energy_available else 1
    finally:
        if session_started:
            machine.restore(helper.restore)
            helper.end_session()
        store.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="joulectrl")
    sub = parser.add_subparsers(dest="command", required=True)
    layouts = sub.add_parser(
        "layouts", help="list execution-layout validation points from the class map"
    )
    layouts.add_argument("--topology", default="fixtures/real/topology.json")
    layouts.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    layouts.set_defaults(handler=list_layouts)
    check = sub.add_parser(
        "check-calibration",
        help="sanity cross-check on calibration sweep fixtures (C1/C2)",
    )
    check.add_argument("--c2", default="fixtures/real/calibration_c2.json")
    check.add_argument("--c1", default="fixtures/real/calibration_c1.json")
    check.set_defaults(handler=check_calibration)
    run = sub.add_parser("run-fixed", help="measure the approved fixed-compute workload")
    run.add_argument("--capabilities", default="fixtures/real/capability_report.json")
    run.add_argument("--socket", default="/run/joulectrl-helper.sock")
    run.add_argument("--db", default=None)
    run.add_argument("--workers", type=int, default=4)
    run.add_argument("--chunks", type=int, default=1024)
    run.add_argument("--iters", type=int, default=50000)
    run.add_argument("--cap-khz", type=int, default=None)
    run.add_argument("--timeout", type=float, default=120.0)
    run.set_defaults(handler=run_fixed_compute)
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except Exception as exc:
        print(f"joulectrl: error: {exc}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
