import React, { useEffect, useState, useRef } from 'react';
import { Experiment } from '../types';
import { explainSelection, fetchExperiment, fetchValidationPoints, validateExperiment } from '../api';
import { colors } from '../design';

interface ValidationViewProps {
  experiment: Experiment;
  onRefreshExperiment?: () => Promise<void>;
  onNavigateExplorer?: () => void;
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

const RESTORATION_LABELS: Record<string, { title: string; color: string; bg: string; border: string; icon: string }> = {
  restored: {
    title: 'Restoration Status: Fully Restored',
    color: colors.emerald,
    bg: 'rgba(16,185,129,0.15)',
    border: colors.emerald,
    icon: '🛡️',
  },
  restoring: {
    title: 'Restoration Status: Restoring…',
    color: colors.amber,
    bg: 'rgba(245,158,11,0.10)',
    border: colors.amber,
    icon: '⏳',
  },
  recovery_required: {
    title: 'Restoration Status: Recovery Required',
    color: colors.red,
    bg: 'rgba(244,88,110,0.15)',
    border: colors.red,
    icon: '⚠️',
  },
  not_required: {
    title: 'Restoration Status: No Controls Applied',
    color: colors.textTertiary,
    bg: 'rgba(25,26,27,0.15)',
    border: 'rgba(255,255,255,0.08)',
    icon: 'ℹ️',
  },
};

export const ValidationView: React.FC<ValidationViewProps> = ({
  experiment,
  onRefreshExperiment,
  onNavigateExplorer,
}) => {
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

  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

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
  }, [experiment?.id, selection?.config_id, provider]);

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
          } else {
            await fetchExperiment(experiment.id);
          }

          // Check if experiment has updated validation pairs
          const updated = await fetchExperiment(experiment.id);
          const updatedPairs = updated?.validation?.pairs || [];
          const currentCount = updatedPairs.length;

          if (currentCount > 0) {
            setValidationMsg(`Measured ${currentCount} of 3 validation pairs on hardware...`);
          }

          if (currentCount >= 3 || updated.state === 'complete' || updated.validation?.status === 'verified' || attempts >= maxAttempts) {
            if (pollTimerRef.current) clearInterval(pollTimerRef.current);
            setIsValidating(false);
            if (currentCount > 0) {
              setValidationMsg(`Validation completed: ${currentCount} pairs measured and verified.`);
            } else {
              setValidationMsg('Validation complete.');
            }
          }
        } catch (pollErr) {
          console.warn('Validation poll error:', pollErr);
        }
      }, 1500);

    } catch (e: any) {
      setValidationError(e?.message || 'Failed to start validation');
      setIsValidating(false);
      setValidationMsg('');
    }
  };

  const handleGenerateExplanation = async (p: string) => {
    if (!experiment?.id) return;
    try {
      setIsExplaining(true);
      setProvider(p);
      const res = await explainSelection(experiment.id, p);
      setExplanation({ text: res.text, grounding_facts: res.grounding_facts, fallback: res.fallback });
    } catch (e: any) {
      console.warn(`Explanation error: ${e?.message}`);
    } finally {
      setIsExplaining(false);
    }
  };

  const handleExport = () => {
    if (!experiment?.id) return;
    window.open(`/api/experiments/${experiment.id}/export`, '_blank');
  };

  const selectedConfigId = selection?.config_id || selection?.selected_config_id;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1100px', margin: '0 auto' }}>
      {/* Header & Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: colors.surface,
          padding: '1.25rem',
          borderRadius: '0.75rem',
          border: colors.border,
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: '1.2rem', color: colors.textPrimary, fontWeight: 600 }}>
            Empirical Validation &amp; Explanation
          </h2>
          <div style={{ fontSize: '0.8rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
            Fresh executions of Stock Baseline vs Selected Candidate to empirically verify package-energy savings on hardware counters.
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={handleRunValidation}
            disabled={isValidating || !selectedConfigId}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '0.375rem',
              backgroundColor: isValidating ? 'rgba(113,112,255,0.3)' : colors.accentBg,
              color: colors.textPrimary,
              fontSize: '0.85rem',
              fontWeight: 600,
              border: 'none',
              cursor: isValidating ? 'wait' : !selectedConfigId ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              opacity: !selectedConfigId ? 0.6 : 1,
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
              borderRadius: '0.375rem',
              backgroundColor: 'rgba(255,255,255,0.08)',
              color: colors.textPrimary,
              fontSize: '0.85rem',
              fontWeight: 600,
              border: colors.border,
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
            background: 'rgba(113, 112, 255, 0.12)',
            border: `1px solid ${colors.accent}`,
            padding: '0.85rem 1.25rem',
            borderRadius: '0.5rem',
            color: colors.textPrimary,
            fontSize: '0.85rem',
          }}
        >
          <div
            style={{
              width: '12px',
              height: '12px',
              borderRadius: '50%',
              border: `2px solid ${colors.accent}`,
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
            background: 'rgba(244, 88, 110, 0.12)',
            border: `1px solid ${colors.red}`,
            padding: '0.85rem 1.25rem',
            borderRadius: '0.5rem',
            color: colors.red,
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
            background: 'rgba(245, 158, 11, 0.10)',
            border: `1px solid ${colors.amber}`,
            padding: '1rem 1.25rem',
            borderRadius: '0.5rem',
          }}
        >
          <div>
            <div style={{ fontWeight: 600, color: colors.amber, fontSize: '0.9rem' }}>
              No Target Configuration Selected
            </div>
            <div style={{ fontSize: '0.8rem', color: colors.textSecondary, marginTop: '0.2rem' }}>
              Validation compares a selected configuration against the stock baseline. Choose a configuration in the Explorer tab first.
            </div>
          </div>
          {onNavigateExplorer && (
            <button
              onClick={onNavigateExplorer}
              style={{
                padding: '0.4rem 0.8rem',
                borderRadius: '0.375rem',
                background: colors.surfaceElevated,
                color: colors.textPrimary,
                border: colors.border,
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
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.25rem', border: colors.border }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1rem', color: colors.textPrimary, fontWeight: 600 }}>
              Fresh Validation Executions ({pairs.length} {pairs.length === 1 ? 'Pair' : 'Pairs'})
            </h3>
            <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginTop: '0.2rem' }}>
              Each pair is run back-to-back with hardware counter bracketing and full state restoration before and after each run.
            </div>
          </div>
          {validation.verified_savings_pct != null && (
            <div
              style={{
                fontSize: '0.9rem',
                color: colors.emerald,
                fontWeight: 700,
                background: 'rgba(16, 185, 129, 0.12)',
                padding: '0.4rem 0.8rem',
                borderRadius: '0.375rem',
                border: '1px solid rgba(16, 185, 129, 0.3)',
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
              color: colors.textTertiary,
              background: colors.surfaceElevated,
              borderRadius: '0.5rem',
              border: '1px dashed rgba(255,255,255,0.08)',
            }}
          >
            <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>📊</div>
            <div style={{ fontWeight: 600, color: colors.textSecondary, marginBottom: '0.25rem' }}>
              No validation pairs measured yet
            </div>
            <div>
              Click <strong>"Run Fresh Validation Pairs"</strong> above to benchmark the baseline against{' '}
              {selectedConfigId ? <code style={{ color: colors.emerald }}>{selectedConfigId}</code> : 'your selected configuration'}.
            </div>
          </div>
        ) : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', color: colors.textTertiary }}>
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
                    <tr key={p.pair_index} style={{ borderBottom: colors.border }}>
                      <td style={{ padding: '0.65rem 0.5rem', fontWeight: 600, color: colors.textPrimary }}>
                        Pair #{p.pair_index}
                      </td>
                      <td style={{ padding: '0.65rem 0.5rem', color: colors.textSecondary }}>
                        {bRun?.runtime_s != null ? `${bRun.runtime_s.toFixed(1)}s` : '—'} ·{' '}
                        {eBase != null ? `${eBase.toFixed(1)} J` : 'energy N/A'}
                      </td>
                      <td style={{ padding: '0.65rem 0.5rem', color: colors.emerald, fontWeight: 600 }}>
                        {sRun?.runtime_s != null ? `${sRun.runtime_s.toFixed(1)}s` : '—'} ·{' '}
                        {eSel != null ? `${eSel.toFixed(1)} J` : 'energy N/A'}
                      </td>
                      <td style={{ padding: '0.65rem 0.5rem', color: colors.textPrimary }}>
                        {tDelta != null ? `${Number(tDelta) >= 0 ? '+' : ''}${tDelta}s` : '—'}
                      </td>
                      <td
                        style={{
                          padding: '0.65rem 0.5rem',
                          color: eSavings != null && eSavings > 0 ? colors.emerald : colors.textTertiary,
                          fontWeight: 700,
                        }}
                      >
                        {eSavings != null ? `${eSavings >= 0 ? '-' : '+'}${Math.abs(eSavings)}%` : 'N/A'}
                      </td>
                      <td style={{ padding: '0.65rem 0.5rem' }}>
                        {p.both_succeeded ? (
                          <span
                            style={{
                              color: colors.emerald,
                              background: 'rgba(16,185,129,0.12)',
                              padding: '0.2rem 0.5rem',
                              borderRadius: '0.25rem',
                              fontSize: '0.75rem',
                              fontWeight: 600,
                            }}
                          >
                            ✓ Output Verified
                          </span>
                        ) : (
                          <span
                            style={{
                              color: colors.red,
                              background: 'rgba(244,88,110,0.12)',
                              padding: '0.2rem 0.5rem',
                              borderRadius: '0.25rem',
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
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.25rem', border: colors.border }}>
        <div style={{ marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, fontSize: '1rem', color: colors.textPrimary, fontWeight: 600 }}>
            Execution Layout Candidates (Topology Verification)
          </h3>
          <div style={{ fontSize: '0.78rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
            Discovered hardware layout options based on CPU topology (Fast Cores, All Physical, All Logical, Efficient Cores).
          </div>
        </div>

        {isLoadingLayouts ? (
          <div style={{ padding: '1rem', color: colors.textTertiary, fontSize: '0.85rem' }}>Loading layout points...</div>
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
                    background: isSelected ? 'rgba(113, 112, 255, 0.08)' : colors.surfaceElevated,
                    border: `1px solid ${isSelected ? colors.accent : 'rgba(255,255,255,0.08)'}`,
                    borderRadius: '0.5rem',
                    padding: '0.85rem',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.4rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        color: colors.accentHover,
                        background: 'rgba(113, 112, 255, 0.15)',
                        padding: '0.15rem 0.45rem',
                        borderRadius: '0.25rem',
                      }}
                    >
                      Layout {cand.layout}
                    </span>
                    {isSelected && (
                      <span style={{ fontSize: '0.7rem', color: colors.emerald, fontWeight: 600 }}>
                        ★ Active Layout
                      </span>
                    )}
                  </div>

                  <div style={{ fontWeight: 600, fontSize: '0.85rem', color: colors.textPrimary, marginTop: '0.1rem' }}>
                    {cand.config_id}
                  </div>

                  <div style={{ fontSize: '0.75rem', color: colors.textSecondary }}>
                    {cand.description}
                  </div>

                  <div style={{ marginTop: 'auto', paddingTop: '0.4rem', borderTop: '1px solid rgba(255,255,255,0.06)', display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem', color: colors.textTertiary }}>
                    <span>Workers: <strong>{cand.workers}</strong></span>
                    <span>Mask: <code style={{ color: colors.textSecondary }}>{cand.cpu_mask}</code></span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ fontSize: '0.8rem', color: colors.textTertiary }}>
            Layout candidates generated dynamically from discovered machine topology.
          </div>
        )}
      </div>

      {/* Explanation Card */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.25rem', border: colors.border }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, fontSize: '1rem', color: colors.textPrimary, fontWeight: 600 }}>
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
                  borderRadius: '0.25rem',
                  border: `1px solid ${provider === p ? colors.accent : 'rgba(255,255,255,0.08)'}`,
                  backgroundColor: provider === p ? 'rgba(113,112,255,0.2)' : colors.surfaceElevated,
                  color: provider === p ? colors.accentHover : colors.textTertiary,
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
          <div style={{ background: colors.surfaceElevated, borderRadius: '0.5rem', padding: '1rem', border: '1px solid rgba(255,255,255,0.08)' }}>
            {explanation.fallback && (
              <div style={{ fontSize: '0.75rem', color: colors.amber, marginBottom: '0.5rem' }}>
                ⚠ Requested provider unavailable — degraded to deterministic Basic templates (guaranteed default).
              </div>
            )}
            <div style={{ fontSize: '0.9rem', color: colors.textPrimary, lineHeight: 1.5, marginBottom: '0.75rem', whiteSpace: 'pre-line' }}>
              {explanation.text}
            </div>
            {explanation.grounding_facts && explanation.grounding_facts.length > 0 && (
              <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '0.6rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: colors.textTertiary, marginBottom: '0.3rem' }}>
                  Grounding Facts (Empirically Verified):
                </div>
                <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.78rem', color: colors.textSecondary, display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                  {explanation.grounding_facts.map((fact, idx) => (
                    <li key={idx}>{fact}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <div style={{ padding: '1rem', color: colors.textTertiary, fontSize: '0.85rem' }}>
            Select a configuration to generate an explanation and evidence breakdown.
          </div>
        )}
      </div>

      {/* Restoration Card */}
      {(() => {
        const statusKey = experiment?.restoration_status || 'not_required';
        const label = RESTORATION_LABELS[statusKey] ?? RESTORATION_LABELS.not_required;
        return (
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              background: label.bg,
              border: `1px solid ${label.border}`,
              padding: '0.9rem 1.25rem',
              borderRadius: '0.5rem',
            }}
          >
            <div>
              <div style={{ fontWeight: 600, color: label.color, fontSize: '0.9rem' }}>{label.title}</div>
              <div style={{ fontSize: '0.75rem', color: colors.textSecondary, marginTop: '0.2rem' }}>
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
          color: colors.textTertiary,
          borderTop: colors.border,
        }}
      >
        CPU-package energy, not whole-system electricity. Best among measured configurations; future runtimes may vary.
      </footer>
    </div>
  );
};

