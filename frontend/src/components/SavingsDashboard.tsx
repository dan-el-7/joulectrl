import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  fetchSavingsDashboard,
  setSavingsOptIn,
  resetSavingsLedger,
  getSavingsExportUrl,
} from '../api';
import { fonts, fontFeatures, radii } from '../design';
import { useTheme } from '../ThemeContext';
import { SavingsDashboardResponse, SavingsLedgerEntry } from '../types';
import { AutoPilotControl } from './AutoPilotControl';

export const SavingsDashboard: React.FC = () => {
  const { theme, themeColors } = useTheme();
  const c = themeColors;
  const isLight = theme === 'light';

  const [data, setData] = useState<SavingsDashboardResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [toggling, setToggling] = useState<boolean>(false);
  const [resetting, setResetting] = useState<boolean>(false);
  const [showResetConfirm, setShowResetConfirm] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterObjective, setFilterObjective] = useState<string>('all');
  const [seedDemo, setSeedDemo] = useState<boolean>(true);

  // Load dashboard data (strictly on-demand, 0 idle loops)
  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetchSavingsDashboard();
      setData(res);
    } catch (e) {
      console.warn('Failed to load savings dashboard:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  // Zero-power invariant: Only fetch on mount and on explicit tab visibility restoration
  useEffect(() => {
    loadDashboard();

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        loadDashboard();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [loadDashboard]);

  // Handle opt-in toggle
  const handleToggleOptIn = async (enabled: boolean) => {
    setToggling(true);
    try {
      await setSavingsOptIn(enabled, seedDemo);
      await loadDashboard();
    } catch (e) {
      console.error('Failed to toggle savings opt-in:', e);
    } finally {
      setToggling(false);
    }
  };

  // Handle ledger reset
  const handleResetLedger = async () => {
    setResetting(true);
    try {
      await resetSavingsLedger();
      setShowResetConfirm(false);
      await loadDashboard();
    } catch (e) {
      console.error('Failed to reset savings ledger:', e);
    } finally {
      setResetting(false);
    }
  };

  // Filtered ledger rows
  const filteredLedger = useMemo(() => {
    if (!data?.ledger) return [];
    return data.ledger.filter((entry: SavingsLedgerEntry) => {
      const matchQuery =
        !searchQuery ||
        (entry.app_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        (entry.workload_name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
        entry.session_id.toLowerCase().includes(searchQuery.toLowerCase());

      const matchObj =
        filterObjective === 'all' ||
        (entry.objective || '').toLowerCase() === filterObjective.toLowerCase();

      return matchQuery && matchObj;
    });
  }, [data?.ledger, searchQuery, filterObjective]);

  const summary = data?.summary;
  const isOptedIn = data?.opted_in ?? false;

  // Formatting helpers
  const formatEnergy = (joules: number) => {
    if (joules >= 1000000) return `${(joules / 1000000).toFixed(2)} MJ`;
    if (joules >= 1000) return `${(joules / 1000).toFixed(1)} kJ`;
    return `${joules.toFixed(1)} J`;
  };

  const formatRuntime = (seconds: number) => {
    if (seconds < 60) return `${seconds.toFixed(1)}s`;
    const mins = Math.floor(seconds / 60);
    const rem = Math.round(seconds % 60);
    return `${mins}m ${rem}s`;
  };

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 20px 60px' }}>
      {/* Top Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: 16,
          marginBottom: 24,
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 24 }}>🌱</span>
            <h1
              style={{
                fontSize: 22,
                fontWeight: 700,
                color: c.textPrimary,
                margin: 0,
                letterSpacing: '-0.02em',
              }}
            >
              Energy & Carbon Savings Dashboard
            </h1>
          </div>
          <p style={{ margin: '6px 0 0', fontSize: 13, color: c.textTertiary }}>
            Auditable hardware energy reduction, watts saved, and carbon emissions averted.
          </p>
        </div>

        {/* Opt-In Switch & Zero-Overhead Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              background: isLight ? '#ecfdf5' : 'rgba(16, 185, 129, 0.08)',
              border: `1px solid ${isLight ? '#a7f3d0' : 'rgba(16, 185, 129, 0.25)'}`,
              padding: '6px 12px',
              borderRadius: radii.md,
              fontSize: 12,
              fontWeight: 600,
              color: isLight ? '#065f46' : '#34d399',
            }}
          >
            <span>⚡</span>
            <span>Zero-Overhead: 0.0 W Idle Cost</span>
          </div>

          <button
            onClick={() => handleToggleOptIn(!isOptedIn)}
            disabled={toggling}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              background: isOptedIn
                ? isLight
                  ? '#eff6ff'
                  : 'rgba(99, 102, 241, 0.12)'
                : isLight
                ? '#f1f5f9'
                : 'rgba(255, 255, 255, 0.05)',
              border: `1px solid ${
                isOptedIn ? (isLight ? '#93c5fd' : c.accent) : c.border
              }`,
              color: isOptedIn ? (isLight ? '#1d4ed8' : c.accent) : c.textSecondary,
              padding: '7px 14px',
              borderRadius: radii.md,
              fontSize: 12,
              fontWeight: 600,
              cursor: toggling ? 'wait' : 'pointer',
              transition: 'all 0.15s ease',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: isOptedIn ? (isLight ? '#2563eb' : '#34d399') : c.textQuaternary,
              }}
            />
            {isOptedIn ? 'Tracking Opted-In (Active)' : 'Tracking Disabled (Opt-In)'}
          </button>
        </div>
      </div>

      {/* Opt-Out Onboarding Card */}
      {!isOptedIn && (
        <div
          style={{
            background: isLight ? '#ffffff' : c.surface,
            border: `1px solid ${c.border}`,
            borderRadius: radii.lg,
            padding: '24px 28px',
            marginBottom: 28,
            boxShadow: c.cardShadow,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <span style={{ fontSize: 24 }}>🛡️</span>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: c.textPrimary }}>
              Energy Savings Telemetry is Opt-In
            </h3>
          </div>
          <p
            style={{
              margin: '0 0 16px',
              fontSize: 13,
              color: c.textSecondary,
              lineHeight: 1.6,
              maxWidth: 780,
            }}
          >
            Joulectrl is built from first principles to prioritize hardware battery life and efficiency.
            To avoid the <strong>Observer Effect</strong> (wasting battery power just to display how much power
            is saved), tracking is strictly disabled until you choose to enable it.
          </p>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
              gap: 12,
              marginBottom: 20,
            }}
          >
            <div
              style={{
                padding: '12px 14px',
                borderRadius: radii.md,
                background: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
                border: `1px solid ${c.borderSubtle}`,
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13, color: c.textPrimary, marginBottom: 4 }}>
                ⚡ 0.0 W Idle Overhead
              </div>
              <div style={{ fontSize: 12, color: c.textTertiary, lineHeight: 1.4 }}>
                No continuous background threads or timer interrupts. Hardware stays in C6/C8/C10 sleep.
              </div>
            </div>

            <div
              style={{
                padding: '12px 14px',
                borderRadius: radii.md,
                background: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
                border: `1px solid ${c.borderSubtle}`,
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13, color: c.textPrimary, marginBottom: 4 }}>
                🔒 100% Local SQLite
              </div>
              <div style={{ fontSize: 12, color: c.textTertiary, lineHeight: 1.4 }}>
                Receipts persist locally in <code>~/.joulectrl/joulectrl.db</code>. Zero cloud reporting.
              </div>
            </div>

            <div
              style={{
                padding: '12px 14px',
                borderRadius: radii.md,
                background: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
                border: `1px solid ${c.borderSubtle}`,
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13, color: c.textPrimary, marginBottom: 4 }}>
                🎯 Discrete Workload Logging
              </div>
              <div style={{ fontSize: 12, color: c.textTertiary, lineHeight: 1.4 }}>
                Records receipts strictly when an optimization run or compute burst ends (&lt;0.2ms write).
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <button
              onClick={() => handleToggleOptIn(true)}
              disabled={toggling}
              style={{
                background: isLight ? '#10b981' : '#059669',
                color: '#ffffff',
                border: 'none',
                borderRadius: radii.md,
                padding: '9px 18px',
                fontWeight: 600,
                fontSize: 13,
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <span>Enable Energy Savings Tracking</span>
              <span>→</span>
            </button>

            <label
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 8,
                fontSize: 12,
                color: c.textSecondary,
                cursor: 'pointer',
              }}
            >
              <input
                type="checkbox"
                checked={seedDemo}
                onChange={(e) => setSeedDemo(e.target.checked)}
              />
              <span>Preload sample demonstration history for exploration</span>
            </label>
          </div>
        </div>
      )}

      {/* Auto-Pilot Autonomous Background Optimizer Card */}
      {isOptedIn && (
        <div style={{ marginBottom: 20 }}>
          <AutoPilotControl compact={false} onStatusChange={() => {}} />
        </div>
      )}

      {/* Hero Metric Tiles (When Opted-In or Previewing) */}
      {isOptedIn && summary && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
            gap: 14,
            marginBottom: 24,
          }}
        >
          {/* Card 1: Total Energy Saved */}
          <div
            style={{
              background: isLight ? '#ffffff' : c.surface,
              border: `1px solid ${c.border}`,
              borderRadius: radii.lg,
              padding: '18px 20px',
              boxShadow: c.cardShadow,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: c.textTertiary }}>
                TOTAL ENERGY SAVED
              </span>
              <span style={{ fontSize: 18 }}>⚡</span>
            </div>
            <div
              style={{
                fontSize: 26,
                fontWeight: 700,
                fontFamily: fonts.mono,
                fontFeatureSettings: fontFeatures,
                color: isLight ? '#059669' : '#34d399',
                letterSpacing: '-0.02em',
              }}
            >
              {formatEnergy(summary.total_saved_energy_j)}
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, marginTop: 4 }}>
              {summary.total_saved_energy_wh.toFixed(2)} Wh ({summary.avg_saved_pct.toFixed(0)}% avg cut)
            </div>
          </div>

          {/* Card 2: Average Power Reduced */}
          <div
            style={{
              background: isLight ? '#ffffff' : c.surface,
              border: `1px solid ${c.border}`,
              borderRadius: radii.lg,
              padding: '18px 20px',
              boxShadow: c.cardShadow,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: c.textTertiary }}>
                AVG POWER REDUCTION
              </span>
              <span style={{ fontSize: 18 }}>📉</span>
            </div>
            <div
              style={{
                fontSize: 26,
                fontWeight: 700,
                fontFamily: fonts.mono,
                fontFeatureSettings: fontFeatures,
                color: isLight ? '#2563eb' : '#60a5fa',
                letterSpacing: '-0.02em',
              }}
            >
              -{summary.avg_watts_saved.toFixed(1)} W
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, marginTop: 4 }}>
              Lower sustained heat & fan noise
            </div>
          </div>

          {/* Card 3: Active Optimized Time */}
          <div
            style={{
              background: isLight ? '#ffffff' : c.surface,
              border: `1px solid ${c.border}`,
              borderRadius: radii.lg,
              padding: '18px 20px',
              boxShadow: c.cardShadow,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: c.textTertiary }}>
                COMPUTE OPTIMIZED
              </span>
              <span style={{ fontSize: 18 }}>⏱️</span>
            </div>
            <div
              style={{
                fontSize: 26,
                fontWeight: 700,
                fontFamily: fonts.mono,
                fontFeatureSettings: fontFeatures,
                color: c.textPrimary,
                letterSpacing: '-0.02em',
              }}
            >
              {formatRuntime(summary.total_runtime_s)}
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, marginTop: 4 }}>
              Across {summary.sessions_count} logged {summary.sessions_count === 1 ? 'burst' : 'bursts'}
            </div>
          </div>

          {/* Card 4: Battery Extension */}
          <div
            style={{
              background: isLight ? '#ffffff' : c.surface,
              border: `1px solid ${c.border}`,
              borderRadius: radii.lg,
              padding: '18px 20px',
              boxShadow: c.cardShadow,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: c.textTertiary }}>
                BATTERY EXTENDED
              </span>
              <span style={{ fontSize: 18 }}>🔋</span>
            </div>
            <div
              style={{
                fontSize: 26,
                fontWeight: 700,
                fontFamily: fonts.mono,
                fontFeatureSettings: fontFeatures,
                color: isLight ? '#d97706' : '#fbbf24',
                letterSpacing: '-0.02em',
              }}
            >
              +{summary.battery_extension_minutes.toFixed(1)} min
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, marginTop: 4 }}>
              Est. runtime on 60Wh battery
            </div>
          </div>

          {/* Card 5: Carbon Avoided */}
          <div
            style={{
              background: isLight ? '#ffffff' : c.surface,
              border: `1px solid ${c.border}`,
              borderRadius: radii.lg,
              padding: '18px 20px',
              boxShadow: c.cardShadow,
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <span style={{ fontSize: 12, fontWeight: 600, color: c.textTertiary }}>
                CO₂ AVERTED
              </span>
              <span style={{ fontSize: 18 }}>🍃</span>
            </div>
            <div
              style={{
                fontSize: 26,
                fontWeight: 700,
                fontFamily: fonts.mono,
                fontFeatureSettings: fontFeatures,
                color: isLight ? '#059669' : '#10b981',
                letterSpacing: '-0.02em',
              }}
            >
              {summary.co2_saved_grams.toFixed(2)} g
            </div>
            <div style={{ fontSize: 12, color: c.textSecondary, marginTop: 4 }}>
              Grid carbon intensity: ~390g/kWh
            </div>
          </div>
        </div>
      )}

      {/* Architectural Transparency Notice */}
      <div
        style={{
          background: isLight ? '#f8fafc' : 'rgba(255, 255, 255, 0.02)',
          border: `1px solid ${c.borderSubtle}`,
          borderRadius: radii.md,
          padding: '14px 18px',
          marginBottom: 24,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: c.textSecondary }}>
          <span style={{ fontSize: 16 }}>💡</span>
          <span>
            <strong>The Observer Effect Solution:</strong> Unlike legacy meters that continuously poll counters at 60Hz and waste 1–2W, Joulectrl logs strictly on burst completion (<code style={{ color: c.textPrimary }}>&lt;0.2ms</code> WAL append). Idle hardware stays in deep package C-states.
          </span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <span
            style={{
              fontSize: 11,
              padding: '3px 8px',
              borderRadius: radii.sm,
              background: isLight ? '#e2e8f0' : 'rgba(255, 255, 255, 0.06)',
              color: c.textTertiary,
              fontFamily: fonts.mono,
            }}
          >
            SQLite WAL
          </span>
          <span
            style={{
              fontSize: 11,
              padding: '3px 8px',
              borderRadius: radii.sm,
              background: isLight ? '#e2e8f0' : 'rgba(255, 255, 255, 0.06)',
              color: c.textTertiary,
              fontFamily: fonts.mono,
            }}
          >
            Event-Driven
          </span>
        </div>
      </div>

      {/* Receipts Ledger Section (When Opted-In) */}
      {isOptedIn && (
        <div
          style={{
            background: isLight ? '#ffffff' : c.surface,
            border: `1px solid ${c.border}`,
            borderRadius: radii.lg,
            padding: '20px 22px',
            boxShadow: c.cardShadow,
          }}
        >
          {/* Controls Bar */}
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 12,
              marginBottom: 16,
            }}
          >
            <div>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: c.textPrimary }}>
                Auditable Savings Receipts Ledger
              </h3>
              <p style={{ margin: '3px 0 0', fontSize: 12, color: c.textTertiary }}>
                Immutable records generated upon workload or burst completion.
              </p>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              {/* Search input */}
              <input
                type="text"
                placeholder="Filter app or workload..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  background: isLight ? '#f1f5f9' : c.inputBg,
                  border: `1px solid ${c.inputBorder}`,
                  borderRadius: radii.md,
                  padding: '6px 10px',
                  fontSize: 12,
                  color: c.textPrimary,
                  outline: 'none',
                  minWidth: 180,
                }}
              />

              {/* Filter objective */}
              <select
                value={filterObjective}
                onChange={(e) => setFilterObjective(e.target.value)}
                style={{
                  background: isLight ? '#f1f5f9' : c.inputBg,
                  border: `1px solid ${c.inputBorder}`,
                  borderRadius: radii.md,
                  padding: '6px 10px',
                  fontSize: 12,
                  color: c.textPrimary,
                  outline: 'none',
                }}
              >
                <option value="all">All Objectives</option>
                <option value="efficiency">Sweet Spot (Efficiency)</option>
                <option value="deadline">Deadline Slack</option>
              </select>

              {/* Export CSV */}
              <a
                href={getSavingsExportUrl('csv')}
                download="joulectrl_savings_ledger.csv"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  background: isLight ? '#f1f5f9' : 'rgba(255, 255, 255, 0.05)',
                  border: `1px solid ${c.border}`,
                  borderRadius: radii.md,
                  padding: '6px 12px',
                  fontSize: 12,
                  fontWeight: 600,
                  color: c.textSecondary,
                  textDecoration: 'none',
                }}
              >
                <span>📥 CSV</span>
              </a>

              {/* Export JSON */}
              <a
                href={getSavingsExportUrl('json')}
                target="_blank"
                rel="noreferrer"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  background: isLight ? '#f1f5f9' : 'rgba(255, 255, 255, 0.05)',
                  border: `1px solid ${c.border}`,
                  borderRadius: radii.md,
                  padding: '6px 12px',
                  fontSize: 12,
                  fontWeight: 600,
                  color: c.textSecondary,
                  textDecoration: 'none',
                }}
              >
                <span>📄 JSON</span>
              </a>

              {/* Clear Ledger Button */}
              <button
                onClick={() => setShowResetConfirm(true)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  background: 'transparent',
                  border: `1px solid ${isLight ? '#fecaca' : 'rgba(244, 88, 110, 0.3)'}`,
                  borderRadius: radii.md,
                  padding: '6px 12px',
                  fontSize: 12,
                  fontWeight: 600,
                  color: isLight ? '#dc2626' : '#f87171',
                  cursor: 'pointer',
                }}
              >
                <span>🗑️ Reset</span>
              </button>
            </div>
          </div>

          {/* Confirmation Modal for Reset */}
          {showResetConfirm && (
            <div
              style={{
                background: isLight ? '#fef2f2' : 'rgba(244, 88, 110, 0.08)',
                border: `1px solid ${isLight ? '#fca5a5' : 'rgba(244, 88, 110, 0.3)'}`,
                borderRadius: radii.md,
                padding: '12px 16px',
                marginBottom: 16,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: 12,
              }}
            >
              <div style={{ fontSize: 13, color: isLight ? '#991b1b' : '#fca5a5' }}>
                Are you sure you want to clear all historical receipts? This cannot be undone.
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={handleResetLedger}
                  disabled={resetting}
                  style={{
                    background: '#dc2626',
                    color: '#ffffff',
                    border: 'none',
                    borderRadius: radii.sm,
                    padding: '5px 12px',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer',
                  }}
                >
                  {resetting ? 'Clearing...' : 'Confirm Clear'}
                </button>
                <button
                  onClick={() => setShowResetConfirm(false)}
                  style={{
                    background: 'transparent',
                    border: `1px solid ${c.border}`,
                    color: c.textSecondary,
                    borderRadius: radii.sm,
                    padding: '5px 12px',
                    fontSize: 12,
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Ledger Table */}
          {filteredLedger.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '36px 20px',
                color: c.textTertiary,
                fontSize: 13,
              }}
            >
              No savings receipts recorded yet. Once an optimization run or monitored app burst finishes, receipts will appear here automatically.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table
                style={{
                  width: '100%',
                  borderCollapse: 'collapse',
                  fontSize: 12,
                  fontFamily: fonts.sans,
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: `1px solid ${c.border}`,
                      color: c.textTertiary,
                      textAlign: 'left',
                    }}
                  >
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>SESSION / TIME</th>
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>APP / WORKLOAD</th>
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>OBJECTIVE</th>
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>RUNTIME</th>
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>STOCK POWER</th>
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>OPTIMIZED POWER</th>
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>WATTS SAVED</th>
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>ENERGY SAVED</th>
                    <th style={{ padding: '10px 8px', fontWeight: 600 }}>SAVINGS %</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLedger.map((entry: SavingsLedgerEntry) => {
                    const stockW = entry.stock_avg_power_w ?? (entry.runtime_s > 0 ? entry.stock_energy_j / entry.runtime_s : 0);
                    const optW = entry.optimized_avg_power_w ?? (entry.runtime_s > 0 ? entry.optimized_energy_j / entry.runtime_s : 0);
                    const savedW = entry.saved_avg_power_w ?? (stockW - optW);

                    return (
                      <tr
                        key={entry.id}
                        style={{
                          borderBottom: `1px solid ${c.borderSubtle}`,
                          color: c.textPrimary,
                        }}
                      >
                        <td style={{ padding: '10px 8px', fontFamily: fonts.mono, fontSize: 11, color: c.textTertiary }}>
                          <div>{entry.session_id}</div>
                          <div style={{ fontSize: 10, color: c.textQuaternary }}>
                            {entry.timestamp_iso ? entry.timestamp_iso.replace('T', ' ').substring(0, 19) : ''}
                          </div>
                        </td>
                        <td style={{ padding: '10px 8px', fontWeight: 600 }}>
                          <div>{entry.app_name || entry.workload_name || 'Workload'}</div>
                          {entry.target_pid && (
                            <div style={{ fontSize: 10, color: c.textTertiary, fontFamily: fonts.mono }}>
                              PID: {entry.target_pid}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: '10px 8px' }}>
                          <span
                            style={{
                              padding: '2px 7px',
                              borderRadius: radii.sm,
                              fontSize: 10,
                              fontWeight: 600,
                              background:
                                entry.objective === 'efficiency'
                                  ? isLight
                                    ? '#dcfce7'
                                    : 'rgba(16, 185, 129, 0.15)'
                                  : isLight
                                  ? '#eff6ff'
                                  : 'rgba(99, 102, 241, 0.15)',
                              color:
                                entry.objective === 'efficiency'
                                  ? isLight
                                    ? '#15803d'
                                    : '#34d399'
                                  : isLight
                                  ? '#1d4ed8'
                                  : '#818cf8',
                            }}
                          >
                            {entry.objective === 'efficiency' ? 'Sweet Spot' : 'Deadline'}
                          </span>
                        </td>
                        <td style={{ padding: '10px 8px', fontFamily: fonts.mono }}>
                          {formatRuntime(entry.runtime_s)}
                        </td>
                        <td style={{ padding: '10px 8px', fontFamily: fonts.mono, color: c.textTertiary }}>
                          {stockW.toFixed(1)} W
                        </td>
                        <td style={{ padding: '10px 8px', fontFamily: fonts.mono, color: c.textSecondary }}>
                          {optW.toFixed(1)} W
                        </td>
                        <td
                          style={{
                            padding: '10px 8px',
                            fontFamily: fonts.mono,
                            fontWeight: 700,
                            color: isLight ? '#2563eb' : '#60a5fa',
                          }}
                        >
                          -{savedW.toFixed(1)} W
                        </td>
                        <td
                          style={{
                            padding: '10px 8px',
                            fontFamily: fonts.mono,
                            fontWeight: 700,
                            color: isLight ? '#059669' : '#34d399',
                          }}
                        >
                          {formatEnergy(entry.saved_energy_j)}
                        </td>
                        <td style={{ padding: '10px 8px' }}>
                          <span
                            style={{
                              display: 'inline-block',
                              padding: '3px 8px',
                              borderRadius: radii.sm,
                              fontSize: 11,
                              fontWeight: 700,
                              background: isLight ? '#dcfce7' : 'rgba(16, 185, 129, 0.15)',
                              color: isLight ? '#166534' : '#34d399',
                              fontFamily: fonts.mono,
                            }}
                          >
                            -{entry.saved_pct.toFixed(0)}%
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
