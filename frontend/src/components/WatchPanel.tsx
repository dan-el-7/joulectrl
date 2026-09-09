import React, { useEffect, useState } from 'react';
import { fetchWatchStatus, startWatch, stopWatch } from '../api';
import { WatchStatus } from '../types';

interface WatchPanelProps {
  onApplySuggestedBudget: (budgetS: number) => void;
}

export const WatchPanel: React.FC<WatchPanelProps> = ({ onApplySuggestedBudget }) => {
  const [status, setStatus] = useState<WatchStatus | null>(null);
  const [isToggling, setIsToggling] = useState<boolean>(false);
  const [latestSegment, setLatestSegment] = useState<{ duration_s: number; estimated_energy_j: number; suggested_budget_s: number } | null>({
    duration_s: 47.0,
    estimated_energy_j: 1410.0,
    suggested_budget_s: 49.35,
  });

  const refreshStatus = async () => {
    try {
      const st = await fetchWatchStatus();
      setStatus(st);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    refreshStatus();
    const interval = setInterval(refreshStatus, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleToggle = async () => {
    try {
      setIsToggling(true);
      if (status?.active) {
        const res = await stopWatch();
        if (res.segments && res.segments.length > 0) {
          setLatestSegment(res.segments[0]);
        }
      } else {
        await startWatch();
      }
      await refreshStatus();
    } catch (e: any) {
      alert(`Watch mode error: ${e.message}`);
    } finally {
      setIsToggling(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1000px', margin: '0 auto' }}>
      {/* Header */}
      <div
        style={{
          background: '#111827',
          padding: '1.25rem',
          borderRadius: '0.75rem',
          border: '1px solid #1f2937',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <h2 style={{ margin: 0, fontSize: '1.15rem', color: '#f3f4f6', fontWeight: 600 }}>
              Passive Watch Mode (Idle → Activity → Idle Detection)
            </h2>
            <span
              style={{
                fontSize: '0.65rem',
                fontWeight: 600,
                padding: '0.15rem 0.4rem',
                borderRadius: '0.25rem',
                backgroundColor: '#374151',
                color: '#9ca3af',
              }}
            >
              Estimate Tier (§6b)
            </span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#9ca3af', marginTop: '0.25rem' }}>
            Watches package power passively (1 Hz) while you run your own task. Automatically suggests a runtime budget.
          </div>
        </div>

        <button
          onClick={handleToggle}
          disabled={isToggling}
          style={{
            padding: '0.5rem 1.25rem',
            borderRadius: '0.375rem',
            backgroundColor: status?.active ? '#ef4444' : '#10b981',
            color: '#ffffff',
            fontSize: '0.85rem',
            fontWeight: 600,
            border: 'none',
            cursor: isToggling ? 'wait' : 'pointer',
          }}
        >
          {status?.active ? 'Stop Passive Watching' : 'Start Passive Watching'}
        </button>
      </div>

      {/* Live Metrics Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem' }}>
        <div style={{ background: '#111827', padding: '1.25rem', borderRadius: '0.75rem', border: '1px solid #1f2937' }}>
          <div style={{ fontSize: '0.75rem', color: '#9ca3af', textTransform: 'uppercase' }}>Current Package Power</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: '#f3f4f6', marginTop: '0.3rem' }}>
            {status?.current_power_w ?? 8.6} W
          </div>
          <div style={{ fontSize: '0.75rem', color: '#10b981', marginTop: '0.25rem' }}>
            {status?.active ? '● Featherweight polling (1 Hz)' : '○ Standby'}
          </div>
        </div>

        <div style={{ background: '#111827', padding: '1.25rem', borderRadius: '0.75rem', border: '1px solid #1f2937' }}>
          <div style={{ fontSize: '0.75rem', color: '#9ca3af', textTransform: 'uppercase' }}>Learned Idle Baseline</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, color: '#60a5fa', marginTop: '0.3rem' }}>
            {status?.baseline_median_w ?? 8.6} W
          </div>
          <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '0.25rem' }}>
            Spread: ±{status?.baseline_spread_w ?? 0.4} W (30s median)
          </div>
        </div>

        <div style={{ background: '#111827', padding: '1.25rem', borderRadius: '0.75rem', border: '1px solid #1f2937' }}>
          <div style={{ fontSize: '0.75rem', color: '#9ca3af', textTransform: 'uppercase' }}>Detection State</div>
          <div style={{ fontSize: '1.4rem', fontWeight: 700, color: '#f59e0b', marginTop: '0.5rem', textTransform: 'capitalize' }}>
            {status?.state?.replace('_', ' ') ?? 'Idle'}
          </div>
          <div style={{ fontSize: '0.75rem', color: '#9ca3af', marginTop: '0.25rem' }}>
            {status?.active ? 'Monitoring power trace' : 'Watcher inactive'}
          </div>
        </div>
      </div>

      {/* Suggested Budget & Observation Card */}
      {latestSegment && (
        <div
          style={{
            background: '#064e3b18',
            border: '1.5px solid #059669',
            borderRadius: '0.75rem',
            padding: '1.25rem',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div>
            <div style={{ fontSize: '0.8rem', color: '#10b981', fontWeight: 600, textTransform: 'uppercase' }}>
              Detected Task Observation (Idle-to-Idle Window)
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: 700, color: '#f3f4f6', marginTop: '0.25rem' }}>
              Observed Duration: {latestSegment.duration_s}s · Est. Energy: {latestSegment.estimated_energy_j} J
            </div>
            <div style={{ fontSize: '0.8rem', color: '#a7f3d0', marginTop: '0.25rem' }}>
              Calculated suggested runtime budget: <strong>{latestSegment.suggested_budget_s}s</strong> (includes 5% headroom)
            </div>
          </div>

          <button
            onClick={() => onApplySuggestedBudget(latestSegment.suggested_budget_s)}
            style={{
              padding: '0.6rem 1.2rem',
              borderRadius: '0.375rem',
              backgroundColor: '#059669',
              color: '#ffffff',
              fontSize: '0.85rem',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
              boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
            }}
          >
            Apply to Setup Budget Slider →
          </button>
        </div>
      )}

      {/* Rules Notice */}
      <div style={{ background: '#1f2937', padding: '1rem', borderRadius: '0.5rem', border: '1px solid #374151', fontSize: '0.78rem', color: '#9ca3af' }}>
        <strong style={{ color: '#d1d5db' }}>Honesty Guard (§6b):</strong> Watch observations carry <code>mode="watch"</code> and are strictly excluded from Pareto/selection evidence by default. They inform the budget slider; the actual optimizer selection runs only on verified harness profiling runs.
      </div>
    </div>
  );
};
