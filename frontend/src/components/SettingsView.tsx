import React, { useState, useEffect } from 'react';
import { useTheme } from '../ThemeContext';
import { getThemeColors, fonts, radii } from '../design';
import { fetchOllamaModels, testOllamaModel, OllamaModelInfo } from '../api';

interface SettingsViewProps {
  expPassiveCaps: boolean;
  onChangeExpPassiveCaps: (val: boolean) => void;
  repetitions: number;
  onChangeRepetitions: (val: number) => void;
  calibrationBudgetS: number | null;
  onChangeCalibrationBudget: (val: number | null) => void;
}

export const SettingsView: React.FC<SettingsViewProps> = ({
  expPassiveCaps,
  onChangeExpPassiveCaps,
  repetitions,
  onChangeRepetitions,
  calibrationBudgetS,
  onChangeCalibrationBudget,
}) => {
  const { theme } = useTheme();
  const c = getThemeColors(theme);
  const isLight = theme === 'light';

  // Ollama & LLM settings
  const [ollamaUrl, setOllamaUrl] = useState<string>(() => {
    return localStorage.getItem('joulectrl_ollama_url') || 'http://localhost:11434';
  });
  const [selectedModel, setSelectedModel] = useState<string>(() => {
    return localStorage.getItem('joulectrl_ollama_model') || 'llama3.2';
  });
  const [defaultProvider, setDefaultProvider] = useState<string>(() => {
    return localStorage.getItem('joulectrl_llm_provider') || 'ollama';
  });

  const [models, setModels] = useState<OllamaModelInfo[]>([]);
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [isConnected, setIsConnected] = useState<boolean | null>(null);
  const [scanMessage, setScanMessage] = useState<string>('');
  const [testResult, setTestResult] = useState<{ ok: boolean; latency_ms?: number; response?: string; error?: string } | null>(null);
  const [isTesting, setIsTesting] = useState<boolean>(false);

  // Scan Ollama models
  const handleScanModels = async (targetUrl?: string) => {
    const urlToScan = targetUrl || ollamaUrl;
    setIsScanning(true);
    setTestResult(null);
    try {
      const res = await fetchOllamaModels(urlToScan);
      setIsConnected(res.connected);
      setModels(res.models || []);
      setScanMessage(res.message);
      if (res.models && res.models.length > 0) {
        // If current selectedModel is not in list, auto-select first
        if (!res.models.some((m) => m.name === selectedModel)) {
          setSelectedModel(res.models[0].name);
          localStorage.setItem('joulectrl_ollama_model', res.models[0].name);
        }
      }
    } catch (e: any) {
      setIsConnected(false);
      setModels([]);
      setScanMessage(`Failed to reach Ollama at ${urlToScan}: ${e?.message || e}`);
    } finally {
      setIsScanning(false);
    }
  };

  // Auto-scan on mount
  useEffect(() => {
    handleScanModels();
  }, []);

  const handleUrlChange = (val: string) => {
    setOllamaUrl(val);
    localStorage.setItem('joulectrl_ollama_url', val);
  };

  const handleModelChange = (val: string) => {
    setSelectedModel(val);
    localStorage.setItem('joulectrl_ollama_model', val);
  };

  const handleProviderChange = (val: string) => {
    setDefaultProvider(val);
    localStorage.setItem('joulectrl_llm_provider', val);
  };

  const handleTestConnection = async () => {
    if (!selectedModel) return;
    setIsTesting(true);
    try {
      const res = await testOllamaModel(ollamaUrl, selectedModel);
      setTestResult(res);
    } catch (e: any) {
      setTestResult({ ok: false, error: e?.message || String(e) });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div style={{ maxWidth: '960px', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
      {/* Header */}
      <div
        style={{
          background: c.surface,
          borderRadius: radii.lg,
          padding: '1.25rem 1.5rem',
          border: `1px solid ${c.border}`,
          boxShadow: c.cardShadow,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: '1.2rem', color: c.textPrimary, fontWeight: 600 }}>
            Settings & Local Inference
          </h2>
          <div style={{ fontSize: '0.8rem', color: c.textTertiary, marginTop: '0.2rem' }}>
            Configure local AI models (Ollama), hardware diagnostics, and engine defaults.
          </div>
        </div>
      </div>

      {/* Section 1: Local LLM & Ollama Configuration */}
      <div
        style={{
          background: c.surface,
          borderRadius: radii.lg,
          padding: '1.5rem',
          border: `1px solid ${c.border}`,
          boxShadow: c.cardShadow,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1rem', color: c.textPrimary, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span>🦙</span> Local LLM Inference (Ollama)
            </h3>
            <div style={{ fontSize: '0.78rem', color: c.textTertiary, marginTop: '0.2rem' }}>
              Generate grounded, plain-language explanations of silicon optimization tradeoffs using your local AI models.
            </div>
          </div>

          <span
            style={{
              padding: '3px 10px',
              borderRadius: radii.full,
              fontSize: '0.75rem',
              fontWeight: 600,
              fontFamily: fonts.mono,
              background: isConnected
                ? isLight ? 'rgba(22,163,74,0.1)' : 'rgba(16,185,129,0.15)'
                : isLight ? 'rgba(245,158,11,0.1)' : 'rgba(245,158,11,0.15)',
              color: isConnected ? c.emerald : c.amber,
              border: `1px solid ${isConnected ? (isLight ? '#bbf7d0' : c.emerald) : (isLight ? '#fde68a' : c.amber)}`,
            }}
          >
            {isConnected === null ? 'Scanning...' : isConnected ? '✓ Ollama Online' : '⚠️ Offline / Unreachable'}
          </span>
        </div>

        {/* Ollama Endpoint Input + Scan Button */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '0.75rem', marginBottom: '1.25rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: c.textSecondary, marginBottom: '0.35rem' }}>
              Ollama Service URL
            </label>
            <input
              type="text"
              value={ollamaUrl}
              onChange={(e) => handleUrlChange(e.target.value)}
              placeholder="http://localhost:11434"
              style={{
                width: '100%',
                padding: '0.55rem 0.85rem',
                borderRadius: radii.md,
                border: `1px solid ${c.border}`,
                background: c.surfaceElevated,
                color: c.textPrimary,
                fontSize: '0.85rem',
                fontFamily: fonts.mono,
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-end' }}>
            <button
              type="button"
              onClick={() => handleScanModels()}
              disabled={isScanning}
              style={{
                padding: '0.55rem 1.25rem',
                borderRadius: radii.md,
                border: 'none',
                backgroundColor: c.accentBg,
                color: '#ffffff',
                fontSize: '0.82rem',
                fontWeight: 600,
                cursor: isScanning ? 'wait' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                boxShadow: isLight ? '0 1px 2px rgba(99,102,241,0.2)' : 'none',
              }}
            >
              {isScanning ? 'Scanning Models…' : '🔄 Scan Installed Models'}
            </button>
          </div>
        </div>

        {/* Models list / selection */}
        <div style={{ marginBottom: '1.25rem' }}>
          <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: c.textSecondary, marginBottom: '0.35rem' }}>
            Active Explanation Model
          </label>
          {models.length > 0 ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.5rem' }}>
              {models.map((m) => {
                const isSel = selectedModel === m.name;
                return (
                  <button
                    key={m.name}
                    type="button"
                    onClick={() => handleModelChange(m.name)}
                    style={{
                      padding: '0.65rem 0.85rem',
                      borderRadius: radii.md,
                      border: `1.5px solid ${isSel ? c.accent : c.border}`,
                      background: isSel ? (isLight ? 'rgba(99,102,241,0.1)' : 'rgba(113,112,255,0.18)') : c.surfaceElevated,
                      textAlign: 'left',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontSize: '0.85rem', fontWeight: 600, color: isSel ? c.accent : c.textPrimary, fontFamily: fonts.mono }}>
                        {m.name}
                      </span>
                      {m.size_mb && (
                        <span style={{ fontSize: '0.7rem', color: c.textTertiary }}>
                          {(m.size_mb / 1024).toFixed(1)} GB
                        </span>
                      )}
                    </div>
                    {(m.parameter_size || m.family) && (
                      <div style={{ fontSize: '0.7rem', color: c.textTertiary, marginTop: 4 }}>
                        {m.family || 'model'} {m.parameter_size ? `· ${m.parameter_size}` : ''} {m.quantization_level ? `· ${m.quantization_level}` : ''}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          ) : (
            <div
              style={{
                padding: '0.85rem 1rem',
                borderRadius: radii.md,
                background: c.surfaceElevated,
                border: `1px solid ${c.border}`,
                fontSize: '0.8rem',
                color: c.textTertiary,
              }}
            >
              {scanMessage || 'No local models found yet. Start Ollama with `ollama serve` and run `ollama pull llama3.2` or `mistral`.'}
            </div>
          )}
        </div>

        {/* Custom model input if needed */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem' }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: 'block', fontSize: '0.74rem', color: c.textTertiary, marginBottom: '0.2rem' }}>
              Or type any custom Ollama model tag:
            </label>
            <input
              type="text"
              value={selectedModel}
              onChange={(e) => handleModelChange(e.target.value)}
              placeholder="e.g. llama3.2:latest, mistral:7b, qwen2.5:3b"
              style={{
                width: '100%',
                padding: '0.45rem 0.75rem',
                borderRadius: radii.sm,
                border: `1px solid ${c.border}`,
                background: c.surfaceElevated,
                color: c.textPrimary,
                fontSize: '0.82rem',
                fontFamily: fonts.mono,
                outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <button
            type="button"
            onClick={handleTestConnection}
            disabled={isTesting || !selectedModel}
            style={{
              marginTop: '1.1rem',
              padding: '0.45rem 0.95rem',
              borderRadius: radii.sm,
              border: `1px solid ${c.border}`,
              background: c.surfaceElevated,
              color: c.textPrimary,
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: isTesting ? 'wait' : 'pointer',
              whiteSpace: 'nowrap',
            }}
          >
            {isTesting ? 'Testing…' : '⚡ Test Model Connection'}
          </button>
        </div>

        {/* Test Connection Output */}
        {testResult && (
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: radii.md,
              background: testResult.ok
                ? (isLight ? 'rgba(22,163,74,0.08)' : 'rgba(16,185,129,0.12)')
                : (isLight ? 'rgba(239,68,68,0.08)' : 'rgba(244,88,110,0.12)'),
              border: `1px solid ${testResult.ok ? c.emerald : c.red}`,
              fontSize: '0.82rem',
              color: c.textPrimary,
              marginBottom: '1rem',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
              <span>{testResult.ok ? '✓ Model Responded Successfully' : '⚠️ Connection Failed'}</span>
              {testResult.latency_ms && (
                <span style={{ fontFamily: fonts.mono, color: c.textTertiary }}>
                  {testResult.latency_ms} ms
                </span>
              )}
            </div>
            <div style={{ marginTop: '0.35rem', color: c.textSecondary, fontSize: '0.8rem' }}>
              {testResult.ok ? testResult.response : testResult.error}
            </div>
          </div>
        )}

        {/* Default Provider Mode Selector */}
        <div>
          <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 600, color: c.textSecondary, marginBottom: '0.35rem' }}>
            Default Explanation Mode
          </label>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {[
              { id: 'ollama', label: '🦙 Ollama (Local LLM)', desc: 'Natural plain language from local model' },
              { id: 'template', label: '🛡️ Deterministic Template (Offline)', desc: 'Guaranteed rule-based summary (0 latency)' },
            ].map((p) => {
              const isSel = defaultProvider === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => handleProviderChange(p.id)}
                  style={{
                    flex: 1,
                    padding: '0.6rem 0.85rem',
                    borderRadius: radii.md,
                    border: `1.5px solid ${isSel ? c.accent : c.border}`,
                    background: isSel ? (isLight ? 'rgba(99,102,241,0.1)' : 'rgba(113,112,255,0.18)') : c.surfaceElevated,
                    color: isSel ? c.textPrimary : c.textSecondary,
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: isSel ? c.accent : c.textPrimary }}>
                    {p.label}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: c.textTertiary, marginTop: 2 }}>
                    {p.desc}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Section 2: Infrequent & Advanced Engine Settings */}
      <div
        style={{
          background: c.surface,
          borderRadius: radii.lg,
          padding: '1.5rem',
          border: `1px solid ${c.border}`,
          boxShadow: c.cardShadow,
        }}
      >
        <h3 style={{ margin: '0 0 0.4rem 0', fontSize: '1rem', color: c.textPrimary, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>⚙️</span> Advanced Hardware & Profiling Defaults
        </h3>
        <div style={{ fontSize: '0.78rem', color: c.textTertiary, marginBottom: '1.25rem' }}>
          Settings you wouldn't normally adjust every run.
        </div>

        {/* Experimental Passive Mode P-State Caps */}
        <div
          style={{
            padding: '0.85rem 1rem',
            borderRadius: radii.md,
            background: c.surfaceElevated,
            border: `1px solid ${c.border}`,
            marginBottom: '1rem',
          }}
        >
          <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={expPassiveCaps}
              onChange={(e) => onChangeExpPassiveCaps(e.target.checked)}
              style={{ marginTop: 3, accentColor: c.amber }}
            />
            <div>
              <div style={{ fontSize: '0.85rem', fontWeight: 600, color: c.textPrimary }}>
                <span style={{ color: c.amber, fontWeight: 700 }}>Experimental:</span> Passive P-State Mode Frequency Caps
              </div>
              <div style={{ fontSize: '0.75rem', color: c.textTertiary, marginTop: '0.2rem', lineHeight: 1.4 }}>
                Tests frequency caps under `amd_pstate=passive` with boost active (2.5–4.5 GHz).
                Measured baseline analysis showed negligible energy improvement over stock autonomous P-states on Zen 5 laptops. Leave off for standard runs.
              </div>
            </div>
          </label>
        </div>

        {/* Default Scan Time / Calibration Preset */}
        <div
          style={{
            padding: '0.85rem 1rem',
            borderRadius: radii.md,
            background: c.surfaceElevated,
            border: `1px solid ${c.border}`,
            marginBottom: '1rem',
          }}
        >
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: c.textPrimary, marginBottom: '0.3rem' }}>
            Default Calibration Scan Budget
          </div>
          <div style={{ fontSize: '0.75rem', color: c.textTertiary, marginBottom: '0.75rem' }}>
            Controls default scan duration before profiling a new workload.
          </div>
          <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
            {[
              { val: 0, label: '0s (Instant · use saved)' },
              { val: 60, label: '60s' },
              { val: 120, label: '120s (Recommended)' },
              { val: 300, label: '5 min (300s)' },
              { val: null, label: 'Exhaustive (All speeds)' },
            ].map((opt) => {
              const isSel = calibrationBudgetS === opt.val;
              return (
                <button
                  key={String(opt.val)}
                  type="button"
                  onClick={() => onChangeCalibrationBudget(opt.val)}
                  style={{
                    padding: '0.4rem 0.75rem',
                    borderRadius: radii.sm,
                    border: `1.5px solid ${isSel ? c.accent : c.border}`,
                    background: isSel ? (isLight ? '#e0e7ff' : 'rgba(113,112,255,0.22)') : c.surface,
                    color: isSel ? c.accent : c.textSecondary,
                    fontSize: '0.76rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Default Repetition Accuracy */}
        <div
          style={{
            padding: '0.85rem 1rem',
            borderRadius: radii.md,
            background: c.surfaceElevated,
            border: `1px solid ${c.border}`,
          }}
        >
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: c.textPrimary, marginBottom: '0.3rem' }}>
            Measurement Consistency Verification
          </div>
          <div style={{ fontSize: '0.75rem', color: c.textTertiary, marginBottom: '0.75rem' }}>
            Default number of test repetitions per CPU frequency setting.
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {[
              { val: 1, label: '1 run (Fast sweep)', desc: 'Standard single measurement per frequency' },
              { val: 2, label: '2 runs (Double-check)', desc: 'Verifies repeatability and detects thermal drift' },
            ].map((opt) => {
              const isSel = repetitions === opt.val;
              return (
                <button
                  key={opt.val}
                  type="button"
                  onClick={() => onChangeRepetitions(opt.val)}
                  style={{
                    flex: 1,
                    padding: '0.6rem 0.85rem',
                    borderRadius: radii.sm,
                    border: `1.5px solid ${isSel ? c.accent : c.border}`,
                    background: isSel ? (isLight ? '#e0e7ff' : 'rgba(113,112,255,0.22)') : c.surface,
                    color: isSel ? c.textPrimary : c.textSecondary,
                    textAlign: 'left',
                    cursor: 'pointer',
                  }}
                >
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: isSel ? c.accent : c.textPrimary }}>
                    {opt.label}
                  </div>
                  <div style={{ fontSize: '0.7rem', color: c.textTertiary, marginTop: 2 }}>
                    {opt.desc}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Section 3: Hardware Diagnostics & Storage */}
      <div
        style={{
          background: c.surface,
          borderRadius: radii.lg,
          padding: '1.5rem',
          border: `1px solid ${c.border}`,
          boxShadow: c.cardShadow,
        }}
      >
        <h3 style={{ margin: '0 0 0.4rem 0', fontSize: '1rem', color: c.textPrimary, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span>🛡️</span> Hardware Diagnostics & Storage
        </h3>
        <div style={{ fontSize: '0.78rem', color: c.textTertiary, marginBottom: '1rem' }}>
          Physical hardware sensors and persistence status.
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.75rem' }}>
          <div style={{ padding: '0.75rem', borderRadius: radii.md, background: c.surfaceElevated, border: `1px solid ${c.border}` }}>
            <div style={{ fontSize: '0.72rem', color: c.textTertiary, textTransform: 'uppercase', fontWeight: 600 }}>Energy Counter Source</div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: c.emerald, marginTop: 4, fontFamily: fonts.mono }}>
              /sys/class/powercap/intel-rapl:0/energy_uj
            </div>
            <div style={{ fontSize: '0.72rem', color: c.textTertiary, marginTop: 4 }}>
              package-0 (Zen 5 + Zen 5c + SoC Fabric)
            </div>
          </div>

          <div style={{ padding: '0.75rem', borderRadius: radii.md, background: c.surfaceElevated, border: `1px solid ${c.border}` }}>
            <div style={{ fontSize: '0.72rem', color: c.textTertiary, textTransform: 'uppercase', fontWeight: 600 }}>Persistent Database</div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: c.textPrimary, marginTop: 4, fontFamily: fonts.mono }}>
              ~/.joulectrl/joulectrl.db
            </div>
            <div style={{ fontSize: '0.72rem', color: c.textTertiary, marginTop: 4 }}>
              SQLite3 persistent store (runs & experiments)
            </div>
          </div>

          <div style={{ padding: '0.75rem', borderRadius: radii.md, background: c.surfaceElevated, border: `1px solid ${c.border}` }}>
            <div style={{ fontSize: '0.72rem', color: c.textTertiary, textTransform: 'uppercase', fontWeight: 600 }}>CPU Governor & Driver</div>
            <div style={{ fontSize: '0.85rem', fontWeight: 600, color: c.textPrimary, marginTop: 4, fontFamily: fonts.mono }}>
              amd_pstate (active)
            </div>
            <div style={{ fontSize: '0.72rem', color: c.textTertiary, marginTop: 4 }}>
              16 independent per-core sysfs policies
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
