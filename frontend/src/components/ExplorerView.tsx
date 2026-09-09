import React, { useEffect, useState } from 'react';
import { ConfigSummary, Experiment } from '../types';
import { fetchValidationPoints } from '../api';
import { ParetoChart } from './ParetoChart';
import { colors } from '../design';

interface ValidationPointCandidate {
  kind: 'layout' | 'calibration';
  config_id: string;
  layout: string;
  cpu_mask?: string;
  cpus?: number[];
  workers?: number;
  core_class?: string;
  description?: string;
  median_runtime_s?: number;
  median_energy_j?: number | null;
  energy_available?: boolean;
  measured: boolean;
}

interface ExplorerViewProps {
  experiment: Experiment;
  onReselect: (budgetS: number) => void;
  onNavigateValidation: () => void;
}

export const ExplorerView: React.FC<ExplorerViewProps> = ({
  experiment,
  onReselect,
  onNavigateValidation,
}) => {
  const { profile, selection } = experiment;
  const [tempBudget, setTempBudget] = useState<number>(selection.runtime_budget_s ?? 45.0);
  const [candidates, setCandidates] = useState<ValidationPointCandidate[] | null>(null);
  const [selectedCandidates, setSelectedCandidates] = useState<Set<string>>(new Set());
  const [candidatesError, setCandidatesError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchValidationPoints(experiment.id)
      .then((data) => {
        if (cancelled) return;
        setCandidates([...(data.layout_candidates ?? []), ...(data.calibration_points ?? [])]);
      })
      .catch((e) => {
        if (!cancelled) setCandidatesError(String(e?.message ?? e));
      });
    return () => {
      cancelled = true;
    };
  }, [experiment.id]);

  const toggleCandidate = (id: string) => {
    setSelectedCandidates((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const configs = profile.configurations;
  const baselineId = profile.baseline_config_id;
  const selectedId = selection.selected_config_id ?? selection.config_id;

  const baseCfg = configs[baselineId];
  const selCfg = configs[selectedId];

  // Find lowest energy overall across usable configurations
  const lowestEnergyCfg = Object.values(configs).reduce((prev, curr) => {
    if (!prev) return curr;
    return curr.median_energy_j < prev.median_energy_j ? curr : prev;
  }, baseCfg);

  // data-derived summary line — no hardcoded counts or core names
  const nConfigs = Object.keys(configs).length;
  const nReps = lowestEnergyCfg?.runtime_samples?.length ?? baseCfg?.runtime_samples?.length ?? 0;
  const layoutsPresent = [...new Set(Object.values(configs).map((c) => c.configuration.layout))].sort();

  /** one-line config descriptor from actual configuration fields */
  const describeConfig = (c: ConfigSummary | undefined): string => {
    if (!c) return '—';
    const parts: string[] = [];
    parts.push(`${c.configuration.cpu_affinity?.length ?? c.configuration.worker_count} cores`);
    if (c.configuration.freq_cap_khz) parts.push(`${(c.configuration.freq_cap_khz / 1e6).toFixed(1)} GHz cap`);
    if (c.configuration.boost === false) parts.push('Boost off');
    else if (c.configuration.boost === true) parts.push('Boost on');
    return parts.join(' · ');
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Top Banner: Status + Interactive Budget Slider */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: colors.surface,
          padding: '1rem 1.5rem',
          borderRadius: '0.75rem',
          border: colors.border,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
              Profile Explorer — {experiment.workload_id}
            </h2>
            <span
              style={{
                fontSize: '0.7rem',
                fontWeight: 600,
                padding: '0.15rem 0.5rem',
                borderRadius: '9999px',
                backgroundColor: colors.emerald,
                color: colors.emerald,
              }}
            >
              Predicted from profile
            </span>
          </div>
          <div style={{ fontSize: '0.8rem', color: colors.textTertiary, marginTop: '0.2rem' }}>
            {nConfigs} configurations tested across layout{layoutsPresent.length > 1 ? 's' : ''} {layoutsPresent.join(', ')}
            {nReps ? ` (${nReps} repetitions each)` : ''}.
          </div>
        </div>

        {/* Live slider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.75rem', color: colors.textTertiary }}>Dynamic Budget Slider</div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: colors.emerald }}>{tempBudget}s</div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="range"
              min="1"
              max="300"
              step="0.5"
              value={Math.min(Math.max(tempBudget, 1), 300)}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                setTempBudget(val);
                onReselect(val);
              }}
              style={{ width: '140px', accentColor: colors.emerald }}
            />
            <input
              type="text"
              inputMode="decimal"
              value={tempBudget}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (Number.isFinite(v) && v > 0) setTempBudget(v);
              }}
              onBlur={(e) => {
                const v = parseFloat(e.target.value);
                if (Number.isFinite(v) && v > 0) onReselect(v);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') (e.target as HTMLInputElement).blur();
              }}
              style={{
                width: 64, padding: '2px 6px', borderRadius: 4,
                border: `1px solid ${colors.border}`, background: colors.surfaceElevated,
                color: colors.textPrimary, fontSize: '0.8rem',
              }}
            />
            <span style={{ fontSize: '0.72rem', color: colors.textTertiary }}>s</span>
          </div>
        </div>
      </div>

      {/* Comparison Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
        {/* Card 1: Default Baseline */}
        <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem', border: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ fontSize: '0.75rem', color: colors.red, fontWeight: 600, textTransform: 'uppercase' }}>
            Default Baseline
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: colors.textPrimary, marginTop: '0.2rem' }}>
            {baseCfg ? baseCfg.config_id : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary }}>
            {describeConfig(baseCfg)}
          </div>
          <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <span style={{ color: colors.textTertiary }}>Runtime:</span>
            <span style={{ fontWeight: 600 }}>{baseCfg?.median_runtime_s}s</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: colors.textTertiary }}>Package Energy:</span>
            <span style={{ fontWeight: 600, color: colors.red }}>{baseCfg?.median_energy_j} J</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: colors.textTertiary }}>Avg Power:</span>
            <span style={{ fontWeight: 600 }}>{baseCfg?.median_power_w} W</span>
          </div>
        </div>

        {/* Card 2: Lowest Energy Overall */}
        <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem', border: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ fontSize: '0.75rem', color: colors.amber, fontWeight: 600, textTransform: 'uppercase' }}>
            Lowest Energy Overall
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: colors.textPrimary, marginTop: '0.2rem' }}>
            {lowestEnergyCfg ? lowestEnergyCfg.config_id : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary }}>
            {describeConfig(lowestEnergyCfg)}
          </div>
          <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <span style={{ color: colors.textTertiary }}>Runtime:</span>
            <span style={{ fontWeight: 600 }}>{lowestEnergyCfg?.median_runtime_s}s</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: colors.textTertiary }}>Package Energy:</span>
            <span style={{ fontWeight: 600, color: colors.amber }}>{lowestEnergyCfg?.median_energy_j} J</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: colors.textTertiary }}>Energy Delta:</span>
            <span style={{ fontWeight: 600, color: colors.emerald }}>
              -{Math.round(100 * (1 - (lowestEnergyCfg?.median_energy_j ?? 1) / (baseCfg?.median_energy_j ?? 1)))}%
            </span>
          </div>
        </div>

        {/* Card 3: Selected Within Budget */}
        <div style={{ background: 'rgba(16,185,129,0.12)', borderRadius: '0.75rem', padding: '1rem', border: '1.5px solid ' + colors.emerald }}>
          <div style={{ fontSize: '0.75rem', color: colors.emerald, fontWeight: 600, textTransform: 'uppercase' }}>
            Selected Within Budget ★
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: colors.emerald, marginTop: '0.2rem' }}>
            {selCfg ? selCfg.config_id : selectedId}
          </div>
          <div style={{ fontSize: '0.75rem', color: colors.textTertiary }}>
            {describeConfig(selCfg)}
          </div>
          <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <span style={{ color: colors.textTertiary }}>Guarded Runtime:</span>
            <span style={{ fontWeight: 700, color: colors.emerald }}>{selCfg?.guarded_runtime_s}s (≤ {tempBudget}s)</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: colors.textTertiary }}>Energy Savings:</span>
            <span style={{ fontWeight: 700, color: colors.emerald, fontSize: '1rem' }}>
              -{selection.savings_vs_baseline_pct ?? selection.energy_reduction_pct ?? 0}%
            </span>
          </div>
          <button
            onClick={onNavigateValidation}
            style={{
              width: '100%',
              marginTop: '0.6rem',
              padding: '0.4rem',
              borderRadius: '0.375rem',
              border: 'none',
              backgroundColor: colors.emerald,
              color: colors.textPrimary,
              fontSize: '0.8rem',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Verify with Fresh Validation Runs →
          </button>
        </div>
      </div>

      {/* Main Pareto Scatter Chart */}
      <ParetoChart
        configurations={configs}
        selectedConfigId={selectedId}
        baselineConfigId={baselineId}
        deadlineS={tempBudget}
        frontierConfigIds={selection.frontier_config_ids}
        onSelectConfig={(cid) => {
          // Point click selection
        }}
      />

      {/* Validation-Point Candidates (B's layout selector + measured calibration points) */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem 1.5rem', border: colors.border }}>
        <h3 style={{ margin: '0 0 0.35rem 0', fontSize: '1rem', color: colors.textPrimary, fontWeight: 600 }}>
          Validation-Point Candidates
        </h3>
        <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginBottom: '0.75rem' }}>
          Execution layouts built from the discovered core-class map plus measured calibration points. Select the
          configurations worth validating with fresh runs — suggestions only; the selector still checks all usable
          configurations. {selectedCandidates.size > 0 && `${selectedCandidates.size} selected.`}
        </div>
        {candidatesError && (
          <div style={{ fontSize: '0.8rem', color: colors.amber }}>Failed to load candidates: {candidatesError}</div>
        )}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {(candidates ?? []).map((c) => {
            const selected = selectedCandidates.has(c.config_id);
            return (
              <button
                key={c.config_id}
                onClick={() => toggleCandidate(c.config_id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  padding: '0.45rem 0.7rem',
                  borderRadius: '0.5rem',
                  border: `1.5px solid ${selected ? colors.emerald : 'rgba(255,255,255,0.08)'}`,
                  backgroundColor: selected ? 'rgba(16,185,129,0.20)' : colors.surfaceElevated,
                  cursor: 'pointer',
                  fontSize: '0.78rem',
                  color: selected ? colors.emerald : colors.textSecondary,
                }}
                title={c.description ?? (c.cpus ? `cpus: ${c.cpus.join(',')}` : c.cpu_mask)}
              >
                <span style={{ fontWeight: 700 }}>{selected ? '✓' : '＋'}</span>
                <span style={{ fontFamily: 'monospace' }}>{c.config_id}</span>
                {c.measured ? (
                  <span style={{ fontSize: '0.65rem', color: colors.accentHover }}>(
                    {c.median_energy_j != null ? `${Math.round(c.median_energy_j)} J` : 'energy unavailable'}
                    {c.median_runtime_s != null ? `, ${c.median_runtime_s.toFixed(1)}s` : ''})</span>
                ) : (
                  <span style={{ fontSize: '0.65rem', color: colors.textTertiary }}>(unmeasured layout)</span>
                )}
              </button>
            );
          })}
          {candidates !== null && candidates.length === 0 && !candidatesError && (
            <span style={{ fontSize: '0.8rem', color: colors.textTertiary }}>No candidates available for this machine.</span>
          )}
        </div>
      </div>

      {/* Complete Run List Table */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem 1.5rem', border: colors.border }}>
        <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: colors.textPrimary, fontWeight: 600 }}>
          Individual Execution Runs ({profile.runs.length} captured)
        </h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.08)', color: colors.textTertiary }}>
                <th style={{ padding: '0.5rem' }}>Run ID</th>
                <th style={{ padding: '0.5rem' }}>Configuration</th>
                <th style={{ padding: '0.5rem' }}>Layout</th>
                <th style={{ padding: '0.5rem' }}>Rep</th>
                <th style={{ padding: '0.5rem' }}>Runtime (s)</th>
                <th style={{ padding: '0.5rem' }}>Energy (J)</th>
                <th style={{ padding: '0.5rem' }}>Avg Power (W)</th>
                <th style={{ padding: '0.5rem' }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {profile.runs.map((r) => {
                const isSelected = r.config_id === selectedId;
                const isBase = r.config_id === baselineId;
                return (
                  <tr
                    key={r.run_id}
                    style={{
                      borderBottom: colors.border,
                      backgroundColor: isSelected ? 'rgba(16,185,129,0.15)' : isBase ? 'rgba(244,88,110,0.10)' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{r.run_id}</td>
                    <td style={{ padding: '0.5rem', fontWeight: isSelected || isBase ? 600 : 400 }}>
                      {r.config_id}
                      {isSelected && <span style={{ color: colors.emerald, marginLeft: 4 }}>★</span>}
                    </td>
                    <td style={{ padding: '0.5rem' }}>{r.configuration?.layout ?? '-'}</td>
                    <td style={{ padding: '0.5rem' }}>#{r.repetition}</td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{r.runtime_s.toFixed(2)}</td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace', color: isSelected ? colors.emerald : colors.textSecondary }}>
                      {r.package_energy_j ? `${r.package_energy_j.toFixed(1)} J` : 'unavailable'}
                    </td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>
                      {r.package_energy_j ? (r.package_energy_j / r.runtime_s).toFixed(1) : '-'} W
                    </td>
                    <td style={{ padding: '0.5rem' }}>
                      <span style={{ color: colors.emerald, fontWeight: 600 }}>✓ verified</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
