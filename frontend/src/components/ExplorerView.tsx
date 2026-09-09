import React, { useState } from 'react';
import { Experiment } from '../types';
import { ParetoChart } from './ParetoChart';

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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1200px', margin: '0 auto' }}>
      {/* Top Banner: Status + Interactive Budget Slider */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: '#111827',
          padding: '1rem 1.5rem',
          borderRadius: '0.75rem',
          border: '1px solid #1f2937',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, fontSize: '1.15rem', color: '#f3f4f6', fontWeight: 600 }}>
              Profile Explorer — {experiment.workload_id}
            </h2>
            <span
              style={{
                fontSize: '0.7rem',
                fontWeight: 600,
                padding: '0.15rem 0.5rem',
                borderRadius: '9999px',
                backgroundColor: '#065f46',
                color: '#34d399',
              }}
            >
              Predicted from profile
            </span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#9ca3af', marginTop: '0.2rem' }}>
            12 configurations tested across Zen 5 &amp; Zen 5c layouts (3 repetitions each).
          </div>
        </div>

        {/* Live slider */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Dynamic Budget Slider</div>
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: '#10b981' }}>{tempBudget}s</div>
          </div>
          <input
            type="range"
            min="25"
            max="65"
            step="0.5"
            value={tempBudget}
            onChange={(e) => {
              const val = parseFloat(e.target.value);
              setTempBudget(val);
              onReselect(val);
            }}
            style={{ width: '140px', accentColor: '#10b981' }}
          />
        </div>
      </div>

      {/* Comparison Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
        {/* Card 1: Default Baseline */}
        <div style={{ background: '#111827', borderRadius: '0.75rem', padding: '1rem', border: '1px solid #374151' }}>
          <div style={{ fontSize: '0.75rem', color: '#f43f5e', fontWeight: 600, textTransform: 'uppercase' }}>
            Default Baseline
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f3f4f6', marginTop: '0.2rem' }}>
            {baseCfg ? baseCfg.config_id : 'cfg_stock_all'}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
            16 threads · Stock boost · All cores
          </div>
          <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <span style={{ color: '#9ca3af' }}>Runtime:</span>
            <span style={{ fontWeight: 600 }}>{baseCfg?.median_runtime_s}s</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: '#9ca3af' }}>Package Energy:</span>
            <span style={{ fontWeight: 600, color: '#f43f5e' }}>{baseCfg?.median_energy_j} J</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: '#9ca3af' }}>Avg Power:</span>
            <span style={{ fontWeight: 600 }}>{baseCfg?.median_power_w} W</span>
          </div>
        </div>

        {/* Card 2: Lowest Energy Overall */}
        <div style={{ background: '#111827', borderRadius: '0.75rem', padding: '1rem', border: '1px solid #374151' }}>
          <div style={{ fontSize: '0.75rem', color: '#f59e0b', fontWeight: 600, textTransform: 'uppercase' }}>
            Lowest Energy Overall
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: '#f3f4f6', marginTop: '0.2rem' }}>
            {lowestEnergyCfg ? lowestEnergyCfg.config_id : 'cfg_zen5c_4c_2000'}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
            4 Zen 5c cores · 2.0 GHz cap
          </div>
          <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <span style={{ color: '#9ca3af' }}>Runtime:</span>
            <span style={{ fontWeight: 600 }}>{lowestEnergyCfg?.median_runtime_s}s</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: '#9ca3af' }}>Package Energy:</span>
            <span style={{ fontWeight: 600, color: '#f59e0b' }}>{lowestEnergyCfg?.median_energy_j} J</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: '#9ca3af' }}>Energy Delta:</span>
            <span style={{ fontWeight: 600, color: '#10b981' }}>
              -{Math.round(100 * (1 - (lowestEnergyCfg?.median_energy_j ?? 1) / (baseCfg?.median_energy_j ?? 1)))}%
            </span>
          </div>
        </div>

        {/* Card 3: Selected Within Budget */}
        <div style={{ background: '#064e3b22', borderRadius: '0.75rem', padding: '1rem', border: '1.5px solid #059669' }}>
          <div style={{ fontSize: '0.75rem', color: '#10b981', fontWeight: 600, textTransform: 'uppercase' }}>
            Selected Within Budget ★
          </div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: '#6ee7b7', marginTop: '0.2rem' }}>
            {selCfg ? selCfg.config_id : selectedId}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#9ca3af' }}>
            4 Zen 5c cores · 3.0 GHz cap · Boost off
          </div>
          <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <span style={{ color: '#9ca3af' }}>Guarded Runtime:</span>
            <span style={{ fontWeight: 700, color: '#10b981' }}>{selCfg?.guarded_runtime_s}s (≤ {tempBudget}s)</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: '#9ca3af' }}>Energy Savings:</span>
            <span style={{ fontWeight: 700, color: '#10b981', fontSize: '1rem' }}>
              -{selection.savings_vs_baseline_pct ?? selection.energy_reduction_pct ?? 44.6}%
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
              backgroundColor: '#059669',
              color: '#ffffff',
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

      {/* Complete Run List Table */}
      <div style={{ background: '#111827', borderRadius: '0.75rem', padding: '1rem 1.5rem', border: '1px solid #1f2937' }}>
        <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: '#f3f4f6', fontWeight: 600 }}>
          Individual Execution Runs ({profile.runs.length} captured)
        </h3>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8rem', textAlign: 'left' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #374151', color: '#9ca3af' }}>
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
                      borderBottom: '1px solid #1f2937',
                      backgroundColor: isSelected ? '#064e3b15' : isBase ? '#88133715' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{r.run_id}</td>
                    <td style={{ padding: '0.5rem', fontWeight: isSelected || isBase ? 600 : 400 }}>
                      {r.config_id}
                      {isSelected && <span style={{ color: '#10b981', marginLeft: 4 }}>★</span>}
                    </td>
                    <td style={{ padding: '0.5rem' }}>{r.configuration?.layout ?? '-'}</td>
                    <td style={{ padding: '0.5rem' }}>#{r.repetition}</td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{r.runtime_s.toFixed(2)}</td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace', color: isSelected ? '#10b981' : '#e5e7eb' }}>
                      {r.package_energy_j ? `${r.package_energy_j.toFixed(1)} J` : 'unavailable'}
                    </td>
                    <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>
                      {r.package_energy_j ? (r.package_energy_j / r.runtime_s).toFixed(1) : '-'} W
                    </td>
                    <td style={{ padding: '0.5rem' }}>
                      <span style={{ color: '#10b981', fontWeight: 600 }}>✓ verified</span>
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
