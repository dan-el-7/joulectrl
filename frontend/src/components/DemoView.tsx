import React, { useState } from 'react';
import { launchDemoTerminal, measureCommand } from '../api';
import { fonts, radii } from '../design';
import { useTheme } from '../ThemeContext';

export const DemoView: React.FC = () => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const [preset, setPreset] = useState<'standard' | 'extended' | 'custom'>('standard');
  const [customCommand, setCustomCommand] = useState<string>("make -C workloads/build_target/zstd -j16");
  const [compareStock, setCompareStock] = useState<boolean>(true);
  const [workers, setWorkers] = useState<number>(16);

  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [terminalMsg, setTerminalMsg] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [runResult, setRunResult] = useState<any | null>(null);
  const [terminalLogs, setTerminalLogs] = useState<string[]>([
    '$ joulectrl ready. Genuine multi-threaded compilation benchmark initialized.',
    '$ Default target: Full Zstandard project build (50+ C source files, clean rebuild outside measurement window).',
  ]);

  const handleLaunchTerminal = async () => {
    setErrorMsg(null);
    setTerminalMsg(null);
    try {
      const res = await launchDemoTerminal({
        command: preset === 'custom' ? customCommand : undefined,
        mode: preset === 'custom' ? undefined : preset,
        compare: compareStock,
        workers,
      });
      setTerminalMsg(`Launched native terminal (${res.terminal}, PID: ${res.pid})`);
      setTerminalLogs((prev) => [
        ...prev,
        `------------------------------------------------------------`,
        `[Terminal] Spawning desktop terminal: ${res.terminal}`,
        `$ ${res.command}`,
        `[Terminal] Heavy compilation running in standalone terminal window.`,
      ]);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to spawn terminal');
    }
  };

  const handleRunInApp = async () => {
    setErrorMsg(null);
    setTerminalMsg(null);
    setIsRunning(true);
    const cmdDisplay =
      preset === 'standard'
        ? `make -C workloads/build_target/zstd -j${workers}`
        : preset === 'extended'
        ? `make -C workloads/build_target/zstd all test-programs -j${workers}`
        : customCommand;

    setTerminalLogs((prev) => [
      ...prev,
      `============================================================`,
      `[Run] Launching genuine compilation: ${cmdDisplay}`,
      `[Target] Clean tree rebuild across ${workers} worker threads`,
      `[Mode] ${compareStock ? 'Side-by-Side: Stock Boost vs Energy-Optimized' : 'Single Configuration'}`,
      `[Wait] Compiling full project and sampling hardware energy counters (10s–30s)...`,
    ]);

    try {
      const data = await measureCommand({
        command: preset === 'custom' ? customCommand : undefined,
        mode: preset === 'custom' ? undefined : preset,
        compare_stock: compareStock,
        workers,
      });
      setRunResult(data);

      if (data.comparison) {
        const comp = data.comparison;
        const savedPct = comp.energy_saved_pct !== null ? `${comp.energy_saved_pct > 0 ? '+' : ''}${comp.energy_saved_pct}%` : 'N/A';
        const pSavedPct = comp.power_saved_pct !== null ? `${comp.power_saved_pct > 0 ? '+' : ''}${comp.power_saved_pct}%` : 'N/A';
        setTerminalLogs((prev) => [
          ...prev,
          `[Done] Status: ${data.status.toUpperCase()}`,
          `  - Stock Runtime:     ${comp.runtime_stock_s?.toFixed(3)} s`,
          `  - Opt Runtime:       ${comp.runtime_opt_s?.toFixed(3)} s (${comp.runtime_delta_pct > 0 ? '+' : ''}${comp.runtime_delta_pct}%)`,
          `  - Stock Energy:      ${comp.energy_stock_j?.toFixed(2)} J`,
          `  - Opt Energy:        ${comp.energy_opt_j?.toFixed(2)} J (Saved: ${savedPct})`,
          `  - Stock Avg Power:   ${comp.avg_power_stock_w?.toFixed(2)} W`,
          `  - Opt Avg Power:     ${comp.avg_power_opt_w?.toFixed(2)} W (Power: ${pSavedPct})`,
          comp.energy_saved_pct && comp.energy_saved_pct > 0
            ? `[Result] SUCCESS: ${comp.energy_saved_pct}% energy reduction verified on hardware!`
            : `[Result] Benchmark completed.`,
        ]);
      } else if (data.run) {
        const r = data.run;
        setTerminalLogs((prev) => [
          ...prev,
          `[Done] Status: ${r.status.toUpperCase()} (Exit: ${r.exit_code})`,
          `  - Elapsed Time:   ${r.runtime_s?.toFixed(3)} s`,
          `  - Package Energy: ${r.package_energy_j?.toFixed(2)} J`,
          `  - Average Power:  ${r.avg_power_w?.toFixed(2)} W`,
        ]);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Execution failed');
      setTerminalLogs((prev) => [...prev, `[Error] ${err.message || 'Execution failed'}`]);
    } finally {
      setIsRunning(false);
    }
  };

  const c = {
    bg: isDark ? 'transparent' : '#f8fafc',
    cardBg: isDark ? '#141516' : '#ffffff',
    border: isDark ? 'rgba(255, 255, 255, 0.08)' : '#e2e8f0',
    primaryText: isDark ? '#f7f8f8' : '#0f172a',
    secondaryText: isDark ? '#8a8f98' : '#64748b',
    accent: '#6366f1',
    termBg: isDark ? '#0b0c0e' : '#1e1e24',
    termText: isDark ? '#a7f3d0' : '#86efac',
  };

  return (
    <div style={{ padding: '24px', maxWidth: '1280px', margin: '0 auto', fontFamily: fonts.sans }}>
      {/* Top Header */}
      <div style={{ marginBottom: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h1 style={{ fontSize: '24px', fontWeight: 600, color: c.primaryText, margin: 0 }}>
            Real-World GCC Compilation Demo & Power Benchmark
          </h1>
          <span
            style={{
              fontSize: '11px',
              fontWeight: 700,
              padding: '2px 8px',
              borderRadius: radii.full,
              backgroundColor: 'rgba(99, 102, 241, 0.15)',
              color: '#818cf8',
              border: '1px solid rgba(99, 102, 241, 0.3)',
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
            }}
          >
            10s+ Sustained Workload
          </span>
        </div>
        <p style={{ color: c.secondaryText, fontSize: '14px', marginTop: '6px' }}>
          Execute genuine multi-file C compilation workloads (50+ files) under hardware RAPL energy tracking and sustained package wattage ($P = E / T$).
        </p>
      </div>

      {/* Control Panel Grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(360px, 440px) 1fr',
          gap: '24px',
          alignItems: 'start',
        }}
      >
        {/* Left Column: Config & Launchers */}
        <div
          style={{
            backgroundColor: c.cardBg,
            border: `1px solid ${c.border}`,
            borderRadius: radii.lg,
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            gap: '18px',
          }}
        >
          <div>
            <label style={{ fontSize: '13px', fontWeight: 600, color: c.primaryText, display: 'block', marginBottom: '8px' }}>
              Target Compilation Workload
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setPreset('standard')}
                style={{
                  textAlign: 'left',
                  padding: '12px 14px',
                  borderRadius: radii.md,
                  border: `1px solid ${preset === 'standard' ? c.accent : c.border}`,
                  backgroundColor: preset === 'standard' ? 'rgba(99, 102, 241, 0.12)' : 'transparent',
                  color: c.primaryText,
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ fontWeight: 600, fontSize: '13px' }}>🚀 Full C Project Build (Zstandard)</div>
                  <span style={{ fontSize: '11px', color: '#10b981', fontWeight: 600 }}>~11s (600+ J)</span>
                </div>
                <div style={{ fontSize: '12px', color: c.secondaryText, marginTop: '3px', fontFamily: fonts.mono }}>
                  make -C workloads/build_target/zstd -j{workers}
                </div>
                <div style={{ fontSize: '11px', color: c.secondaryText, marginTop: '4px' }}>
                  Compiles 50+ source files, dynamic/static libraries & CLI executable from clean tree
                </div>
              </button>

              <button
                type="button"
                onClick={() => setPreset('extended')}
                style={{
                  textAlign: 'left',
                  padding: '12px 14px',
                  borderRadius: radii.md,
                  border: `1px solid ${preset === 'extended' ? c.accent : c.border}`,
                  backgroundColor: preset === 'extended' ? 'rgba(99, 102, 241, 0.12)' : 'transparent',
                  color: c.primaryText,
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={{ fontWeight: 600, fontSize: '13px' }}>⚡ Extended Multi-Target Suite</div>
                  <span style={{ fontSize: '11px', color: '#6366f1', fontWeight: 600 }}>~25s–35s</span>
                </div>
                <div style={{ fontSize: '12px', color: c.secondaryText, marginTop: '3px', fontFamily: fonts.mono }}>
                  make -C workloads/build_target/zstd all test-programs
                </div>
                <div style={{ fontSize: '11px', color: c.secondaryText, marginTop: '4px' }}>
                  Heavy sustained multi-threaded compilation of full library, CLI, and test harnesses
                </div>
              </button>

              <button
                type="button"
                onClick={() => setPreset('custom')}
                style={{
                  textAlign: 'left',
                  padding: '12px 14px',
                  borderRadius: radii.md,
                  border: `1px solid ${preset === 'custom' ? c.accent : c.border}`,
                  backgroundColor: preset === 'custom' ? 'rgba(99, 102, 241, 0.12)' : 'transparent',
                  color: c.primaryText,
                  cursor: 'pointer',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: '13px' }}>🛠️ Custom Command / App</div>
                <div style={{ fontSize: '12px', color: c.secondaryText, marginTop: '2px' }}>
                  Execute arbitrary compiler invocation, build script, or command
                </div>
              </button>
            </div>
          </div>

          {preset === 'custom' && (
            <div>
              <label style={{ fontSize: '13px', fontWeight: 600, color: c.primaryText, display: 'block', marginBottom: '6px' }}>
                Custom Command Line
              </label>
              <input
                type="text"
                value={customCommand}
                onChange={(e) => setCustomCommand(e.target.value)}
                placeholder="e.g. make -C my_repo -j16"
                style={{
                  width: '100%',
                  padding: '8px 10px',
                  fontFamily: fonts.mono,
                  fontSize: '12px',
                  borderRadius: radii.sm,
                  border: `1px solid ${c.border}`,
                  backgroundColor: isDark ? '#1a1b1e' : '#f1f5f9',
                  color: c.primaryText,
                  boxSizing: 'border-box',
                }}
              />
            </div>
          )}

          {/* Options */}
          <div style={{ borderTop: `1px solid ${c.border}`, paddingTop: '14px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer', fontSize: '13px', color: c.primaryText }}>
              <input
                type="checkbox"
                checked={compareStock}
                onChange={(e) => setCompareStock(e.target.checked)}
                style={{ accentColor: c.accent, cursor: 'pointer' }}
              />
              <span>Compare Stock Boost vs Energy-Optimized</span>
            </label>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '13px', color: c.primaryText }}>
              <span>Workers / Threads:</span>
              <select
                value={workers}
                onChange={(e) => setWorkers(parseInt(e.target.value, 10))}
                style={{
                  padding: '4px 8px',
                  borderRadius: radii.sm,
                  border: `1px solid ${c.border}`,
                  backgroundColor: isDark ? '#1a1b1e' : '#f1f5f9',
                  color: c.primaryText,
                }}
              >
                <option value={1}>1 worker</option>
                <option value={2}>2 workers</option>
                <option value={4}>4 workers</option>
                <option value={8}>8 workers</option>
                <option value={16}>16 workers (All cores)</option>
              </select>
            </div>
          </div>

          {/* Launch Buttons */}
          <div style={{ borderTop: `1px solid ${c.border}`, paddingTop: '14px', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button
              type="button"
              onClick={handleLaunchTerminal}
              disabled={isRunning}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '12px 16px',
                borderRadius: radii.md,
                backgroundColor: '#10b981',
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '14px',
                border: 'none',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                opacity: isRunning ? 0.6 : 1,
                boxShadow: '0 2px 6px rgba(16, 185, 129, 0.3)',
              }}
            >
              <span style={{ fontSize: '16px' }}>🖥️</span> Launch in OS Terminal
            </button>

            <button
              type="button"
              onClick={handleRunInApp}
              disabled={isRunning}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '8px',
                padding: '10px 16px',
                borderRadius: radii.md,
                backgroundColor: c.accent,
                color: '#ffffff',
                fontWeight: 600,
                fontSize: '14px',
                border: 'none',
                cursor: isRunning ? 'not-allowed' : 'pointer',
                opacity: isRunning ? 0.6 : 1,
              }}
            >
              <span>{isRunning ? '⏳ Running 10s+ Compilation Benchmark…' : '▶️ Run Benchmark in App'}</span>
            </button>
          </div>

          {terminalMsg && (
            <div style={{ padding: '8px 12px', borderRadius: radii.sm, backgroundColor: 'rgba(16, 185, 129, 0.15)', color: '#34d399', fontSize: '12px' }}>
              ✓ {terminalMsg}
            </div>
          )}

          {errorMsg && (
            <div style={{ padding: '8px 12px', borderRadius: radii.sm, backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#f87171', fontSize: '12px' }}>
              ✗ {errorMsg}
            </div>
          )}
        </div>

        {/* Right Column: Results & Terminal Output Window */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {/* Metrics summary cards if results exist */}
          {runResult?.comparison && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(3, 1fr)',
                gap: '12px',
              }}
            >
              <div style={{ backgroundColor: c.cardBg, border: `1px solid ${c.border}`, borderRadius: radii.lg, padding: '14px' }}>
                <div style={{ fontSize: '12px', color: c.secondaryText }}>Package Energy</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#10b981', margin: '4px 0' }}>
                  {runResult.comparison.energy_saved_pct !== null && runResult.comparison.energy_saved_pct > 0
                    ? `+${runResult.comparison.energy_saved_pct}% Saved`
                    : 'Measured'}
                </div>
                <div style={{ fontSize: '12px', color: c.secondaryText }}>
                  {runResult.comparison.energy_stock_j?.toFixed(1)} J → {runResult.comparison.energy_opt_j?.toFixed(1)} J
                </div>
              </div>

              <div style={{ backgroundColor: c.cardBg, border: `1px solid ${c.border}`, borderRadius: radii.lg, padding: '14px' }}>
                <div style={{ fontSize: '12px', color: c.secondaryText }}>Average Power</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: '#38bdf8', margin: '4px 0' }}>
                  {runResult.comparison.power_saved_pct !== null && runResult.comparison.power_saved_pct > 0
                    ? `${runResult.comparison.power_saved_pct}% Lower`
                    : 'Tracked'}
                </div>
                <div style={{ fontSize: '12px', color: c.secondaryText }}>
                  {runResult.comparison.avg_power_stock_w?.toFixed(1)} W → {runResult.comparison.avg_power_opt_w?.toFixed(1)} W
                </div>
              </div>

              <div style={{ backgroundColor: c.cardBg, border: `1px solid ${c.border}`, borderRadius: radii.lg, padding: '14px' }}>
                <div style={{ fontSize: '12px', color: c.secondaryText }}>Runtime Duration</div>
                <div style={{ fontSize: '20px', fontWeight: 700, color: c.primaryText, margin: '4px 0' }}>
                  {runResult.comparison.runtime_stock_s?.toFixed(1)}s vs {runResult.comparison.runtime_opt_s?.toFixed(1)}s
                </div>
                <div style={{ fontSize: '12px', color: c.secondaryText }}>
                  Trade-off: +{runResult.comparison.runtime_delta_pct?.toFixed(1)}% time for {runResult.comparison.energy_saved_pct?.toFixed(1)}% energy
                </div>
              </div>
            </div>
          )}

          {/* Terminal Console */}
          <div
            style={{
              backgroundColor: c.termBg,
              border: '1px solid rgba(255, 255, 255, 0.12)',
              borderRadius: radii.lg,
              overflow: 'hidden',
              boxShadow: '0 4px 16px rgba(0, 0, 0, 0.4)',
            }}
          >
            {/* Terminal Title Bar */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#ef4444', display: 'inline-block' }} />
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#f59e0b', display: 'inline-block' }} />
                <span style={{ width: '10px', height: '10px', borderRadius: '50%', backgroundColor: '#10b981', display: 'inline-block' }} />
                <span style={{ marginLeft: '10px', fontSize: '12px', color: '#94a3b8', fontFamily: fonts.mono }}>
                  terminal ~ joulectrl compiler benchmark
                </span>
              </div>
              <button
                type="button"
                onClick={() => setTerminalLogs(['$ terminal logs cleared.'])}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#64748b',
                  fontSize: '11px',
                  cursor: 'pointer',
                  fontFamily: fonts.mono,
                }}
              >
                Clear
              </button>
            </div>

            {/* Terminal Content Body */}
            <div
              style={{
                padding: '16px',
                minHeight: '340px',
                maxHeight: '480px',
                overflowY: 'auto',
                fontFamily: fonts.mono,
                fontSize: '12px',
                lineHeight: '1.6',
                color: c.termText,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {terminalLogs.map((log, idx) => (
                <div key={idx} style={{ marginBottom: '4px' }}>
                  {log}
                </div>
              ))}
              {isRunning && (
                <div style={{ color: '#fbbf24', marginTop: '6px' }}>
                  ⏳ Compiling full project across all threads (10s–30s) and reading hardware energy counters...
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
