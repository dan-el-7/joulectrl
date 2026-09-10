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


def run_doctor(args: argparse.Namespace) -> int:
    """Render A's capability report (core/doctor.py); degrades off-Linux."""
    from core.doctor import doctor_report, format_doctor

    # doctor_report() platform-guards the helper probe internally (A, 13:01Z),
    # so we can request the probe everywhere; off-Linux it degrades honestly.
    try:
        report = doctor_report()
    except Exception as exc:  # discovery may fail hard on non-Linux dev boxes
        print(f"capability discovery failed on this machine: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_doctor(report))
    return 0


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


def resolve_energy_backend(socket_path: str = "/run/joulectrl-helper.sock"):
    """Acquire the best available energy backend: root helper socket, direct RAPL, or synthetic."""
    if os.path.exists(socket_path):
        try:
            client = HelperClient(socket_path=socket_path)
            res = client.read_energy()
            if res.get("ok") and res.get("uj") is not None:
                return HelperEnergyBackend(client, 65532610987)
        except Exception:
            pass
    from energy.base import LinuxRaplBackend
    direct = LinuxRaplBackend()
    if direct.available():
        return direct
    from energy.synthetic import SyntheticEnergyBackend
    return SyntheticEnergyBackend()


def _print_single_run_report(record: RunRecord, workload) -> None:
    watts_str = f"{record.avg_power_w:.2f} W" if record.avg_power_w is not None else "N/A"
    joules_str = f"{record.package_energy_j:.2f} J" if record.package_energy_j is not None else "N/A"
    uj_diff = (record.end_energy_uj - record.start_energy_uj) if (record.end_energy_uj is not None and record.start_energy_uj is not None) else None
    uj_str = f"({uj_diff:,} µJ)" if uj_diff is not None else ""
    w_count = record.configuration.worker_count if record.configuration else 1
    cmd_display = " ".join(workload.command(w_count))

    print()
    print("=" * 68)
    print("            JOULECTRL REAL-WORK MEASUREMENT REPORT            ")
    print("=" * 68)
    print(f"Command:        {cmd_display}")
    print(f"Status:         {'SUCCESS' if record.status == 'success' else 'FAILED'} (Exit Code: {record.exit_code})")
    print(f"Elapsed Time:   {record.runtime_s:.3f} s")
    print(f"Package Energy: {joules_str} {uj_str}")
    print(f"Average Power:  {watts_str}")
    if record.configuration:
        cpus_str = ",".join(map(str, record.configuration.cpu_affinity)) if record.configuration.cpu_affinity else "All"
        boost_str = "ON (Stock Boost)" if record.configuration.boost else "OFF (Base Clock)"
        print(f"CPU Affinity:   [{cpus_str}] ({record.configuration.worker_count} workers)")
        print(f"Boost State:    {boost_str}")
    print("=" * 68)
    print()


def _print_comparison_report(stock: RunRecord, opt: RunRecord, workload) -> None:
    w_count = stock.configuration.worker_count if stock.configuration else 1
    cmd_display = " ".join(workload.command(w_count))
    t_stock = stock.runtime_s
    t_opt = opt.runtime_s
    t_delta_pct = ((t_opt - t_stock) / t_stock * 100.0) if t_stock > 0 else 0.0

    e_stock = stock.package_energy_j
    e_opt = opt.package_energy_j
    e_saved_pct = ((1.0 - e_opt / e_stock) * 100.0) if (e_stock and e_opt and e_stock > 0) else None

    p_stock = stock.avg_power_w
    p_opt = opt.avg_power_w
    p_saved_pct = ((1.0 - p_opt / p_stock) * 100.0) if (p_stock and p_opt and p_stock > 0) else None

    print()
    print("=" * 76)
    print("            JOULECTRL SIDE-BY-SIDE ENERGY & POWER COMPARISON            ")
    print("=" * 76)
    print(f"Workload: {cmd_display}")
    print("-" * 76)
    print(f"{'Metric':<22} {'Stock Baseline':<20} {'Energy-Optimized':<20} {'Delta':<12}")
    print("-" * 76)
    print(f"{'Runtime:':<22} {t_stock:.3f} s{'':<13} {t_opt:.3f} s{'':<13} {t_delta_pct:+.1f}%")

    e_stock_str = f"{e_stock:.2f} J" if e_stock else "N/A"
    e_opt_str = f"{e_opt:.2f} J" if e_opt else "N/A"
    e_delta_str = f"{e_saved_pct:+.1f}% saved" if e_saved_pct is not None else "N/A"
    print(f"{'Package Energy:':<22} {e_stock_str:<20} {e_opt_str:<20} {e_delta_str:<12}")

    p_stock_str = f"{p_stock:.2f} W" if p_stock else "N/A"
    p_opt_str = f"{p_opt:.2f} W" if p_opt else "N/A"
    p_delta_str = f"{p_saved_pct:+.1f}% lower" if p_saved_pct is not None else "N/A"
    print(f"{'Average Power:':<22} {p_stock_str:<20} {p_opt_str:<20} {p_delta_str:<12}")
    print("-" * 76)
    if e_saved_pct is not None and e_saved_pct > 0:
        print(f"Result: SUCCESS — Energy reduction of {e_saved_pct:.1f}% verified on real hardware!")
    elif e_saved_pct is not None:
        print(f"Result: Regressed by {abs(e_saved_pct):.1f}% under constrained mode.")
    print("=" * 76)
    print()


def _run_measure_comparison(workload, workers: int, cpus: list[int], backend, helper, args) -> int:
    """Run under Stock Boost and Energy-Optimized configurations and render side-by-side comparison."""
    cfg_stock = Configuration(
        id="stock_baseline",
        layout="stock",
        worker_count=workers,
        cpu_affinity=cpus,
        boost=True,
    )
    cfg_opt = Configuration(
        id="energy_optimized",
        layout="optimized",
        worker_count=workers,
        cpu_affinity=cpus,
        boost=False,
        freq_cap_khz=args.cap_khz or 2000000,
    )

    runner = WorkloadRunner(backend, working_dir=".")

    # 1. Execute Stock
    if helper:
        try:
            helper.begin_session()
            helper.apply_configuration({"boost": True})
        except Exception:
            pass
    rec_stock = runner.run(workload, "cli_compare_stock", cfg_stock, 1, timeout_s=args.timeout)

    # 2. Execute Optimized
    if helper:
        try:
            helper.apply_configuration({"boost": False})
        except Exception:
            pass
    rec_opt = runner.run(workload, "cli_compare_opt", cfg_opt, 1, timeout_s=args.timeout)

    if helper:
        try:
            helper.restore()
            helper.end_session()
        except Exception:
            pass

    if args.json:
        print(json.dumps({"stock": rec_stock.to_dict(), "optimized": rec_opt.to_dict()}, indent=2))
        return 0 if rec_stock.status == "success" and rec_opt.status == "success" else 1

    _print_comparison_report(rec_stock, rec_opt, workload)
    return 0 if rec_stock.status == "success" and rec_opt.status == "success" else 1


def run_measure_command(args: argparse.Namespace) -> int:
    """Measure the energy, runtime, and average wattage of an application, compile command, or demo."""
    from workloads.custom_command import CustomCommandWorkload, get_gcc_compile_demo_workload

    cmd_str = getattr(args, "target_command", None) or getattr(args, "command_arg", None)
    if not cmd_str or getattr(args, "demo", False):
        if getattr(args, "extended", False) or getattr(args, "heavy", False):
            demo_mode = "extended"
        elif getattr(args, "quick", False):
            demo_mode = "quick"
        else:
            demo_mode = "standard"
        workload = get_gcc_compile_demo_workload(mode=demo_mode)
    else:
        workload = CustomCommandWorkload(cmd_str)

    ncpu = os.cpu_count() or 4
    workers = args.workers if args.workers is not None else ncpu
    cpus = [int(c.strip()) for c in args.cpus.split(",")] if getattr(args, "cpus", None) else list(range(workers))

    backend = resolve_energy_backend(getattr(args, "socket", "/run/joulectrl-helper.sock"))
    sock_path = getattr(args, "socket", "/run/joulectrl-helper.sock")
    helper = HelperClient(socket_path=sock_path) if os.path.exists(sock_path) else None

    if getattr(args, "compare", False):
        return _run_measure_comparison(workload, workers, cpus, backend, helper, args)

    boost_val = True
    if getattr(args, "boost", None) == "off":
        boost_val = False
    elif getattr(args, "boost", None) == "on":
        boost_val = True

    cfg = Configuration(
        id="cli_run",
        layout="custom",
        worker_count=workers,
        cpu_affinity=cpus,
        boost=boost_val,
        freq_cap_khz=getattr(args, "cap_khz", None),
    )
    runner = WorkloadRunner(backend, working_dir=".")
    record = runner.run(workload, "cli_measure", cfg, 1, timeout_s=args.timeout)

    if args.json:
        print(json.dumps(record.to_dict(), indent=2))
        return 0 if record.status == "success" else 1

    _print_single_run_report(record, workload)
    return 0 if record.status == "success" else 1


def run_compile_demo(args: argparse.Namespace) -> int:
    """Friendly entry point for the GCC compilation demo."""
    setattr(args, "demo", True)
    setattr(args, "target_command", None)
    return run_measure_command(args)


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
    doctor = sub.add_parser(
        "doctor", help="capability report: topology, classes, controls, energy source"
    )
    doctor.add_argument("--json", action="store_true", help="emit the raw report dict")
    doctor.set_defaults(handler=run_doctor)
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

    measure = sub.add_parser(
        "measure",
        help="measure energy, runtime, and average wattage for any command or GCC compile demo",
    )
    measure.add_argument(
        "target_command",
        nargs="?",
        default=None,
        help="command to execute (defaults to GCC compile demo if omitted)",
    )
    measure.add_argument("--demo", action="store_true", help="run default GCC compile demo")
    measure.add_argument("--extended", "--heavy", action="store_true", help="compile full zstd project + test suites (~25s)")
    measure.add_argument("--quick", action="store_true", help="quick compile kernel (CI testing only)")
    measure.add_argument("--compare", action="store_true", help="compare Stock Boost vs Energy-Optimized side-by-side")
    measure.add_argument("--workers", type=int, default=None, help="worker count (default: all cores)")
    measure.add_argument("--cpus", default=None, help="comma-separated CPU IDs (e.g. 0,1,2,3)")
    measure.add_argument("--boost", choices=["on", "off"], default=None, help="force boost state")
    measure.add_argument("--cap-khz", type=int, default=None, help="frequency cap clamp in kHz")
    measure.add_argument("--timeout", type=float, default=180.0, help="timeout in seconds")
    measure.add_argument("--socket", default="/run/joulectrl-helper.sock", help="helper socket path")
    measure.add_argument("--json", action="store_true", help="emit JSON report")
    measure.set_defaults(handler=run_measure_command)

    compile_demo = sub.add_parser(
        "compile-demo",
        help="run real GCC C compilation demo (10s+ multi-core benchmark) with live wattage & energy tracking",
    )
    compile_demo.add_argument("--extended", "--heavy", action="store_true", help="compile full zstd project + test suites (~25s)")
    compile_demo.add_argument("--quick", action="store_true", help="quick compile kernel (CI testing only)")
    compile_demo.add_argument("--compare", action="store_true", help="compare Stock Boost vs Energy-Optimized side-by-side")
    compile_demo.add_argument("--workers", type=int, default=None, help="worker count (default: all cores)")
    compile_demo.add_argument("--cpus", default=None, help="comma-separated CPU IDs (e.g. 0,1,2,3)")
    compile_demo.add_argument("--cap-khz", type=int, default=None, help="frequency cap clamp in kHz")
    compile_demo.add_argument("--timeout", type=float, default=180.0, help="timeout in seconds")
    compile_demo.add_argument("--socket", default="/run/joulectrl-helper.sock", help="helper socket path")
    compile_demo.add_argument("--json", action="store_true", help="emit JSON report")
    compile_demo.set_defaults(handler=run_compile_demo)

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
