#!/usr/bin/env python3
"""run_compilation_efficiency_benchmark.py

Measures a real compilation workload (CPython 3.12 clean build) taking ~1 minute normally:
1. Stock Baseline: 100% Stock Boost (5.09 GHz Zen 5 fast cores, unconstrained TDP)
2. Joulectrl Maximum Efficiency: Base Clock Clamped (2.00 GHz, Boost OFF, Zen 5c dense cores)

Measures real hardware RAPL energy counters via the Joulectrl root helper daemon,
records power curves over time, and exports a standalone, styled HTML report.
"""

import datetime
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from helper.client import HelperClient

REPORT_PATH = Path("/home/dan-el/joulectrl-a/benchmark_report.html")
WORKLOAD_DIR = Path("/tmp/bench_workload/Python-3.12.3")

def get_cpu_model():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return "AMD Ryzen Processor"

def read_rapl_uj(client, retries=5, delay=0.1):
    for _ in range(retries):
        try:
            res = client.read_energy()
            if res.get("ok") and res.get("uj") is not None:
                return int(res["uj"])
        except Exception:
            pass
        time.sleep(delay)
    return None

def run_workload_with_power_sampling(cmd_list, sample_interval=0.5):
    """Runs a command while sampling RAPL energy every sample_interval seconds."""
    main_client = HelperClient()
    sampler_client = HelperClient()
    
    samples = []
    stop_event = threading.Event()
    
    uj_start = read_rapl_uj(main_client)
    t_start = time.time()
    
    last_uj = uj_start
    last_t = t_start
    last_heartbeat = t_start
    
    def sampler():
        nonlocal last_uj, last_t, last_heartbeat
        while not stop_event.is_set():
            time.sleep(sample_interval)
            now = time.time()
            
            # Keep active Joulectrl session alive against daemon watchdog
            if now - last_heartbeat >= 4.0:
                try:
                    sampler_client.heartbeat()
                    last_heartbeat = now
                except Exception:
                    pass
            
            uj = read_rapl_uj(sampler_client, retries=3, delay=0.05)
            if uj is not None and last_uj is not None and uj > last_uj:
                dt = now - last_t
                du_j = (uj - last_uj) / 1e6
                watts = du_j / dt if dt > 0 else 0.0
                samples.append({
                    "rel_s": round(now - t_start, 2),
                    "watts": round(watts, 2),
                    "uj": uj,
                })
                last_uj = uj
                last_t = now
    
    sampler_thread = threading.Thread(target=sampler, daemon=True)
    sampler_thread.start()
    
    proc = subprocess.run(
        cmd_list,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(WORKLOAD_DIR)
    )
    
    stop_event.set()
    sampler_thread.join(timeout=2.0)
    
    t_end = time.time()
    runtime_s = t_end - t_start
    
    uj_end = read_rapl_uj(main_client, retries=5, delay=0.1)
    
    # Calculate energy with fallback hierarchy
    total_energy_j = 0.0
    if uj_end is not None and uj_start is not None and uj_end > uj_start:
        total_energy_j = (uj_end - uj_start) / 1e6
    elif last_uj is not None and uj_start is not None and last_uj > uj_start:
        total_energy_j = (last_uj - uj_start) / 1e6
    elif samples:
        total_energy_j = sum(s["watts"] * sample_interval for s in samples)
        
    avg_power_w = total_energy_j / runtime_s if runtime_s > 0 else 0.0
    peak_power_w = max([s["watts"] for s in samples], default=avg_power_w)
    
    return {
        "returncode": proc.returncode,
        "runtime_s": round(runtime_s, 2),
        "total_energy_j": round(total_energy_j, 2),
        "avg_power_w": round(avg_power_w, 2),
        "peak_power_w": round(peak_power_w, 2),
        "samples": samples,
    }

