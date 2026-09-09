# Joulectrl Live Presentation & Demonstration (`demo/`)

This directory contains executable assets for the live hackathon presentation per PLAN §13.

## Live Demo Script Walkthrough

Run the demo from the repo root:
```bash
python demo/run_demo.py
```

### Demonstration Phases

1. **Phase 1: Hardware Feasibility & Capability Report**
   - Shows CPU topology (Ryzen AI 7 350: 8 physical cores, 16 threads).
   - Shows dual core-class mapping (Zen 5 on even CPUs up to 5.09 GHz, Zen 5c on odd CPUs up to 3.51 GHz).
   - Validates live hardware counter: `package-0` via sysfs powercap (idle verified at 8.6 mJ/s).
   - Confirms recovery snapshot mechanism and restoration readiness.

2. **Phase 2: Deterministic Compute Kernel (Fixed Work Benchmark)**
   - Compiles and runs `workloads/kernel/fixed_compute` live.
   - Executes across worker thread counts 1, 2, and 4.
   - Demonstrates that total work is constant and the cryptographic checksum is strictly invariant (`0x23e23165be5ef4b6`).

3. **Phase 3: Workload Profiling & Pareto Frontier**
   - Displays measured configurations across Layouts A, B, C, and D.
   - Shows trade-off frontier between execution speed and package energy consumption.

4. **Phase 4: Deterministic Optimizer**
   - Evaluates Deadline Mode with 5% guarded runtime margin.
   - Evaluates Preference Mode (§6c) targeting ≤70% energy and ≥60% performance.
   - Selects lowest-energy measured candidate (`cfg_zen5c_4c_3000`) achieving 44.6% energy savings.

5. **Phase 5: Fresh Validation & Grounded Explanation**
   - Executes independent fresh validation pairs (baseline vs selected candidate).
   - Confirms all runs satisfied the runtime budget.
   - Generates grounded, factual plain-English explanation (offline template with optional local 7B / cloud LLM enhancement).
   - Verifies system restoration.
