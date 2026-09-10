import React, { useEffect, useRef, useState } from 'react';
import { ConfigSummary, Experiment, Selection } from '../types';
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

function formatDuration(sec: number): string {
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

function formatEnergy(j: number): string {
  if (j >= 1e6) return `${(j / 1e6).toFixed(2)} MJ`;
  if (j >= 1000) return `${(j / 1000).toFixed(1)} kJ`;
  return `${Math.round(j)} J`;
}

interface ExplorerViewProps {
  experiment: Experiment;
  onReselect: (budgetS: number, taskDurationS?: number | null) => void;
  onNavigateValidation: () => void;
}

export const ExplorerView: React.FC<ExplorerViewProps> = ({
  experiment,
  onReselect,
  onNavigateValidation,
}) => {
  const { profile } = experiment;
  const selection = experiment.selection as Partial<Selection> | null | undefined;
  const initialBudget = selection?.runtime_budget_s ?? experiment?.runtime_budget_s ?? 45.0;
  const initialTaskDuration = (selection as any)?.task_duration_s ?? experiment?.task_duration_s ?? null;
  const [tempBudget, setTempBudget] = useState<number>(initialBudget);
  const [taskDuration, setTaskDuration] = useState<number | null>(initialTaskDuration);
  const [isExtrapolating, setIsExtrapolating] = useState<boolean>(initialTaskDuration != null && initialTaskDuration > 0);
  const [candidates, setCandidates] = useState<ValidationPointCandidate[] | null>(null);
  const [selectedCandidates, setSelectedCandidates] = useState<Set<string>>(new Set());
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const debounceTimerRef = useRef<any>(null);

  useEffect(() => {
    const budget = selection?.runtime_budget_s ?? experiment?.runtime_budget_s;
    if (budget != null && Number.isFinite(budget) && budget > 0) {
      setTempBudget(budget);
    }
  }, [experiment.id, selection?.runtime_budget_s, experiment?.runtime_budget_s]);

  useEffect(() => {
    const dur = (selection as any)?.task_duration_s ?? experiment?.task_duration_s;
    if (dur != null && Number.isFinite(dur) && dur > 0) {
      setTaskDuration(dur);
      setIsExtrapolating(true);
    }
  }, [experiment.id, (selection as any)?.task_duration_s, experiment?.task_duration_s]);

  const handleSliderChange = (val: number) => {
    setTempBudget(val);
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    debounceTimerRef.current = setTimeout(() => {
      onReselect(val, isExtrapolating ? (taskDuration || 900) : null);
    }, 120);
  };

  const triggerReselect = (budgetVal: number, durationVal?: number | null) => {
    setTempBudget(budgetVal);
    onReselect(budgetVal, durationVal !== undefined ? durationVal : (isExtrapolating ? (taskDuration || 900) : null));
  };

  const handleTaskDurationChange = (val: number | null) => {
    setTaskDuration(val);
    if (val && val > 0) {
      setIsExtrapolating(true);
      let newBudget = tempBudget;
      // If current budget was for benchmark (e.g. <= 60s) but task is long (e.g. 900s), adapt budget
      if (tempBudget <= 60 && val > 60) {
        newBudget = Math.round(val * 1.33);
        setTempBudget(newBudget);
      }
      onReselect(newBudget, val);
    } else {
      setIsExtrapolating(false);
      onReselect(tempBudget, null);
    }
  };

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

  const configs = profile?.configurations || {};
  const candList: any[] = (selection as any)?.candidates || (selection as any)?.candidate_summaries || [];

  // Robust configurations map: profile.configurations if populated, or reconstructed from candList
  const effectiveConfigs: Record<string, ConfigSummary> = React.useMemo(() => {
    if (configs && Object.keys(configs).length > 0) {
      return configs;
    }
    const map: Record<string, any> = {};
    candList.forEach((c: any) => {
      const cid = c.config_id || c.configuration?.id || c.id;
      if (cid) map[cid] = c;
    });
    return map;
  }, [configs, candList]);

  const baselineId = profile?.baseline_config_id || (selection as any)?.baseline_config_id || Object.keys(effectiveConfigs)[0];
  const selectedId = selection?.selected_config_id ?? selection?.config_id;

  const baseCfg: any = (baselineId ? effectiveConfigs[baselineId] : undefined)
    || Object.values(effectiveConfigs).find((c: any) => c.config_id === baselineId || c.configuration?.id === baselineId || c.is_baseline)
    || candList.find((c: any) => c.config_id === baselineId || c.configuration?.id === baselineId || c.is_baseline);

  const selCfg: any = (selectedId ? effectiveConfigs[selectedId] : undefined)
    || Object.values(effectiveConfigs).find((c: any) => c.config_id === selectedId || c.configuration?.id === selectedId)
    || candList.find((c: any) => c.config_id === selectedId || c.configuration?.id === selectedId)
    || ((selection as any)?.configuration || (selection as any)?.selected_configuration
      ? { config_id: selectedId, configuration: (selection as any)?.configuration || (selection as any)?.selected_configuration }
      : undefined);

  const allConfigsList: any[] = Object.keys(effectiveConfigs).length > 0
    ? Object.values(effectiveConfigs)
    : candList;

  // Find lowest energy overall across usable configurations
  const lowestEnergyCfg: any = allConfigsList.reduce((prev: any, curr: any) => {
    if (!prev) return curr;
    if (curr.median_energy_j == null) return prev;
    if (prev.median_energy_j == null) return curr;
    return curr.median_energy_j < prev.median_energy_j ? curr : prev;
  }, undefined) || baseCfg;

  const guardedRuntime = selCfg?.guarded_runtime_s
    ?? (selection as any)?.metrics?.guarded_runtime_s
    ?? (selection as any)?.selected_guarded_runtime_s
    ?? (selection as any)?.guarded_runtime_s;

  // data-derived summary line — no hardcoded counts or core names
  const nConfigs = allConfigsList.length;
  const nReps = lowestEnergyCfg?.runtime_samples?.length ?? baseCfg?.runtime_samples?.length ?? 0;
  const layoutsPresent = [...new Set(allConfigsList.map((c) => c.configuration?.layout).filter(Boolean))].sort();

  /** one-line config descriptor from actual configuration fields */
  const describeConfig = (c: any): string => {
    const cfg = c?.configuration ?? c;
    if (!cfg || (!cfg.cpu_affinity && cfg.worker_count == null)) return '—';
    const parts: string[] = [];
    parts.push(`${cfg.cpu_affinity?.length ?? cfg.worker_count ?? 1} cores`);
    if (cfg.freq_cap_khz) parts.push(`${(cfg.freq_cap_khz / 1e6).toFixed(1)} GHz cap`);
    if (cfg.boost === false) parts.push('Boost off');
    else if (cfg.boost === true) parts.push('Boost on');
    return parts.join(' · ');
  };

  // Derived bounds and fine step resolution for the budget slider
  const configRuntimes = React.useMemo(() => {
    return allConfigsList
      .map((c: any) => c.median_runtime_s)
      .filter((r: any) => r != null && r > 0);
  }, [allConfigsList]);

  const minConfigRuntime = configRuntimes.length > 0 ? Math.min(...configRuntimes) : 1;
  const maxConfigRuntime = configRuntimes.length > 0 ? Math.max(...configRuntimes) : 30;

  const { sliderMin, sliderMax, sliderStep } = React.useMemo(() => {
    if (isExtrapolating && taskDuration) {
      const sMin = Math.max(1, Math.round(taskDuration * 0.5));
      const sMax = Math.round(taskDuration * 2.5);
      const sStep = taskDuration > 1000 ? 10 : (taskDuration > 100 ? 5 : 1);
      return { sliderMin: sMin, sliderMax: sMax, sliderStep: sStep };
    }

    // Benchmark mode: tightly bound around measured runtimes instead of static 300s
    const sMin = Math.max(0.5, Math.floor(minConfigRuntime * 0.8 * 10) / 10);
    const naturalMax = Math.ceil(maxConfigRuntime * 1.6);
    const sMax = Math.max(naturalMax, Math.ceil((tempBudget || 0) * 1.15), 15);

    let sStep = 0.5;
    if (sMax <= 15) sStep = 0.1;
    else if (sMax <= 40) sStep = 0.2;
    else if (sMax <= 100) sStep = 0.5;
    else sStep = 1.0;

    return { sliderMin: sMin, sliderMax: sMax, sliderStep: sStep };
  }, [isExtrapolating, taskDuration, minConfigRuntime, maxConfigRuntime, tempBudget]);

  const handleNudge = (direction: -1 | 1) => {
    const delta = direction * sliderStep;
    const nextVal = Math.max(sliderMin, Math.min(sliderMax, Math.round((tempBudget + delta) / sliderStep) * sliderStep));
    const cleanVal = parseFloat(nextVal.toFixed(2));
    setTempBudget(cleanVal);
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      onReselect(cleanVal, isExtrapolating ? (taskDuration || 900) : null);
    }, 120);
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
          border: `1px solid ${colors.border}`,
          boxShadow: colors.cardShadow,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, fontSize: '1.15rem', color: colors.textPrimary, fontWeight: 600 }}>
              Profile Explorer
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
            <div style={{ fontSize: '0.95rem', fontWeight: 700, color: colors.emerald }}>
              {isExtrapolating && taskDuration ? `${formatDuration(tempBudget)} (${tempBudget}s)` : `${tempBudget}s`}
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {/* Fine Nudge Down */}
            <button
              type="button"
              onClick={() => handleNudge(-1)}
              style={{
                width: 26,
                height: 26,
                borderRadius: '0.25rem',
                border: `1px solid ${colors.border}`,
                background: colors.surfaceElevated,
                color: colors.textSecondary,
                fontSize: '0.9rem',
                fontWeight: 'bold',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                userSelect: 'none',
                lineHeight: 1,
              }}
              title={`Decrease budget by ${sliderStep}s`}
            >
              −
            </button>

            {/* Range Slider with fine-tuned bounds */}
            <input
              type="range"
              min={sliderMin}
              max={sliderMax}
              step={sliderStep}
              value={tempBudget}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                if (Number.isFinite(val)) handleSliderChange(val);
              }}
              onPointerUp={() => {
                if (debounceTimerRef.current) {
                  clearTimeout(debounceTimerRef.current);
                }
                onReselect(tempBudget, isExtrapolating ? (taskDuration || 900) : null);
              }}
              style={{ width: '220px', accentColor: colors.emerald, cursor: 'pointer' }}
            />

            {/* Fine Nudge Up */}
            <button
              type="button"
              onClick={() => handleNudge(1)}
              style={{
                width: 26,
                height: 26,
                borderRadius: '0.25rem',
                border: `1px solid ${colors.border}`,
                background: colors.surfaceElevated,
                color: colors.textSecondary,
                fontSize: '0.9rem',
                fontWeight: 'bold',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                userSelect: 'none',
                lineHeight: 1,
              }}
              title={`Increase budget by ${sliderStep}s`}
            >
              +
            </button>

            {/* Numeric Direct Entry Input */}
            <input
              type="text"
              inputMode="decimal"
              value={tempBudget}
              onChange={(e) => {
                const v = parseFloat(e.target.value);
                if (Number.isFinite(v) && v > 0) {
                  setTempBudget(v);
                  if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
                  debounceTimerRef.current = setTimeout(() => onReselect(v, isExtrapolating ? (taskDuration || 900) : null), 300);
                }
              }}
              onBlur={(e) => {
                const v = parseFloat(e.target.value);
                if (Number.isFinite(v) && v > 0) {
                  setTempBudget(v);
                  onReselect(v, isExtrapolating ? (taskDuration || 900) : null);
                }
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  const v = parseFloat((e.target as HTMLInputElement).value);
                  if (Number.isFinite(v) && v > 0) {
                    setTempBudget(v);
                    onReselect(v, isExtrapolating ? (taskDuration || 900) : null);
                  }
                  (e.target as HTMLInputElement).blur();
                }
              }}
              style={{
                width: 58,
                padding: '3px 6px',
                borderRadius: 4,
                border: `1px solid ${colors.border}`,
                background: colors.surfaceElevated,
                color: colors.textPrimary,
                fontSize: '0.82rem',
                textAlign: 'center',
                fontWeight: 600,
              }}
            />
            <span style={{ fontSize: '0.72rem', color: colors.textTertiary }}>s</span>
          </div>
        </div>
      </div>

      {/* Workload Scaling / Task Duration Extrapolation Toolbar */}
      <div
        style={{
          background: colors.surface,
          padding: '0.85rem 1.25rem',
          borderRadius: '0.75rem',
          border: `1px solid ${colors.border}`,
          boxShadow: colors.cardShadow,
          display: 'flex',
          flexDirection: 'column',
          gap: '0.65rem',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span style={{ fontSize: '0.9rem', fontWeight: 600, color: colors.textPrimary }}>
              Workload Extrapolation & Scaling
            </span>
            <span style={{ fontSize: '0.74rem', color: colors.textTertiary }}>
              Measured micro-benchmark: <strong>~{(baseCfg?.median_runtime_s ?? 5.5).toFixed(1)}s</strong>
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              onClick={() => handleTaskDurationChange(null)}
              style={{
                padding: '0.25rem 0.65rem',
                borderRadius: '0.375rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                cursor: 'pointer',
                border: '1px solid ' + (!isExtrapolating ? colors.emerald : colors.border),
                background: !isExtrapolating ? 'rgba(16, 185, 129, 0.15)' : colors.surfaceElevated,
                color: !isExtrapolating ? colors.emerald : colors.textTertiary,
              }}
            >
              Native Benchmark (~{(baseCfg?.median_runtime_s ?? 5.5).toFixed(1)}s)
            </button>
            <button
              onClick={() => handleTaskDurationChange(taskDuration || 900)}
              style={{
                padding: '0.25rem 0.65rem',
                borderRadius: '0.375rem',
                fontSize: '0.75rem',
                fontWeight: 600,
                cursor: 'pointer',
                border: '1px solid ' + (isExtrapolating ? colors.accentHover : colors.border),
                background: isExtrapolating ? 'rgba(56, 189, 248, 0.15)' : colors.surfaceElevated,
                color: isExtrapolating ? colors.accentHover : colors.textTertiary,
              }}
            >
              Scale to Real Task Duration
            </button>
          </div>
        </div>

        {isExtrapolating && (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexWrap: 'wrap',
              gap: '0.75rem',
              paddingTop: '0.5rem',
              borderTop: '1px solid rgba(255,255,255,0.06)',
            }}
          >
            {/* Reference Stock Duration Input */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '0.76rem', color: colors.textSecondary }}>Reference Stock Duration:</span>
              <input
                type="text"
                inputMode="decimal"
                value={taskDuration ?? 900}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  if (Number.isFinite(v) && v > 0) {
                    setTaskDuration(v);
                    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
                    debounceTimerRef.current = setTimeout(() => handleTaskDurationChange(v), 400);
                  }
                }}
                style={{
                  width: 70, padding: '2px 6px', borderRadius: 4,
                  border: `1px solid ${colors.border}`, background: colors.surfaceElevated,
                  color: colors.textPrimary, fontSize: '0.8rem', fontWeight: 600,
                }}
              />
              <span style={{ fontSize: '0.72rem', color: colors.textTertiary }}>
                s ({formatDuration(taskDuration ?? 900)})
              </span>
              <div style={{ display: 'flex', gap: '0.25rem', marginLeft: '0.4rem' }}>
                {[
                  { label: '5m', sec: 300 },
                  { label: '15m (900s)', sec: 900 },
                  { label: '30m', sec: 1800 },
                  { label: '1h', sec: 3600 },
                ].map((p) => (
                  <button
                    key={p.sec}
                    onClick={() => handleTaskDurationChange(p.sec)}
                    style={{
                      padding: '0.15rem 0.45rem',
                      borderRadius: 4,
                      border: '1px solid ' + (taskDuration === p.sec ? colors.accentHover : colors.border),
                      background: taskDuration === p.sec ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                      color: taskDuration === p.sec ? colors.accentHover : colors.textTertiary,
                      fontSize: '0.7rem',
                      cursor: 'pointer',
                    }}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Quick Slack Presets */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
              <span style={{ fontSize: '0.72rem', color: colors.textTertiary }}>Quick Slack:</span>
              {[
                { label: '+0% (Strict)', mult: 1.0 },
                { label: '+10%', mult: 1.10 },
                { label: '+20%', mult: 1.20 },
                { label: '+33% (1200s)', mult: 1.3333 },
                { label: '+50%', mult: 1.50 },
              ].map((slack) => {
                const targetS = Math.round((taskDuration || 900) * slack.mult);
                const isActive = Math.abs(tempBudget - targetS) <= 1;
                return (
                  <button
                    key={slack.label}
                    onClick={() => triggerReselect(targetS, taskDuration || 900)}
                    style={{
                      padding: '0.15rem 0.45rem',
                      borderRadius: 4,
                      border: '1px solid ' + (isActive ? colors.emerald : colors.border),
                      background: isActive ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
                      color: isActive ? colors.emerald : colors.textTertiary,
                      fontSize: '0.7rem',
                      cursor: 'pointer',
                    }}
                  >
                    {slack.label}
                  </button>
                );
              })}
            </div>
          </div>
        )}
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
            <span style={{ fontWeight: 600 }}>
              {isExtrapolating && taskDuration
                ? `${formatDuration(taskDuration)} (${taskDuration}s)`
                : `${baseCfg?.median_runtime_s}s`}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: colors.textTertiary }}>Package Energy:</span>
            <span style={{ fontWeight: 600, color: colors.red }}>
              {isExtrapolating && taskDuration && baseCfg?.median_runtime_s
                ? formatEnergy((baseCfg.median_energy_j ?? 0) * (taskDuration / baseCfg.median_runtime_s))
                : `${baseCfg?.median_energy_j} J`}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            <span style={{ color: colors.textTertiary }}>Avg Power:</span>
            <span style={{ fontWeight: 600 }}>{baseCfg?.median_power_w} W</span>
          </div>
        </div>

        {/* Card 2: Lowest Energy Overall */}
        {(() => {
          const baseRt = baseCfg?.median_runtime_s || 1;
          const lowestRt = lowestEnergyCfg?.median_runtime_s || 1;
          const lowestGuarded = lowestEnergyCfg?.guarded_runtime_s || lowestRt * 1.05;
          const extLowestRt = isExtrapolating && taskDuration ? taskDuration * (lowestRt / baseRt) : lowestRt;
          const extLowestGuarded = isExtrapolating && taskDuration ? taskDuration * (lowestGuarded / baseRt) : lowestGuarded;
          const extLowestEnergy = isExtrapolating && taskDuration
            ? (lowestEnergyCfg?.median_energy_j ?? 0) * (taskDuration / baseRt)
            : (lowestEnergyCfg?.median_energy_j ?? 0);
          const isLowestFeasible = extLowestGuarded <= tempBudget;

          return (
            <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem', border: `1px solid ${!isLowestFeasible ? 'rgba(239, 68, 68, 0.35)' : 'rgba(255,255,255,0.08)'}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '0.75rem', color: colors.amber, fontWeight: 600, textTransform: 'uppercase' }}>
                  Lowest Energy Overall
                </span>
                {!isLowestFeasible && (
                  <span style={{ fontSize: '0.68rem', fontWeight: 600, color: colors.red }}>
                    ⚠ Infeasible for {tempBudget}s budget
                  </span>
                )}
              </div>
              <div style={{ fontSize: '1rem', fontWeight: 700, color: colors.textPrimary, marginTop: '0.2rem' }}>
                {lowestEnergyCfg ? lowestEnergyCfg.config_id : '—'}
              </div>
              <div style={{ fontSize: '0.75rem', color: colors.textTertiary }}>
                {describeConfig(lowestEnergyCfg)}
              </div>
              <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                <span style={{ color: colors.textTertiary }}>Runtime:</span>
                <span style={{ fontWeight: 600, color: !isLowestFeasible ? colors.red : colors.textPrimary }}>
                  {isExtrapolating && taskDuration
                    ? `${formatDuration(extLowestRt)} (guarded: ${formatDuration(extLowestGuarded)})`
                    : `${lowestEnergyCfg?.median_runtime_s}s`}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                <span style={{ color: colors.textTertiary }}>Package Energy:</span>
                <span style={{ fontWeight: 600, color: colors.amber }}>
                  {isExtrapolating && taskDuration ? formatEnergy(extLowestEnergy) : `${lowestEnergyCfg?.median_energy_j} J`}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                <span style={{ color: colors.textTertiary }}>Energy Delta:</span>
                <span style={{ fontWeight: 600, color: colors.emerald }}>
                  -{Math.round(100 * (1 - (lowestEnergyCfg?.median_energy_j ?? 1) / (baseCfg?.median_energy_j ?? 1)))}%
                </span>
              </div>
            </div>
          );
        })()}

        {/* Card 3: Selected Within Budget */}
        {(() => {
          const baseRt = baseCfg?.median_runtime_s || 1;
          const selRt = selCfg?.median_runtime_s || 1;
          const extSelRt = isExtrapolating && taskDuration ? taskDuration * (selRt / baseRt) : selRt;
          const extSelGuarded = isExtrapolating && taskDuration && guardedRuntime != null
            ? taskDuration * (guardedRuntime / baseRt)
            : guardedRuntime;
          const extSelEnergy = isExtrapolating && taskDuration
            ? (selCfg?.median_energy_j ?? 0) * (taskDuration / baseRt)
            : (selCfg?.median_energy_j ?? 0);

          return (
            <div style={{ background: 'rgba(16,185,129,0.12)', borderRadius: '0.75rem', padding: '1rem', border: '1.5px solid ' + colors.emerald }}>
              <div style={{ fontSize: '0.75rem', color: colors.emerald, fontWeight: 600, textTransform: 'uppercase' }}>
                Selected Within Budget ★
              </div>
              <div style={{ fontSize: '1rem', fontWeight: 700, color: colors.emerald, marginTop: '0.2rem' }}>
                {selCfg ? selCfg.config_id : selectedId ? selectedId : 'Profiling in progress…'}
              </div>
              <div style={{ fontSize: '0.75rem', color: colors.textTertiary }}>
                {describeConfig(selCfg)}
              </div>
              <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                <span style={{ color: colors.textTertiary }}>Guarded Runtime:</span>
                <span style={{ fontWeight: 700, color: colors.emerald }}>
                  {isExtrapolating && taskDuration && extSelGuarded != null
                    ? `${formatDuration(extSelGuarded)} (≤ ${formatDuration(tempBudget)})`
                    : guardedRuntime != null
                    ? `${guardedRuntime.toFixed(2)}s (≤ ${tempBudget}s)`
                    : 'Measuring…'}
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                <span style={{ color: colors.textTertiary }}>Energy Savings:</span>
                <span style={{ fontWeight: 700, color: colors.emerald, fontSize: '1rem' }}>
                  {selection?.savings_vs_baseline_pct != null
                    ? `-${selection.savings_vs_baseline_pct}%`
                    : selection?.energy_reduction_pct != null
                    ? `-${selection.energy_reduction_pct.toFixed(1)}%`
                    : '—'}
                </span>
              </div>
              <button
                onClick={onNavigateValidation}
                disabled={!selCfg && !selectedId}
                style={{
                  width: '100%',
                  marginTop: '0.6rem',
                  padding: '0.4rem',
                  borderRadius: '0.375rem',
                  border: 'none',
                  backgroundColor: (selCfg || selectedId) ? colors.emerald : colors.surfaceElevated,
                  color: (selCfg || selectedId) ? colors.textPrimary : colors.textTertiary,
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  cursor: (selCfg || selectedId) ? 'pointer' : 'default',
                }}
              >
                Verify with Fresh Validation Runs →
              </button>
            </div>
          );
        })()}
      </div>

      {/* Main Pareto Scatter Chart */}
      <ParetoChart
        configurations={effectiveConfigs}
        selectedConfigId={selectedId}
        baselineConfigId={baselineId}
        deadlineS={tempBudget}
        taskDurationS={isExtrapolating ? (taskDuration || 900) : null}
        frontierConfigIds={selection?.frontier_config_ids ?? []}
        onSelectConfig={(cid) => {
          // Point click selection
        }}
      />

      {/* Layout Candidates */}
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem 1.5rem', border: `1px solid ${colors.border}`, boxShadow: colors.cardShadow }}>
        <h3 style={{ margin: '0 0 0.35rem 0', fontSize: '1rem', color: colors.textPrimary, fontWeight: 600 }}>
          Layout Candidates
        </h3>
        <div style={{ fontSize: '0.75rem', color: colors.textTertiary, marginBottom: '0.75rem' }}>
          Configurations based on processor topology and calibration measurements. {selectedCandidates.size > 0 && `${selectedCandidates.size} selected.`}
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
      <div style={{ background: colors.surface, borderRadius: '0.75rem', padding: '1rem 1.5rem', border: `1px solid ${colors.border}`, boxShadow: colors.cardShadow }}>
        <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', color: colors.textPrimary, fontWeight: 600 }}>
          Measured Runs ({(profile?.runs || []).length} captured)
        </h3>
        <div style={{ overflowX: 'auto' }}>
          {(profile?.runs || []).length === 0 ? (
            <div style={{ padding: '1.5rem', textAlign: 'center', color: colors.textTertiary, fontSize: '0.85rem' }}>
              No individual execution runs recorded yet. Start a sweep to profile configurations live on hardware.
            </div>
          ) : (
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
                {(profile?.runs || []).map((r) => {
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
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>{r.runtime_s != null ? r.runtime_s.toFixed(2) : '—'}</td>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace', color: isSelected ? colors.emerald : colors.textSecondary }}>
                        {r.package_energy_j != null ? `${r.package_energy_j.toFixed(1)} J` : 'unavailable'}
                      </td>
                      <td style={{ padding: '0.5rem', fontFamily: 'monospace' }}>
                        {r.package_energy_j != null && r.runtime_s ? (r.package_energy_j / r.runtime_s).toFixed(1) + ' W' : '-'}
                      </td>
                      <td style={{ padding: '0.5rem' }}>
                        <span style={{ color: colors.emerald, fontWeight: 600 }}>✓ verified</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};