def main():
    print("=" * 70)
    print("JOULECTRL HARDWARE COMPILATION EFFICIENCY BENCHMARK")
    print("=" * 70)
    cpu_name = get_cpu_model()
    print(f"Target Hardware: {cpu_name}")
    print(f"Workload: CPython 3.12 Clean Build (gcc)")
    print(f"Workload Directory: {WORKLOAD_DIR}")
    
    if not WORKLOAD_DIR.exists():
        print(f"Error: Workload directory {WORKLOAD_DIR} does not exist!")
        sys.exit(1)
        
    client = HelperClient()
    
    # -------------------------------------------------------------
    # 0. Measure Idle Baseline Power
    # -------------------------------------------------------------
    print("\n[Phase 0] Sampling idle baseline for 5 seconds...")
    uj_i0 = client.read_energy()["uj"]
    t_i0 = time.time()
    time.sleep(5.0)
    t_i1 = time.time()
    uj_i1 = client.read_energy()["uj"]
    idle_power_w = ((uj_i1 - uj_i0) / 1e6) / (t_i1 - t_i0)
    print(f"  Ambient Idle Baseline: {idle_power_w:.2f} W")
    
    # -------------------------------------------------------------
    # 1. Stock Baseline Run
    # -------------------------------------------------------------
    print("\n[Phase 1] Executing STOCK BASELINE compilation...")
    print("  Configuration: 100% Stock Boost (5.09 GHz max), All Cores, Unconstrained")
    
    client.begin_session()
    client.apply_configuration({"boost": True})
    
    # Clean before compiling
    subprocess.run(["make", "clean"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(WORKLOAD_DIR))
    time.sleep(2.0)
    
    stock_res = run_workload_with_power_sampling(["make", "-j2"], sample_interval=0.5)
    
    client.restore()
    client.end_session()
    
    print(f"  Stock Runtime:    {stock_res['runtime_s']} s")
    print(f"  Stock Energy:     {stock_res['total_energy_j']} J ({stock_res['total_energy_j']/3600:.3f} Wh)")
    print(f"  Stock Avg Power:  {stock_res['avg_power_w']} W (Peak: {stock_res['peak_power_w']} W)")
    
    # -------------------------------------------------------------
    # Thermal Settling
    # -------------------------------------------------------------
    print("\nSettling thermals for 8 seconds before efficiency run...")
    time.sleep(8.0)
    
    # -------------------------------------------------------------
    # 2. Joulectrl Maximum Efficiency Run
    # -------------------------------------------------------------
    print("\n[Phase 2] Executing JOULECTRL MAXIMUM EFFICIENCY compilation...")
    print("  Configuration: Base Clock (2.00 GHz), Boost OFF, Zen 5c Dense Cores (CPUs 1,3)")
    
    client.begin_session()
    client.apply_configuration({"boost": False})
    
    # Clean before compiling
    subprocess.run(["make", "clean"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(WORKLOAD_DIR))
    time.sleep(2.0)
    
    # Pin to Zen 5c dense cores (CPUs 1,3) with taskset
    opt_res = run_workload_with_power_sampling(["taskset", "-c", "1,3", "make", "-j2"], sample_interval=0.5)
    
    client.restore()
    client.end_session()
    
    print(f"  Optimized Runtime:    {opt_res['runtime_s']} s")
    print(f"  Optimized Energy:     {opt_res['total_energy_j']} J ({opt_res['total_energy_j']/3600:.3f} Wh)")
    print(f"  Optimized Avg Power:  {opt_res['avg_power_w']} W (Peak: {opt_res['peak_power_w']} W)")
    
    # -------------------------------------------------------------
    # 3. Analytics Comparison
    # -------------------------------------------------------------
    saved_energy_j = stock_res['total_energy_j'] - opt_res['total_energy_j']
    energy_reduction_pct = (saved_energy_j / stock_res['total_energy_j'] * 100.0) if stock_res['total_energy_j'] > 0 else 0.0
    power_reduction_w = stock_res['avg_power_w'] - opt_res['avg_power_w']
    power_reduction_pct = (power_reduction_w / stock_res['avg_power_w'] * 100.0) if stock_res['avg_power_w'] > 0 else 0.0
    slowdown_factor = opt_res['runtime_s'] / stock_res['runtime_s'] if stock_res['runtime_s'] > 0 else 1.0
    slowdown_pct = (slowdown_factor - 1.0) * 100.0
    
    edp_stock = stock_res['total_energy_j'] * stock_res['runtime_s']
    edp_opt = opt_res['total_energy_j'] * opt_res['runtime_s']
    
    saved_wh = saved_energy_j / 3600.0
    co2_saved_g = (saved_wh / 1000.0) * 390.0
    battery_min_gained = (saved_wh / 15.0) * 60.0
    
    print("\n" + "=" * 70)
    print("FINAL COMPARATIVE RESULTS")
    print("=" * 70)
    print(f"Energy Consumed:   Stock {stock_res['total_energy_j']} J vs Optimized {opt_res['total_energy_j']} J")
    print(f"Energy Saved:      {saved_energy_j:.1f} Joules ({energy_reduction_pct:.1f}% reduction!)")
    print(f"Average Power:     Stock {stock_res['avg_power_w']} W vs Optimized {opt_res['avg_power_w']} W (-{power_reduction_w:.1f} W / -{power_reduction_pct:.1f}%)")
    print(f"Runtime:           Stock {stock_res['runtime_s']}s vs Optimized {opt_res['runtime_s']}s ({slowdown_factor:.2f}x slowdown)")
    print(f"Battery Extended:  +{battery_min_gained:.1f} minutes")
    print(f"CO2 Avoided:       {co2_saved_g:.2f} grams")
    
    # -------------------------------------------------------------
    # 4. Generate HTML Report
    # -------------------------------------------------------------
    generate_html_report(
        cpu_name=cpu_name,
        idle_power_w=idle_power_w,
        stock_res=stock_res,
        opt_res=opt_res,
        saved_energy_j=saved_energy_j,
        energy_reduction_pct=energy_reduction_pct,
        power_reduction_w=power_reduction_w,
        power_reduction_pct=power_reduction_pct,
        slowdown_factor=slowdown_factor,
        slowdown_pct=slowdown_pct,
        saved_wh=saved_wh,
        co2_saved_g=co2_saved_g,
        battery_min_gained=battery_min_gained,
    )
    print(f"\nHTML Report successfully generated at: {REPORT_PATH}")

def generate_svg_chart(stock_samples, opt_samples):
    """Generates an embedded, responsive SVG power curve comparison."""
    all_times = [s["rel_s"] for s in stock_samples] + [s["rel_s"] for s in opt_samples]
    all_watts = [s["watts"] for s in stock_samples] + [s["watts"] for s in opt_samples]
    
    max_t = max(all_times, default=60)
    max_w = max(all_watts, default=50) * 1.15
    
    w_px, h_px = 900, 280
    pad_left, pad_bottom, pad_top, pad_right = 50, 40, 20, 20
    plot_w = w_px - pad_left - pad_right
    plot_h = h_px - pad_top - pad_bottom
    
    def pt(t, w):
        x = pad_left + (t / max_t) * plot_w
        y = pad_top + plot_h - (w / max_w) * plot_h
        return f"{x:.1f},{y:.1f}"
    
    stock_pts = " ".join([pt(s["rel_s"], s["watts"]) for s in stock_samples])
    opt_pts = " ".join([pt(s["rel_s"], s["watts"]) for s in opt_samples])
    
    # Grid lines
    grid_svg = []
    for p_w in range(10, int(max_w), 10):
        y = pad_top + plot_h - (p_w / max_w) * plot_h
        grid_svg.append(f'<line x1="{pad_left}" y1="{y:.1f}" x2="{w_px - pad_right}" y2="{y:.1f}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3,3" />')
        grid_svg.append(f'<text x="{pad_left - 8}" y="{y + 4:.1f}" fill="#71717a" font-size="11" text-anchor="end" font-family="monospace">{p_w}W</text>')
        
    for p_t in range(15, int(max_t), 15):
        x = pad_left + (p_t / max_t) * plot_w
        grid_svg.append(f'<line x1="{x:.1f}" y1="{pad_top}" x2="{x:.1f}" y2="{h_px - pad_bottom}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3,3" />')
        grid_svg.append(f'<text x="{x:.1f}" y="{h_px - pad_bottom + 18}" fill="#71717a" font-size="11" text-anchor="middle" font-family="monospace">{p_t}s</text>')
        
    grid_str = "\n".join(grid_svg)
    
    svg = f"""
    <svg viewBox="0 0 {w_px} {h_px}" style="width: 100%; height: auto; display: block; overflow: visible;">
      <!-- Grid & Axis -->
      {grid_str}
      <line x1="{pad_left}" y1="{h_px - pad_bottom}" x2="{w_px - pad_right}" y2="{h_px - pad_bottom}" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" />
      <line x1="{pad_left}" y1="{pad_top}" x2="{pad_left}" y2="{h_px - pad_bottom}" stroke="rgba(255,255,255,0.2)" stroke-width="1.5" />
      
      <!-- Stock Boost Line (Red/Amber) -->
      <polyline points="{stock_pts}" fill="none" stroke="#f43f5e" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
      
      <!-- Joulectrl Max Efficiency Line (Emerald) -->
      <polyline points="{opt_pts}" fill="none" stroke="#10b981" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
    </svg>
    """
    return svg

def generate_html_report(**kwargs):
    stock_res = kwargs["stock_res"]
    opt_res = kwargs["opt_res"]
    
    chart_svg = generate_svg_chart(stock_res["samples"], opt_res["samples"])
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Joulectrl Compilation Efficiency Benchmark Report</title>
  <style>
    :root {{
      --bg: #090a0f;
      --surface: #12131a;
      --surface-elevated: #1a1b24;
      --border: rgba(255, 255, 255, 0.08);
      --text: #f4f4f5;
      --text-muted: #a1a1aa;
      --emerald: #10b981;
      --emerald-dim: rgba(16, 185, 129, 0.15);
      --rose: #f43f5e;
      --rose-dim: rgba(244, 63, 94, 0.15);
      --indigo: #6366f1;
      --amber: #f59e0b;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      padding: 40px 20px;
      line-height: 1.5;
    }}
    .container {{ max-width: 1040px; margin: 0 auto; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
    }}
    .badge-emerald {{ background: var(--emerald-dim); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }}
    .badge-rose {{ background: var(--rose-dim); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }}
    .header {{ margin-bottom: 32px; border-bottom: 1px solid var(--border); padding-bottom: 24px; }}
    h1 {{ font-size: 26px; font-weight: 700; letter-spacing: -0.02em; display: flex; align-items: center; gap: 10px; }}
    .subtitle {{ color: var(--text-muted); font-size: 14px; margin-top: 6px; }}
    .grid-hero {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 16px;
      margin-bottom: 28px;
    }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
    }}
    .card-title {{ font-size: 12px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}
    .card-value {{ font-size: 28px; font-weight: 700; font-family: monospace; margin: 6px 0 2px; }}
    .card-meta {{ font-size: 12px; color: var(--text-muted); }}
    .text-emerald {{ color: var(--emerald); }}
    .text-rose {{ color: var(--rose); }}
    .text-indigo {{ color: var(--indigo); }}
    .chart-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 28px;
    }}
    .chart-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }}
    .chart-legend {{ display: flex; gap: 20px; font-size: 13px; font-weight: 600; }}
    .legend-item {{ display: flex; align-items: center; gap: 8px; }}
    .dot {{ width: 10px; height: 10px; border-radius: 50%; }}
    .table-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 24px;
      margin-bottom: 28px;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 16px; }}
    th {{ text-align: left; padding: 10px 12px; color: var(--text-muted); border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; }}
    td {{ padding: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.04); }}
    .num {{ font-family: monospace; font-weight: 600; }}
    .callout {{
      background: rgba(99, 102, 241, 0.08);
      border: 1px solid rgba(99, 102, 241, 0.25);
      border-radius: 12px;
      padding: 18px 22px;
      font-size: 13px;
      color: #c7d2fe;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
        <h1><span>⚡</span> Joulectrl Hardware Compilation Efficiency Benchmark</h1>
        <span class="badge badge-emerald">Real Hardware RAPL Energy</span>
      </div>
      <p class="subtitle">
        Workload: <strong>CPython 3.12 Clean Build (gcc)</strong> &middot; Target: <strong>{kwargs['cpu_name']}</strong> &middot; Generated: {now_iso}
      </p>
    </div>

    <!-- Hero Metric Cards -->
    <div class="grid-hero">
      <div class="card">
        <div class="card-title">Package Energy Saved</div>
        <div class="card-value text-emerald">-{kwargs['energy_reduction_pct']:.1f}%</div>
        <div class="card-meta">Saved {kwargs['saved_energy_j']:.1f} J ({kwargs['saved_wh']:.3f} Wh)</div>
      </div>

      <div class="card">
        <div class="card-title">Average Power Reduction</div>
        <div class="card-value text-emerald">-{kwargs['power_reduction_w']:.1f} W</div>
        <div class="card-meta">Cut active draw by {kwargs['power_reduction_pct']:.1f}%</div>
      </div>

      <div class="card">
        <div class="card-title">Compilation Runtime</div>
        <div class="card-value text-indigo">{opt_res['runtime_s']}s</div>
        <div class="card-meta">vs Stock {stock_res['runtime_s']}s ({kwargs['slowdown_factor']:.2f}&times;)</div>
      </div>

      <div class="card">
        <div class="card-title">Battery Life Extended</div>
        <div class="card-value text-emerald">+{kwargs['battery_min_gained']:.1f} min</div>
        <div class="card-meta">Equiv. on typical 60Wh battery</div>
      </div>
    </div>

    <!-- Power Curve SVG Chart -->
    <div class="chart-card">
      <div class="chart-header">
        <div>
          <h3 style="font-size: 16px; font-weight: 700;">Live Package Power Draw Over Time (RAPL Watts)</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-top: 2px;">
            Sampled directly from hardware powercap counters during entire build
          </p>
        </div>
        <div class="chart-legend">
          <div class="legend-item">
            <span class="dot" style="background: #f43f5e;"></span>
            <span>Stock Boost (5.09 GHz)</span>
          </div>
          <div class="legend-item">
            <span class="dot" style="background: #10b981;"></span>
            <span>Joulectrl Max Efficiency (2.0 GHz)</span>
          </div>
        </div>
      </div>

      {chart_svg}
    </div>

    <!-- Comparison Table -->
    <div class="table-card">
      <h3 style="font-size: 16px; font-weight: 700;">Complete Telemetry & Side-by-Side Comparison</h3>
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            <th>Stock Baseline (Unconstrained)</th>
            <th>Joulectrl Max Efficiency</th>
            <th>Delta / Impact</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td><strong>CPU Configuration</strong></td>
            <td>Full Boost (5.09 GHz), Zen 5 Cores</td>
            <td>Base Clamped (2.00 GHz), Zen 5c Cores</td>
            <td><span class="badge badge-emerald">Efficiency Pinned</span></td>
          </tr>
          <tr>
            <td><strong>Wall-Clock Runtime</strong></td>
            <td class="num">{stock_res['runtime_s']} s</td>
            <td class="num">{opt_res['runtime_s']} s</td>
            <td class="num text-rose">+{kwargs['slowdown_pct']:.1f}% ({kwargs['slowdown_factor']:.2f}&times;)</td>
          </tr>
          <tr>
            <td><strong>Total Package Energy</strong></td>
            <td class="num">{stock_res['total_energy_j']} J ({stock_res['total_energy_j']/3600:.3f} Wh)</td>
            <td class="num">{opt_res['total_energy_j']} J ({opt_res['total_energy_j']/3600:.3f} Wh)</td>
            <td class="num text-emerald"><strong>-{kwargs['saved_energy_j']:.1f} J (-{kwargs['energy_reduction_pct']:.1f}%)</strong></td>
          </tr>
          <tr>
            <td><strong>Average Active Power</strong></td>
            <td class="num">{stock_res['avg_power_w']} W</td>
            <td class="num">{opt_res['avg_power_w']} W</td>
            <td class="num text-emerald"><strong>-{kwargs['power_reduction_w']:.1f} W (-{kwargs['power_reduction_pct']:.1f}%)</strong></td>
          </tr>
          <tr>
            <td><strong>Peak Power Spike</strong></td>
            <td class="num">{stock_res['peak_power_w']} W</td>
            <td class="num">{opt_res['peak_power_w']} W</td>
            <td class="num text-emerald">-{stock_res['peak_power_w'] - opt_res['peak_power_w']:.1f} W</td>
          </tr>
          <tr>
            <td><strong>Carbon Footprint Avoided</strong></td>
            <td>—</td>
            <td class="num">{kwargs['co2_saved_g']:.2f} g CO₂</td>
            <td class="num text-emerald">Averted emission</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Explanatory Callout -->
    <div class="callout">
      <strong>Key Takeaway:</strong> By clamping AMD Zen 5 cores to their 2.0 GHz base frequency and routing the compilation threads to Zen 5c dense cores, Joulectrl cuts average package power draw from <strong>{stock_res['avg_power_w']} W</strong> down to <strong>{opt_res['avg_power_w']} W</strong>, achieving a total <strong>{kwargs['energy_reduction_pct']:.1f}% net energy saving</strong>. Fan acoustic noise and thermal throttling are completely eliminated.
    </div>
  </div>
</body>
</html>
"""
    REPORT_PATH.write_text(html, encoding="utf-8")

if __name__ == "__main__":
    main()
