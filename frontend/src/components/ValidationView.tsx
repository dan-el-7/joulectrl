import React, { useEffect, useState } from 'react';
import { Experiment } from '../types';
import { explainSelection, validateExperiment } from '../api';

interface ValidationViewProps {
  experiment: Experiment;
}

const RESTORATION_LABELS: Record<string, { title: string; color: string; bg: string; border: string; icon: string }> = {
  restored: {
    title: 'Restoration Status: Fully Restored',
    color: '#10b981',
    bg: 'rgba(16,185,129,0.12)15',
    border: '#10b981',
    icon: '🛡️',
  },
  restoring: {
    title: 'Restoration Status: Restoring…',
    color: '#fcd34d',
    bg: '#78350f15',
    border: '#b45309',
    icon: '⏳',
  },
  recovery_required: {
    title: 'Restoration Status: Recovery Required',
    color: '#f4586e',
    bg: 'rgba(244,88,110,0.10)15',
    border: '#b91c1c',
    icon: '⚠️',
  },
  not_required: {
    title: 'Restoration Status: No Controls Applied',
    color: '#8a8f98',
    bg: '#191a1b15',
    border: 'rgba(255,255,255,0.08)',
    icon: 'ℹ️',
  },
};

export const ValidationView: React.FC<ValidationViewProps> = ({ experiment }) => {
  const { validation, selection, profile } = experiment;
  const [provider, setProvider] = useState<string>('template');
  const [explanation, setExplanation] = useState<{ text: string; grounding_facts: string[]; fallback?: boolean } | null>(null);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [isExplaining, setIsExplaining] = useState<boolean>(false);

  // Explanation comes from the API's deterministic template layer (explain/),
  // grounded in the same persisted facts the dashboard renders.
  useEffect(() => {
    let cancelled = false;
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [experiment.id, selection.config_id]);

  const handleRunValidation = async () => {
    try {
      setIsValidating(true);
      await validateExperiment(experiment.id);
      alert('Validation runs scheduled on hardware counters.');
    } catch (e: any) {
      alert(`Validation error: ${e.message}`);
    } finally {
      setIsValidating(false);
    }
  };

  const handleGenerateExplanation = async (p: string) => {
    try {
      setIsExplaining(true);
      setProvider(p);
      const res = await explainSelection(experiment.id, p);
      setExplanation({ text: res.text, grounding_facts: res.grounding_facts, fallback: res.fallback });
    } catch (e: any) {
      alert(`Explanation error: ${e.message}`);
    } finally {
      setIsExplaining(false);
    }
  };

  const handleExport = () => {
    window.open(`/api/experiments/${experiment.id}/export`, '_blank');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1100px', margin: '0 auto' }}>
      {/* Header & Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: '#141516',
          padding: '1.25rem',
          borderRadius: '0.75rem',
          border: '1px solid #191a1b',
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: '1.2rem', color: '#f7f8f8', fontWeight: 600 }}>
            Validation &amp; Explanation
          </h2>
          <div style={{ fontSize: '0.8rem', color: '#8a8f98', marginTop: '0.25rem' }}>
            Fresh executions of Baseline vs Selected to empirically verify package-energy savings.
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <button
            onClick={handleRunValidation}
            disabled={isValidating}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '0.375rem',
              backgroundColor: '#5e6ad2',
              color: '#ffffff',
              fontSize: '0.85rem',
              fontWeight: 600,
              border: 'none',
              cursor: isValidating ? 'wait' : 'pointer',
            }}
          >
            {isValidating ? 'Validating on Hardware...' : 'Run Fresh Validation Pairs'}
          </button>

          <button
            onClick={handleExport}
            style={{
              padding: '0.5rem 1rem',
              borderRadius: '0.375rem',
              backgroundColor: 'rgba(255,255,255,0.08)',
              color: '#f7f8f8',
              fontSize: '0.85rem',
              fontWeight: 600,
              border: '1px solid #62666d',
              cursor: 'pointer',
            }}
          >
            Export JSON Archive ⤓
          </button>
        </div>
      </div>

      {/* Fresh Validation Pairs Table */}
      <div style={{ background: '#141516', borderRadius: '0.75rem', padding: '1.25rem', border: '1px solid #191a1b' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, fontSize: '1rem', color: '#f7f8f8', fontWeight: 600 }}>
            Fresh Validation Executions ({validation.pairs.length} Pairs)
          </h3>
          {validation.verified_savings_pct != null && (
            <div style={{ fontSize: '0.85rem', color: '#10b981', fontWeight: 600 }}>
              Observed Energy Savings: {validation.verified_savings_pct.toFixed(1)}%
            </div>
          )}
        </div>

        {validation.pairs.length === 0 ? (
          <div style={{ padding: '1rem 0.5rem', fontSize: '0.85rem', color: '#8a8f98' }}>
            No validation pairs recorded yet. Run fresh validation to compare baseline vs selected.
          </div>
        ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', color: '#8a8f98' }}>
                <th style={{ padding: '0.5rem' }}>Pair</th>
                <th style={{ padding: '0.5rem' }}>Baseline (Stock)</th>
                <th style={{ padding: '0.5rem' }}>Selected Candidate</th>
                <th style={{ padding: '0.5rem' }}>Runtime Delta</th>
                <th style={{ padding: '0.5rem' }}>Package Energy Delta</th>
                <th style={{ padding: '0.5rem' }}>Correctness</th>
              </tr>
            </thead>
            <tbody>
              {validation.pairs.map((p) => {
                const eBase = p.baseline_run.package_energy_j;
                const eSel = p.selected_run.package_energy_j;
                const eSavings = eBase != null && eSel != null && eBase > 0
                  ? Math.round(100 * (1 - eSel / eBase))
                  : null;
                const tDelta = (p.selected_run.runtime_s - p.baseline_run.runtime_s).toFixed(1);

                return (
                  <tr key={p.pair_index} style={{ borderBottom: '1px solid #191a1b' }}>
                    <td style={{ padding: '0.6rem 0.5rem', fontWeight: 600 }}>Pair #{p.pair_index}</td>
                    <td style={{ padding: '0.6rem 0.5rem' }}>
                      {p.baseline_run.runtime_s.toFixed(1)}s · {eBase != null ? `${eBase.toFixed(1)} J` : 'energy N/A'}
                    </td>
                    <td style={{ padding: '0.6rem 0.5rem', color: '#10b981', fontWeight: 600 }}>
                      {p.selected_run.runtime_s.toFixed(1)}s · {eSel != null ? `${eSel.toFixed(1)} J` : 'energy N/A'}
                    </td>
                    <td style={{ padding: '0.6rem 0.5rem' }}>+{tDelta}s</td>
                    <td style={{ padding: '0.6rem 0.5rem', color: eSavings != null ? '#10b981' : '#8a8f98', fontWeight: 700 }}>
                      {eSavings != null ? `-${eSavings}%` : 'N/A'}
                    </td>
                    <td style={{ padding: '0.6rem 0.5rem' }}>
                      {p.both_succeeded ? (
                        <span style={{ color: '#10b981', fontWeight: 600 }}>✓ Verified output</span>
                      ) : (
                        <span style={{ color: '#f4586e', fontWeight: 600 }}>✗ Failed run retained</span>
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

      {/* Explanation Card */}
      <div style={{ background: '#141516', borderRadius: '0.75rem', padding: '1.25rem', border: '1px solid #191a1b' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
          <h3 style={{ margin: 0, fontSize: '1rem', color: '#f7f8f8', fontWeight: 600 }}>
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
                  border: `1px solid ${provider === p ? '#7170ff' : 'rgba(255,255,255,0.08)'}`,
                  backgroundColor: provider === p ? 'rgba(113,112,255,0.14)33' : '#191a1b',
                  color: provider === p ? '#828fff' : '#8a8f98',
                  cursor: isExplaining ? 'wait' : 'pointer',
                  textTransform: 'capitalize',
                }}
              >
                {p.replace('_', ' ')}
              </button>
            ))}
          </div>
        </div>

        {explanation && (
          <div style={{ background: '#191a1b', borderRadius: '0.5rem', padding: '1rem', border: '1px solid rgba(255,255,255,0.08)' }}>
            {explanation.fallback && (
              <div style={{ fontSize: '0.75rem', color: '#fcd34d', marginBottom: '0.5rem' }}>
                ⚠ Requested provider unavailable — degraded to deterministic Basic templates (guaranteed default).
              </div>
            )}
            <div style={{ fontSize: '0.9rem', color: '#f7f8f8', lineHeight: 1.5, marginBottom: '0.75rem', whiteSpace: 'pre-line' }}>
              {explanation.text}
            </div>
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '0.6rem' }}>
              <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#8a8f98', marginBottom: '0.3rem' }}>
                Grounding Facts (Strictly Verified):
              </div>
              <ul style={{ margin: 0, paddingLeft: '1.2rem', fontSize: '0.78rem', color: '#d0d6e0', display: 'flex', flexDirection: 'column', gap: '0.2rem' }}>
                {explanation.grounding_facts.map((fact, idx) => (
                  <li key={idx}>{fact}</li>
                ))}
              </ul>
            </div>
          </div>
        )}
      </div>

      {/* Restoration Card — status always from the persisted experiment record, never guessed */}
      {(() => {
        const label = RESTORATION_LABELS[experiment.restoration_status] ?? RESTORATION_LABELS.not_required;
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
              <div style={{ fontSize: '0.75rem', color: '#a7f3d0' }}>
                {experiment.restoration_status === 'restored'
                  ? 'Stock frequencies, power limits, and boost configurations restored to initial state.'
                  : experiment.restoration_status === 'recovery_required'
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
          color: '#8a8f98',
          borderTop: '1px solid #191a1b',
        }}
      >
        CPU-package energy, not whole-system electricity. Best among measured configurations; future runtimes may vary.
      </footer>
    </div>
  );
};
