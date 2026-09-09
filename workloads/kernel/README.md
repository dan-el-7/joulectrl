# Deterministic Compute Kernel (`fixed_compute`)

This is the deterministic compute kernel for `joulectrl`, used for:
1. **Agent A's calibration**: C1 single-core baseline (stock) and C2 dense multi-core scaling sweep.
2. **Workload B (CPU Benchmark)**: Contasting workload plugin (`workloads/fixed_compute.py`).

## Core Invariants

1. **Fixed total chunks**: Default `4096` chunks.
2. **Fixed work per chunk**: Default `100000` SplitMix64 non-linear integer mixing rounds per chunk.
3. **Partitioning**: Chunks are statically partitioned across worker threads into disjoint contiguous blocks. Changing worker count (e.g. 1 vs 4 vs 8) does **not** double or alter the total work.
4. **Deterministic checksum**: Order-dependent reduction over chunk results in ascending order `0..chunks-1`. The final checksum is **strictly invariant** across worker counts:
   - Default params (`-c 4096 -i 100000`): Checksum is `0x3a762069507139ac`
   - Fast smoke test (`-c 1024 -i 50000`): Checksum is `0x23e23165be5ef4b6`
5. **No time-based stopping**: Runs until all chunks are finished.
6. **Compiler anti-elimination**: Includes compiler optimization barriers (`__asm__ __volatile__("" : "+r"(state))`) preventing Dead Code Elimination (DCE) or algebraic folding under `-O3`.

## Build Instructions

### Linux (Fedora demo laptop)
```bash
gcc -O3 -Wall -Wextra -pthread workloads/kernel/fixed_compute.c -o workloads/kernel/fixed_compute
```
Or use the Makefile / build script:
```bash
make -C workloads/kernel
# or
bash workloads/kernel/build.sh
```

## Exact Invocations for Agent A Calibration

### C1: Single-core Stock Calibration
Runs 1 worker pinned to a single core:
```bash
./workloads/kernel/fixed_compute -w 1 -c 4096 -i 200000 --json
```
(Or `--quiet` to output only the hex checksum `0x...`).

### C2: Multi-core Scaling Sweep
Runs $W$ workers (e.g., 4 workers for Ryzen AI 7 350 physical core layout):
```bash
./workloads/kernel/fixed_compute -w 4 -c 4096 -i 200000 --json
```

### CLI Reference
```text
Options:
  -w, --workers <N>   Number of worker threads (default: 4)
  -c, --chunks  <N>   Total number of chunks to divide (default: 4096)
  -i, --iters   <N>   Iterations per chunk (default: 100000)
  -s, --seed    <HEX> 64-bit base seed in hex (default: 0x517cc1b727220a95)
  -q, --quiet         Quiet mode: print only the checksum hex
  -j, --json          Output results as JSON
  -h, --help          Show help message
```
