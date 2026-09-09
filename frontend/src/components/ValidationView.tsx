import React, { useEffect, useState, useRef } from 'react';
import { Experiment } from '../types';
import { explainSelection, fetchValidationPoints, validateExperiment } from '../api';
import { getThemeColors, fonts, fontFeatures, radii, ThemeMode } from '../design';
import { useTheme } from '../ThemeContext';

interface ValidationViewProps {
  experiment: Experiment;
  onRefreshExperiment?: () => Promise<void>;
  onNavigateExplorer?: () => void;
  theme?: ThemeMode;
}

interface LayoutCandidate {
  kind: string;
  config_id: string;
  layout: string;
  cpu_mask: string;
  workers: number;
  description: string;
  measured: boolean;
  source: string;
}

export const ValidationView: React.FC<ValidationViewProps> = ({
  experiment,
  onRefreshExperiment,
  onNavigateExplorer,
  theme: propTheme,
}) => {
  const { theme: ctxTheme, themeColors: c } = useTheme();
  const theme = propTheme || ctxTheme;
  const isLight = theme === 'light';

  const validation = experiment?.validation || { pairs: [], status: 'not_run', verified_savings_pct: null, verified_runtime_delta_s: null };
  const selection = experiment?.selection;
  const pairs = validation.pairs || [];

  const [provider, setProvider] = useState<string>('template');
  const [explanation, setExplanation] = useState<{ text: string; grounding_facts: string[]; fallback?: boolean } | null>(null);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [validationMsg, setValidationMsg] = useState<string>('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [isExplaining, setIsExplaining] = useState<boolean>(false);
  const [layoutCandidates, setLayoutCandidates] = useState<LayoutCandidate[]>([]);
  const [isLoadingLayouts, setIsLoadingLayouts] = useState<boolean>(false);
  const [clockHoldInfo, setClockHoldInfo] = useState<{
    holdable: boolean;
    effective_khz: number | null;
    requires_passive_mode: boolean;
    reason: string;
  } | null>(null);

  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const selectedConfigId = selection?.config_id || (selection as any)?.selected_config_id;
  const selectedConfig =
    selection?.configuration ||
    (experiment?.profile?.configurations && selectedConfigId
      ? experiment.profile.configurations[selectedConfigId]?.configuration
      : null);

  // Fetch clock holdability check (<1ms)
  useEffect(() => {
    if (!selectedConfig) {
      setClockHoldInfo(null);
      return;
    }
    const cap = selectedConfig.freq_cap_khz;
    const boost = selectedConfig.boost;
    const affinity = selectedConfig.cpu_affinity?.join(',');
    const params = new URLSearchParams();
    if (cap) params.set('freq_cap_khz', String(cap));
    if (boost !== undefined && boost !== null) params.set('boost', String(boost));
    if (affinity) params.set('affinity', affinity);

    fetch(`/api/system/clock-check?${params.toString()}`)
      .then((r) => r.json())
      .then((data) => setClockHoldInfo(data))
      .catch((e) => console.warn('Clock hold check failed:', e));
  }, [selectedConfig?.freq_cap_khz, selectedConfig?.boost, selectedConfig?.cpu_affinity]);

  // Fetch explanation when experiment or selection changes
  useEffect(() => {
    let cancelled = false;
    if (!experiment?.id) return;

    explainSelection(experiment.id, provider)
      .then((res) => {
        if (!cancelled) {
          setExplanation({ text: res.text, grounding_facts: res.grounding_facts, fallback: res.fallback });
        }
      })
      .catch((e) => console.warn('Could not fetch explanation:', e));

    return () => {
      cancelled = true;
    };
  }, [experiment?.id, selectedConfigId, provider]);

  // Fetch validation point candidates (Layout A, B, C, D)
  useEffect(() => {
    let cancelled = false;
    if (!experiment?.id) return;

    setIsLoadingLayouts(true);
    fetchValidationPoints(experiment.id)
      .then((data) => {
        if (!cancelled && data?.layout_candidates) {
          setLayoutCandidates(data.layout_candidates);
        }
      })
      .catch((e) => console.warn('Could not fetch validation layout candidates:', e))
      .finally(() => {
        if (!cancelled) setIsLoadingLayouts(false);
      });

    return () => {
      cancelled = true;
    };
  }, [experiment?.id]);

  // Cleanup polling timer on unmount
  useEffect(() => {
    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, []);

  const handleRunValidation = async () => {
    if (!experiment?.id) return;
    setValidationError(null);
    setIsValidating(true);
    setValidationMsg('Starting hardware validation runs (Baseline vs Selected)...');

    try {
      await validateExperiment(experiment.id);
      setValidationMsg('Validation in progress on hardware counters. Measuring runs...');

      let attempts = 0;
      const maxAttempts = 60; // 60 * 1.5s = 90s max

      if (pollTimerRef.current) clearInterval(pollTimerRef.current);

      pollTimerRef.current = setInterval(async () => {
        attempts++;
        try {
          if (onRefreshExperiment) {
            await onRefreshExperiment();
          }

          if (experiment?.state === 'COMPLETE' || experiment?.state === 'complete' || attempts >= maxAttempts) {
            if (pollTimerRef.current) {
              clearInterval(pollTimerRef.current);
              pollTimerRef.current = null;
            }
            setIsValidating(false);
            setValidationMsg('');
          }
        } catch {
          // ignore transient poll error
        }
      }, 1500);
    } catch (e: any) {
      setValidationError(e?.message || 'Failed to trigger validation run');
      setIsValidating(false);
      setValidationMsg('');
    }
  };

  const handleGenerateExplanation = async (selectedProvider: string) => {
    if (!experiment?.id) return;
    setIsExplaining(true);
    setProvider(selectedProvider);
    try {
      const res = await explainSelection(experiment.id, selectedProvider);
      setExplanation({ text: res.text, grounding_facts: res.grounding_facts, fallback: res.fallback });
    } catch (e: any) {
      setExplanation({ text: `Explanation unavailable: ${e?.message || e}`, grounding_facts: [], fallback: true });
    } finally {
      setIsExplaining(false);
    }
  };

  const handleExport = () => {
    if (!experiment?.id) return;
    window.open(`/api/experiments/${experiment.id}/export`, '_blank');
  };

  const restorationLabels: Record<string, { title: string; color: string; bg: string; border: string; icon: string }> = {
    restored: {
      title: 'Restoration Status: Fully Restored',
      color: c.emerald,
      bg: isLight ? '#ecfdf5' : 'rgba(16,185,129,0.15)',
      border: isLight ? '#a7f3d0' : c.emerald,
      icon: '🛡️',
    },
    restoring: {
      title: 'Restoration Status: Restoring…',
      color: c.amber,
      bg: isLight ? '#fffbeb' : 'rgba(245,158,11,0.10)',
      border: isLight ? '#fde68a' : c.amber,
      icon: '⏳',
    },
    recovery_required: {
      title: 'Restoration Status: Recovery Required',
      color: c.red,
      bg: isLight ? '#fef2f2' : 'rgba(244,88,110,0.15)',
      border: isLight ? '#fecaca' : c.red,
      icon: '⚠️',
    },
    not_required: {
      title: 'Restoration Status: No Controls Applied',
      color: c.textTertiary,
      bg: isLight ? '#f8fafc' : 'rgba(25,26,27,0.15)',
      border: isLight ? '#e2e8f0' : 'rgba(255,255,255,0.08)',
      icon: 'ℹ️',
    },
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1100px', margin: '0 auto', fontFamily: fonts.sans }}>
      {/* Header & Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: c.surface,
          padding: '1.25rem',
          borderRadius: radii.lg,
          border: `1px solid ${c.border}`,
          boxShadow: c.cardShadow,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
            <h2 style={{ margin: 0, fontSize: '1.2rem', color: c.textPrimary, fontWeight: 600 }}>
              Empirical Validation &amp; Explanation
            </h2>
            {clockHoldInfo && (
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 5,
                  padding: '2px 8px',
                  borderRadius: radii.full,
                  fontSize: '0.74rem',
                  fontWeight: 600,
                  fontFamily: fonts.mono,
                  background: clockHoldInfo.requires_passive_mode
                    ? (isLight ? 'rgba(99,102,241,0.1)' : 'rgba(113,112,255,0.15)')
                    : (isLight ? 'rgba(22,163,74,0.1)' : 'rgba(16,185,129,0.15)'),
                  color: clockHoldInfo.requires_passive_mode ? c.accent : c.emerald,
                  border: `1px solid ${clockHoldInfo.requires_passive_mode ? (isLight ? '#c7d2fe' : c.accent) : (isLight ? '#bbf7d0' : c.emerald)}`,
                }}
                title={clockHoldInfo.reason}
              >
                <span>{clockHoldInfo.requires_passive_mode ? '🔄' : '⚡'}</span>
                <span>
                  {selectedConfig?.freq_cap_khz
                    ? `${(selectedConfig.freq_cap_khz / 1000000).toFixed(1)} GHz Target: ${
                        clockHoldInfo.requires_passive_mode ? 'Holdable (via Passive P-State)' : 'Holdable'
                      }`
                    : 'Stock Clock (Boost Active)'}
                </span>
              </span>
            )}
          </div>
          <div style={{ fontSize: '0.8rem', color: c.textTertiary, marginTop: '0.25rem' }}>
            Fresh executions of Stock Baseline vs Selected Candidate to empirically verify package-energy savings on hardware counters.
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={handleRunValidation}
            disabled={isValidating || !selectedConfigId}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: radii.md,
              backgroundColor: isValidating ? (isLight ? '#c7d2fe' : 'rgba(113,112,255,0.3)') : c.accentBg,
              color: '#ffffff',
              fontSize: '0.85rem',
              fontWeight: 600,
              border: 'none',
              cursor: isValidating ? 'wait' : !selectedConfigId ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              opacity: !selectedConfigId ? 0.6 : 1,
              boxShadow: isLight ? '0 1px 2px rgba(99,102,241,0.2)' : 'none',
            }}
          >
            {isValidating ? (
              <>
                <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite' }}>⏳</span>
                Validating on Hardware...
              </>
            ) : (
              '⚡ Run Fresh Validation Pairs'
            )}
          </button>

          <button
            onClick={handleExport}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: radii.md,
              backgroundColor: isLight ? '#f1f5f9' : 'rgba(255,255,255,0.06)',
              color: c.textPrimary,
              fontSize: '0.85rem',
              fontWeight: 600,
              border: `1px solid ${c.border}`,
              cursor: 'pointer',
            }}
          >
            Export JSON Archive ⤓
          </button>
        </div>
      </div>

      {/* Active Validation Status Notification */}
      {isValidating && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            background: isLight ? '#eef2ff' : 'rgba(113, 112, 255, 0.12)',
            border: `1px solid ${c.accent}`,
            padding: '0.85rem 1.25rem',
            borderRadius: radii.md,
            color: c.textPrimary,
            fontSize: '0.85rem',
          }}
        >
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              border: `2px solid ${c.accent}`,
              borderTopColor: 'transparent',
              animation: 'spin 1s linear infinite',
            }}
          />
          <div>{validationMsg || 'Measuring baseline vs selected candidate on hardware...'}</div>
        </div>
      )}

      {validationError && (
        <div
          style={{
            background: isLight ? '#fef2f2' : 'rgba(244, 88, 110, 0.12)',
            border: `1px solid ${c.red}`,
            padding: '0.85rem 1.25rem',
            borderRadius: radii.md,
            color: c.red,
            fontSize: '0.85rem',
          }}
        >
          Validation Notice: {validationError}
        </div>
      )}

      {/* No Selection Warning */}
      {!selectedConfigId && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: isLight ? '#fffbeb' : 'rgba(245, 158, 11, 0.10)',
            border: `1px solid ${c.amber}`,
            padding: '1rem 1.25rem',
            borderRadius: radii.md,
          }}
        >
          <div>
            <div style={{ fontWeight: 600, color: c.amber, fontSize: '0.9rem' }}>
              No Target Configuration Selected
            </div>
            <div style={{ fontSize: '0.8rem', color: c.textSecondary, marginTop: '0.2rem' }}>
              Validation compares a selected configuration against the stock baseline. Choose a configuration in the Explorer tab first.
            </div>
          </div>
          {onNavigateExplorer && (
            <button
              onClick={onNavigateExplorer}
              style={{
                padding: '0.4rem 0.8rem',
                borderRadius: radii.md,
                background: c.surfaceElevated,
                color: c.textPrimary,
                border: `1px solid ${c.border}`,
                fontSize: '0.8rem',
                cursor: 'pointer',
              }}
            >
              Go to Explorer ➔
            </button>
          )}
        </div>
      )}

      {/* Fresh Validation Pairs Table */}
      <div
        style={{
          background: c.surface,
          borderRadius: radii.lg,
          padding: '1.25rem',
          border: `1px solid ${c.border}`,
          boxShadow: c.cardShadow,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: 8 }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1rem', color: c.textPrimary, fontWeight: 600 }}>
              Fresh Validation Executions ({pairs.length} {pairs.length === 1 ? 'Pair' : 'Pairs'})
            </h3>
            <div style={{ fontSize: '0.75rem', color: c.textTertiary, marginTop: '0.2rem' }}>
              Each pair is run back-to-back with hardware counter bracketing and full state restoration before and after each run.
            </div>
          </div>
          {validation.verified_savings_pct != null && (
            <div
              style={{
                fontSize: '0.9rem',
                color: c.emerald,
                fontWeight: 700,
                background: isLight ? '#ecfdf5' : 'rgba(16, 185, 129, 0.12)',
                padding: '0.4rem 0.8rem',
                borderRadius: radii.md,
                border: `1px solid ${isLight ? '#a7f3d0' : 'rgba(16, 185, 129, 0.3)'}`,
              }}
            >
              Observed Energy Savings: {validation.verified_savings_pct.toFixed(1)}%
            </div>
          )}
        </div>

        {pairs.length === 0 ? (
          <div
            style={{
              padding: '2.5rem 1rem',
              textAlign: 'center',
              fontSize: '0.85rem',
              color: c.textTertiary,
              background: c.surfaceElevated,
              borderRadius: radii.md,
              border: `1px dashed ${c.border}`,
            }}
          >
            <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>📊</div>
            <div style={{ fontWeight: 600, color: c.textSecondary, marginBottom: '0.25rem' }}>
              No validation pairs measured yet
            </div>
            <div>
              Click <strong>"Run Fresh Validation Pairs"</strong> above to benchmark the baseline against{' '}
              {selectedConfigId ? <code style={{ color: c.emerald, fontWeight: 600 }}>{selectedConfigId}</code> : 'your selected configuration'}.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${c.border}`, color: c.textTertiary }}>
                  <th style={{ padding: '0.6rem 0.5rem' }}>Pair</th>
                  <th style={{ padding: '0.6rem 0.5rem' }}>Baseline (Stock)</th>
                  <th style={{ padding: '0.6rem 0.5rem' }}>Selected Candidate</th>
                  <th style={{ padding: '0.6rem 0.5rem' }}>Runtime Delta</th>
                  <th style={{ padding: '0.6rem 0.5rem' }}>Package Energy Delta</th>
                  <th style={{ padding: '0.6rem 0.5rem' }}>Verification</th>
                </tr>
              </thead>
              <tbody>
                {pairs.map((p) => {
                  const bRun = p.baseline_run;
                  const sRun = p.selected_run;

                  const eBase = bRun?.package_energy_j;
                  const eSel = sRun?.package_energy_j;

                  const eSavings =
                    eBase != null && eSel != null && eBase > 0
                      ? Math.round(100 * (1 - eSel / eBase))
                      : p.energy_reduction_pct != null
                        ? Math.round(p.energy_reduction_pct)
                        : null;

                  const tDelta =
                    sRun?.runtime_s != null && bRun?.runtime_s != null
                      ? (sRun.runtime_s - bRun.runtime_s).toFixed(1)
                      : null;

                  return (
                    <tr key={p.pair_index} style={{ borderBottom: `1px solid ${c.borderSubtle}` }}>
                      <td style={{ padding: '0.65rem 0.5rem', fontWeight: 600, color: c.textPrimary }}>
                        Pair #{p.pair_index}
                      </td>
                      <td style={{ padding: '0.65rem 0.5rem', color: c.textSecondary, fontFamily: fonts.mono }}>
                        {bRun?.runtime_s != null ? `${bRun.runtime_s.toFixed(1)}s` : '—'} ·{' '}
                        {eBase != null ? `${eBase.toFixed(1)} J` : 'energy N/A'}
                      </td>
                      <td style={{ padding: '0.65rem 0.5rem', color: c.emerald, fontWeight: 600, fontFamily: fonts.mono }}>
                        {sRun?.runtime_s != null && sRun.runtime_s > 0 ? `${sRun.runtime_s.toFixed(1)}s` : '0.0s'} ·{' '}
                        {eSel != null ? `${eSel.toFixed(1)} J` : 'energy N/A'}
                      </td>
                      <td style={{ padding: '0.65rem 0.5rem', color: c.textPrimary, fontFamily: fonts.mono }}>
                        {tDelta != null ? `${Number(tDelta) >= 0 ? '+' : ''}${tDelta}s` : '—'}
                      </td>
                      <td
                        style={{
                          padding: '0.65rem 0.5rem',
                          color: eSavings != null && eSavings > 0 ? c.emerald : c.textTertiary,
                          fontWeight: 700,
                          fontFamily: fonts.mono,
                        }}
                      >
                        {eSavings != null ? `${eSavings >= 0 ? '-' : '+'}${Math.abs(eSavings)}%` : 'N/A'}
                      </td>
                      <td style={{ padding: '0.65rem 0.5rem' }}>
                        {p.both_succeeded ? (
                          <span
                            style={{
                              color: c.emerald,
                              background: isLight ? '#ecfdf5' : 'rgba(16,185,129,0.12)',
                              border: `1px solid ${isLight ? '#a7f3d0' : 'rgba(16,185,129,0.3)'}`,
                              padding: '0.2rem 0.5rem',
                              borderRadius: radii.sm,
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            ✓ Output Verified
                          </span>
                        ) : (
                          <span
                            style={{
                              color: c.red,
                              background: isLight ? '#fef2f2' : 'rgba(244,88,110,0.12)',
                              border: `1px solid ${isLight ? '#fecaca' : 'rgba(244,88,110,0.3)'}`,
                              padding: '0.2rem 0.5rem',
                              borderRadius: radii.sm,
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            ✗ Run Failed
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Topology Layout Candidates Explorer */}
      <div
        style={{
          background: c.surface,
          borderRadius: radii.lg,
          padding: '1.25rem',
          border: `1px solid ${c.border}`,
          boxShadow: c.cardShadow,
        }}
      >
        <div style={{ marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, fontSize: '1rem', color: c.textPrimary, fontWeight: 600 }}>
            Execution Layout Candidates (Topology Verification)
          </h3>
          <div style={{ fontSize: '0.78rem', color: c.textTertiary, marginTop: '0.25rem' }}>
            Discovered hardware layout options based on CPU topology (Fast Cores, All Physical, All Logical, Efficient Cores).
          </div>
        </div>

        {isLoadingLayouts ? (
          <div style={{ padding: '1rem', color: c.textTertiary, fontSize: '0.85rem' }}>Loading layout points...</div>
        ) : layoutCandidates.length > 0 ? (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
              gap: '0.75rem',
            }}
          >
            {layoutCandidates.map((cand) => {
              const isSelected = selectedConfigId === cand.config_id || (cand.layout === selection?.configuration?.layout);
              return (
                <div
                  key={cand.config_id}
                  style={{
                    background: isSelected
                      ? (isLight ? '#eef2ff' : 'rgba(113, 112, 255, 0.08)')
                      : c.surfaceElevated,
                    border: `1px solid ${isSelected ? c.accent : c.border}`,
                    borderRadius: radii.md,
                    padding: '0.85rem',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.4rem',
                    boxShadow: isSelected && isLight ? '0 1px 3px rgba(99,102,241,0.15)' : 'none',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        color: c.accent,
                        background: isLight ? '#e0e7ff' : 'rgba(113, 112, 255, 0.15)',
                        padding: '0.15rem 0.45rem',
                        borderRadius: radii.xs,
                      }}
                    >
                      Layout {cand.layout}
                    </span>
                    {isSelected && (
                      <span style={{ fontSize: '0.7rem', color: c.emerald, fontWeight: 600 }}>
                        ★ Active Layout
                      </span>
                    )}
                  </div>

                  <div style={{ fontWeight: 600, fontSize: '0.85rem', color: c.textPrimary, marginTop: '0.1rem' }}>
                    {cand.config_id}
                  </div>

                  <div style={{ fontSize: '0.75rem', color: c.textSecondary }}>
                    {cand.description}
                  </div>

                  <div
                    style={{
                      marginTop: 'auto',
                      paddingTop: '0.4rem',
                      borderTop: `1px solid ${c.borderSubtle}`,
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '0.72rem',
                      color: c.textTertiary,
                    }}
                  >
                    <span>Workers: <strong>{cand.workers}</strong></span>
                    <span>Mask: <code style={{ color: c.textSecondary }}>{cand.cpu_mask}</code></span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ fontSize: '0.8rem', color: c.textTertiary }}>
            Layout candidates generated dynamically from discovered machine topology.
          </div>
        )}
      </div>

      {/* Explanation Card */}
      <div
        style={{
          background: c.surface,
          borderRadius: radii.lg,
          padding: '1.25rem',
          border: `1px solid ${c.border}`,
          boxShadow: c.cardShadow,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem', flexWrap: 'wrap', gap: 8 }}>
          <h3 style={{ margin: 0, fontSize: '1rem', color: c.textPrimary, fontWeight: 600 }}>
            Deterministic Explanation &amp; Rationale
          </h3>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {['template', 'local_llm', 'cloud_llm'].map((p) => (
              <button
                key={p}
                onClick={() => handleGenerateExplanation(p)}
                disabled={isExplaining}
                style={{
                  padding: '0.3rem 0.6rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  borderRadius: radii.sm,
                  border: `1px solid ${provider === p ? c.accent : c.border}`,
                  backgroundColor: provider === p
                    ? (isLight ? '#e0e7ff' : 'rgba(113,112,255,0.2)')
                    : c.surfaceElevated,
                  color: provider === p ? c.accent : c.textTertiary,
                  cursor: isExplaining ? 'wait' : 'pointer',
                  textTransform: 'capitalize',
                }}
              >
                {p.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>

        {explanation ? (
          <div
            style={{
              background: c.surfaceElevated,
              borderRadius: radii.md,
              padding: '1rem',
              border: `1px solid ${c.border}`,
            }}
          >
            {explanation.fallback && (
              <div style={{ fontSize: '0.75rem', color: c.amber, marginBottom: '0.5rem' }}>
                ⚠ Requested provider unavailable — degraded to deterministic Basic templates (guaranteed default).
              </div>
            )}
            <div style={{ fontSize: '0.9rem', color: c.textPrimary, lineHeight: 1.5, marginBottom: '0.75rem', whiteSpace: 'pre-line' }}>
              {explanation.text}
            </div>
            {explanation.grounding_facts && explanation.grounding_facts.length > 0 && (
              <div style={{ borderTop: `1px solid ${c.borderSubtle}`, paddingTop: '0.6rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: c.textTertiary, marginBottom: '0.3rem' }}>
                  Grounding Facts (Empirically Verified):
                </div>
                <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.78rem', color: c.textSecondary, display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                  {explanation.grounding_facts.map((fact, idx) => (
                    <li key={idx}>{fact}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div style={{ padding: '1rem', color: c.textTertiary, fontSize: '0.85rem' }}>
            Select a configuration to generate an explanation and evidence breakdown.
          </div>
        )}
      </div>

      {/* Restoration Card */}
      {(() => {
        const statusKey = experiment?.restoration_status || 'not_required';
        const label = restorationLabels[statusKey] ?? restorationLabels.not_required;
        return (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: label.bg,
              border: `1px solid ${label.border}`,
              padding: '0.9rem 1.25rem',
              borderRadius: radii.md,
            }}
          >
            <div>
              <div style={{ fontWeight: 600, color: label.color, fontSize: '0.9rem' }}>{label.title}</div>
              <div style={{ fontSize: '0.75rem', color: c.textSecondary, marginTop: '0.2rem' }}>
                {statusKey === 'restored'
                  ? 'Stock frequencies, power limits, and boost configurations restored to initial state.'
                  : statusKey === 'recovery_required'
                    ? 'Restoration could not be verified — run the manual restore command before the next experiment.'
                    : 'Restoration state is tracked in the persisted experiment record.'}
              </div>
            </div>
            <span style={{ fontSize: '1.2rem' }}>{label.icon}</span>
          </div>
        );
      })()}

      {/* Mandatory Footer per PLAN §11 */}
      <footer
        style={{
          textAlign: 'center',
          padding: '1.5rem 0',
          fontSize: '0.75rem',
          color: c.textTertiary,
          borderTop: `1px solid ${c.borderSubtle}`,
        }}
      >
        CPU-package energy, not whole-system electricity. Best among measured configurations; future runtimes may vary.
      </footer>
    </div>
  );
};
