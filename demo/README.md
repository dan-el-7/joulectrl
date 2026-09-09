# Joulectrl Live Presentation & Demonstration (`demo/`)

This directory contains executable assets for the live hackathon presentation per PLAN §13.

## Live Demo Script Walkthrough

Run the demo from the repo root:
```bash
# Run full demonstration
python demo/run_demo.py

# Or run a specific phase with custom preset
python demo/run_demo.py --phase kernel --preset light

# CLI Options:
#   --phase {all,capabilities,kernel,watch,pareto,optimizer,validation}
#   --preset {smoke,light,standard,heavy}
```

### Demonstration Phases

1. **Phase 1: Hardware Feasibility & Capability Report**
   - Shows CPU topology (Ryzen AI 7 350: 8 physical cores, 16 threads).
   - Shows dual core-class mapping (Zen 5 on even CPUs up to 5.09 GHz, Zen 5c on odd CPUs up to 3.51 GHz).
   - Validates live hardware counter: `package-0` via sysfs powercap (idle verified at 8.6 mJ/s).
   - Evaluates C1 single-core stock calibration (Zen 5 1.45x throughput ratio over Zen 5c).
   - Evaluates C2 dense sweep and canonical 8-point effective control space (`calibration_c2_effective.json`), demonstrating the 29.6% energy reduction tradeoff headline on Fast Zen 5 (4-worker).
   - Confirms pre-demo controls re-verification pass (`controls_reverify.json`) and recovery snapshot/restoration readiness.

2. **Phase 2: Deterministic Compute Kernel (Fixed Work Benchmark)**
   - Compiles and runs `workloads/kernel/fixed_compute` live.
   - Executes across worker thread counts 1, 2, and 4.
   - Demonstrates that total work is constant and the cryptographic checksum is strictly invariant (`0x23e23165be5ef4b6`).

3. **Demo Beat: Passive Watch Mode ("Point it at anything you run")**
   - Learns package power idle baseline (~10W) without manual timing.
   - Detects sustained power spikes (>= 2s) and backdates onset to the first above-band sample.
   - Absorbs mid-task dips within the grace window (maintains active task state).
   - Backtracks task end to the last above-band sample after sustained idle return.
   - Computes suggested budget (+5% margin) pre-filling the Setup slider.
   - Enforces honesty guards (`mode="watch"`, excluded from Pareto evidence).

4. **Phase 3: Workload Profiling & Pareto Frontier**
   - Displays measured configurations across Layouts A, B, C, and D.
   - Shows trade-off frontier between execution speed and package energy consumption.

5. **Phase 4: Deterministic Optimizer**
   - Evaluates Deadline Mode with 5% guarded runtime margin.
   - Evaluates Preference Mode (§6c) targeting <= 70% energy and >= 60% performance.
   - Selects lowest-energy measured candidate (`cfg_zen5c_4c_3000`) achieving 44.6% energy savings.

6. **Phase 5: Fresh Validation & Grounded Explanation**
   - Executes independent fresh validation pairs (baseline vs selected candidate).
   - Confirms all runs satisfied the runtime budget.
   - Generates grounded, factual plain-English explanation (offline template with optional local 7B / cloud LLM enhancement).
   - Verifies system restoration.
