"""Safe CLI for the approved fixed-compute workload.

There is deliberately no arbitrary command option.  Privileged operations are
limited to the helper's frozen API and restoration is attempted on every exit.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from core.experiment import ExperimentStateMachine
from core.models import Configuration
from core.runner import WorkloadRunner
from core.store import Store
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
