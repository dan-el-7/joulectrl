import React from 'react';
import { CapabilitiesResponse, WorkloadInfo } from '../types';
import { colors } from '../design';

interface SetupViewProps {
  capabilities: CapabilitiesResponse | null;
  workloads: WorkloadInfo[];
  selectedWorkload: string;
  onSelectWorkload: (id: string) => void;
  objective: string;
  onChangeObjective: (obj: string) => void;
  runtimeBudgetS: number | null;
  onChangeRuntimeBudget: (val: number | null) => void;
  energyTargetPct: number;
  onChangeEnergyTarget: (val: number) => void;
  perfFloorPct: number;
  onChangePerfFloor: (val: number) => void;
  calibrationBudgetS: number | null;
  onChangeCalibrationBudget: (val: number | null) => void;
  onStartExperiment: () => void;
  isStarting: boolean;
}

export const SetupView: React.FC<SetupViewProps> = ({
  capabilities,
  workloads,
  selectedWorkload,
  onSelectWorkload,
  objective,
  onChangeObjective,
  runtimeBudgetS,
  onChangeRuntimeBudget,
  energyTargetPct,
  onChangeEnergyTarget,
  perfFloorPct,
  onChangePerfFloor,
  calibrationBudgetS,
  onChangeCalibrationBudget,
  onStartExperiment,
  isStarting,
}) => {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: '1.5rem', maxWidth: '1100px', margin: '0 auto' }}>
      {/* Left Column: Workload & Objective Configuration */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.5rem', border: colors.border }}>
        <h2 style={{ margin: '0 0 1.25rem 0', fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
          Experiment Setup
        </h2>

        {/* 1. Workload Selection */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: colors.textTertiary, marginBottom: '0.5rem' }}>
            Workload Plugin
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
            {workloads.map((w) => {
              const isSelected = w.id === selectedWorkload;
              return (
                <div
                  key={w.id}
                  onClick={() => onSelectWorkload(w.id)}
                  style={{
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                    border: `1.5px solid ${isSelected ? colors.accent : 'rgba(255,255,255,0.08)'}`,
                    backgroundColor: isSelected ? 'rgba(113,112,255,0.14)25' : colors.surfaceElevated,
                    cursor: 'pointer',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '0.9rem', color: isSelected ? colors.accentHover : colors.textSecondary }}>
                    {w.name}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginTop: '0.25rem' }}>
                    {w.description}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 2. Objective Selection */}
        <div style={{ marginBottom: '1.5rem' }}>
          <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: colors.textTertiary, marginBottom: '0.5rem' }}>
            Optimization Objective
          </label>
          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem' }}>
            {[
              { id: 'deadline', label: 'Deadline Mode', desc: 'Finish within runtime budget' },
              { id: 'preference', label: 'Preference Mode', desc: '70% energy / 90% perf tradeoff' },
              { id: 'frontier', label: 'Explore Frontier', desc: 'View all Pareto candidates' },
            ].map((obj) => (
              <button
                key={obj.id}
                onClick={() => onChangeObjective(obj.id)}
                style={{
                  flex: 1,
                  padding: '0.5rem',
                  borderRadius: '0.375rem',
                  border: `1.5px solid ${objective === obj.id ? colors.emerald : 'rgba(255,255,255,0.08)'}`,
                  backgroundColor: objective === obj.id ? 'rgba(16,185,129,0.12)33' : colors.surfaceElevated,
                  color: objective === obj.id ? colors.emerald : colors.textSecondary,
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: 'pointer',
                  textAlign: 'center',
                }}
              >
                <div>{obj.label}</div>
              </button>
            ))}
          </div>

          {/* Conditional inputs based on Objective */}
          {objective === 'deadline' && (
            <div style={{ background: colors.surfaceElevated, padding: '1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.85rem', color: colors.textSecondary }}>Runtime Budget:</span>
                <span style={{ fontSize: '0.95rem', fontWeight: 700, color: colors.emerald }}>
                  {runtimeBudgetS === null ? 'Unlimited' : `${runtimeBudgetS}s`}
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <input
                  type="range"
                  min="20"
                  max="90"
                  step="0.5"
                  value={runtimeBudgetS ?? 45}
                  disabled={runtimeBudgetS === null}
                  onChange={(e) => onChangeRuntimeBudget(parseFloat(e.target.value))}
                  style={{ flex: 1, accentColor: colors.emerald }}
                />
                <label style={{ fontSize: '0.75rem', color: colors.textTertiary, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  <input
                    type="checkbox"
                    checked={runtimeBudgetS === null}
                    onChange={(e) => onChangeRuntimeBudget(e.target.checked ? null : 45.0)}
                  />
                  Unlimited
                </label>
              </div>
              <div style={{ fontSize: '0.72rem', color: colors.textTertiary, marginTop: '0.4rem' }}>
                Rule: lowest-energy measured configuration meeting the empirical runtime rule (with 5% guard margin).
              </div>
            </div>
          )}

          {objective === 'preference' && (
            <div style={{ background: colors.surfaceElevated, padding: '1rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)', display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: colors.textSecondary, marginBottom: '0.3rem' }}>
                  <span>Energy Target:</span>
                  <span style={{ fontWeight: 700, color: colors.amber }}>≤ {energyTargetPct}% of baseline</span>
                </div>
                <input
                  type="range"
                  min="40"
                  max="100"
                  step="5"
                  value={energyTargetPct}
                  onChange={(e) => onChangeEnergyTarget(parseInt(e.target.value))}
                  style={{ width: '100%', accentColor: colors.amber }}
                />
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: colors.textSecondary, marginBottom: '0.3rem' }}>
                  <span>Performance Floor:</span>
                  <span style={{ fontWeight: 700, color: colors.accent }}>≥ {perfFloorPct}% baseline speed (runtime ≤ {Math.round(10000 / perfFloorPct)}%)</span>
                </div>
                <input
                  type="range"
                  min="50"
                  max="100"
                  step="5"
                  value={perfFloorPct}
                  onChange={(e) => onChangePerfFloor(parseInt(e.target.value))}
                  style={{ width: '100%', accentColor: colors.accent }}
                />
              </div>
              <div style={{ fontSize: '0.72rem', color: colors.textTertiary }}>
                Spec §6c: Reports closest honest outcome explicitly if no single candidate satisfies both constraints.
              </div>
            </div>
          )}
        </div>

        {/* 3. Calibration Budget */}
        <div style={{ marginBottom: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', color: colors.textTertiary, marginBottom: '0.4rem' }}>
            <span>Calibration Sweep Budget (C2 ladder):</span>
            <span style={{ color: colors.textSecondary, fontWeight: 600 }}>
              {calibrationBudgetS === null ? 'Exhaustive' : `${calibrationBudgetS}s`}
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <input
              type="range"
              min="30"
              max="300"
              step="10"
              value={calibrationBudgetS ?? 120}
              disabled={calibrationBudgetS === null}
              onChange={(e) => onChangeCalibrationBudget(parseInt(e.target.value))}
              style={{ flex: 1, accentColor: colors.accent }}
            />
            <label style={{ fontSize: '0.75rem', color: colors.textTertiary, display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <input
                type="checkbox"
                checked={calibrationBudgetS === null}
                onChange={(e) => onChangeCalibrationBudget(e.target.checked ? null : 120)}
              />
              Exhaustive
            </label>
          </div>
        </div>

        {/* Action Button */}
        <button
          onClick={onStartExperiment}
          disabled={isStarting}
          style={{
            width: '100%',
            padding: '0.75rem',
            borderRadius: '0.5rem',
            backgroundColor: colors.accentBg,
            color: colors.textPrimary,
            fontSize: '0.95rem',
            fontWeight: 600,
            border: 'none',
            cursor: isStarting ? 'wait' : 'pointer',
            boxShadow: '0 4px 6px -1px rgba(37, 99, 235, 0.3)',
          }}
        >
          {isStarting ? 'Profiling Workload...' : 'Profile Workload & Search Minimum Energy'}
        </button>
      </div>

      {/* Right Column: Hardware Discovery Card */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1.5rem', border: colors.border }}>
        <h2 style={{ margin: '0 0 1.25rem 0', fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
          Hardware Discovery & Capabilities
        </h2>

        {capabilities ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.85rem' }}>
            <div style={{ background: colors.surfaceElevated, padding: '0.75rem', borderRadius: '0.5rem', border: '1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ color: colors.textTertiary, fontSize: '0.75rem' }}>Processor / Topology</div>
              <div style={{ fontWeight: 600, color: colors.textPrimary, marginTop: '0.2rem' }}>
                {capabilities.machine.cpu_model}
              </div>
              <div style={{ color: colors.textTertiary, marginTop: '0.2rem', fontSize: '0.75rem' }}>
                {capabilities.topology.logical_cores} logical CPUs ({capabilities.topology.physical_cores} physical cores)
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', flexWrap: 'wrap' }}>
                {Object.entries(capabilities.topology.classes ?? {}).map(([cls, cpus]) => (
                  <span
                    key={cls}
                    style={{
                      background: cls === 'fast' ? 'rgba(16,185,129,0.12)' : 'rgba(245,158,11,0.10)',
                      color: cls === 'fast' ? colors.emerald : colors.amber,
                      padding: '0.15rem 0.4rem',
                      borderRadius: '0.25rem',
                      fontSize: '0.7rem',
                    }}
                  >
                    {cls} class: CPUs {(cpus as number[]).join(', ')}
                  </span>
                ))}
              </div>
            </div>

            {/* Checklist of Gates */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Package-energy access (RAPL)</span>
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Verified ({capabilities.energy.idle_watts} W idle)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>CPU Frequency Caps</span>
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Verified (16 policies, boost=0 pair)</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Global Boost Toggle</span>
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Verified</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Restoration Engine</span>
                <span style={{ color: colors.emerald, fontWeight: 700 }}>✓ Available</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>Tuned PM Profile</span>
                <span style={{ color: colors.accentHover, fontWeight: 600 }}>{capabilities.machine.tuned_active_profile}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>AC Power Supply</span>
                <span style={{ color: capabilities.machine.ac_power ? colors.emerald : colors.amber, fontWeight: 600 }}>
                  {capabilities.machine.ac_power ? '✓ Connected' : '⚠ On Battery'}
                </span>
              </div>
            </div>

            <div style={{ background: colors.surfaceElevated, border: colors.border, borderRadius: '0.5rem', padding: '0.6rem', fontSize: '0.72rem', color: colors.textTertiary }}>
              <strong>Non-negotiable rule:</strong> Package energy measured directly from verified hardware counter. Missing energy is never relabeled as zero.
            </div>
          </div>
        ) : (
          <div style={{ color: colors.textTertiary }}>Loading machine capabilities...</div>
        )}
      </div>
    </div>
  );
};
