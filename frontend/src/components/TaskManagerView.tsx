import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { fetchUserProcesses, setProcessPriority, UserProcess } from '../api';
import { colors, fonts, fontFeatures, type, radii, card, sectionLabel } from '../design';

export const TaskManagerView: React.FC = () => {
  const [processes, setProcesses] = useState<UserProcess[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [manualTarget, setManualTarget] = useState<string>('');
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [isActing, setIsActing] = useState<boolean>(false);

  const loadProcesses = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetchUserProcesses(150);
      setProcesses(res.processes || []);
      setTotalCount(res.total || 0);
      setError(null);
    } catch (e: any) {
      setError(e?.message ?? 'Failed to load processes');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProcesses();
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      loadProcesses();
    }, 3500);
    return () => clearInterval(interval);
  }, [loadProcesses, autoRefresh]);

  const handleApplyPriority = async (
    target: { pid?: number; pattern?: string },
    policy: 'deprioritize_eco' | 'prioritize_fast' | 'restore_normal',
  ) => {
    try {
      setIsActing(true);
      const res = await setProcessPriority({ ...target, policy });
      const policyLabel =
        policy === 'deprioritize_eco'
          ? 'deprioritized to Zen 5c Eco Cores'
          : policy === 'prioritize_fast'
            ? 'prioritized to Zen 5 Fast Cores'
            : 'restored to All Cores';
      const name = target.pattern ? `All matching "${target.pattern}"` : `PID ${target.pid}`;
      setActionFeedback(`✓ ${name} ${policyLabel}.`);
      setTimeout(() => setActionFeedback(null), 5000);
      await loadProcesses();
    } catch (e: any) {
      setActionFeedback(`⚠️ Failed to set priority: ${e?.message ?? e}`);
      setTimeout(() => setActionFeedback(null), 6000);
    } finally {
      setIsActing(false);
    }
  };

  const filteredProcesses = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return processes;
    return processes.filter(
      (p) =>
        p.name.toLowerCase().includes(q) ||
        p.cmdline.toLowerCase().includes(q) ||
        String(p.pid).includes(q),
    );
  }, [processes, searchQuery]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 1160,
        margin: '0 auto',
        fontFamily: fonts.sans,
        fontFeatureSettings: fontFeatures,
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ ...type.display, color: colors.textPrimary }}>Task & Process Priority Manager</div>
          <div style={{ ...type.small, color: colors.textTertiary, marginTop: 4 }}>
            Control CPU core affinity and scheduling priority for running background tasks.
            Deprioritize heavy apps to Zen 5c eco cores so other work or benchmarks run at peak performance.
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, ...type.small, color: colors.textSecondary, cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              style={{ cursor: 'pointer' }}
            />
            Auto-refresh (3.5s)
          </label>
          <button
            disabled={loading}
            onClick={() => loadProcesses()}
            style={{
              padding: '6px 14px',
              borderRadius: radii.sm,
              border: `1px solid ${colors.border}`,
              background: colors.surfaceElevated,
              color: colors.textPrimary,
              cursor: loading ? 'wait' : 'pointer',
              font: 'inherit',
              fontSize: 12,
            }}
          >
            {loading ? 'Refreshing…' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {/* Info Card: Core Architecture Explainer */}
      <div
        style={{
          ...card,
          padding: 16,
          background: 'rgba(255,255,255,0.02)',
          border: `1px solid ${colors.border}`,
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 14,
        }}
      >
        <div style={{ borderLeft: `3px solid ${colors.series.fast}`, paddingLeft: 10 }}>
          <div style={{ ...type.smallMedium, color: colors.series.fast }}>⚡ Zen 5 Fast Cores (0, 2, 4, 6, 8, 10, 12, 14)</div>
          <div style={{ ...type.caption, color: colors.textTertiary, marginTop: 4 }}>
            Clocks up to 5.09 GHz. Maximum single-thread compute. Keep these free of background noise for fast runs.
          </div>
        </div>
        <div style={{ borderLeft: `3px solid ${colors.series.efficient}`, paddingLeft: 10 }}>
          <div style={{ ...type.smallMedium, color: colors.series.efficient }}>🌿 Zen 5c Eco Cores (1, 3, 5, 7, 9, 11, 13, 15)</div>
          <div style={{ ...type.caption, color: colors.textTertiary, marginTop: 4 }}>
            Clocks up to 3.51 GHz. High energy efficiency. Ideal for background browsers, compiles, and streaming without jitter.
          </div>
        </div>
        <div style={{ borderLeft: `3px solid #38bdf8`, paddingLeft: 10 }}>
          <div style={{ ...type.smallMedium, color: '#38bdf8' }}>🔒 Process Isolation via taskset -a</div>
          <div style={{ ...type.caption, color: colors.textTertiary, marginTop: 4 }}>
            Affinity applies to all threads in the process group instantly without requiring root privileges.
          </div>
        </div>
      </div>

      {/* Quick Target Action Bar */}
      <div style={{ ...card, padding: 16 }}>
        <div style={{ ...type.smallMedium, color: colors.textPrimary, marginBottom: 8 }}>
          Target Any Process by Name or PID
        </div>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            type="text"
            placeholder="e.g. brave, cargo, rustc, ffmpeg, 44436..."
            value={manualTarget}
            onChange={(e) => setManualTarget(e.target.value)}
            style={{
              flex: '1 1 240px',
              maxWidth: 360,
              padding: '7px 12px',
              borderRadius: radii.sm,
              border: `1px solid ${colors.border}`,
              background: colors.surfaceElevated,
              color: colors.textPrimary,
              fontFamily: fonts.sans,
              fontSize: 13,
              outline: 'none',
            }}
          />
          <button
            disabled={isActing || !manualTarget.trim()}
            onClick={() => {
              const val = manualTarget.trim();
              const asNum = parseInt(val, 10);
              const target = !Number.isNaN(asNum) && String(asNum) === val ? { pid: asNum } : { pattern: val };
              handleApplyPriority(target, 'deprioritize_eco');
            }}
            style={{
              padding: '7px 14px',
              borderRadius: radii.sm,
              border: `1px solid rgba(52, 211, 153, 0.4)`,
              background: 'rgba(52, 211, 153, 0.12)',
              color: '#34d399',
              fontWeight: 600,
              cursor: isActing || !manualTarget.trim() ? 'not-allowed' : 'pointer',
              font: 'inherit',
              fontSize: 12,
              opacity: !manualTarget.trim() ? 0.5 : 1,
            }}
          >
            🌿 Deprioritize to Eco Cores
          </button>
          <button
            disabled={isActing || !manualTarget.trim()}
            onClick={() => {
              const val = manualTarget.trim();
              const asNum = parseInt(val, 10);
              const target = !Number.isNaN(asNum) && String(asNum) === val ? { pid: asNum } : { pattern: val };
              handleApplyPriority(target, 'prioritize_fast');
            }}
            style={{
              padding: '7px 14px',
              borderRadius: radii.sm,
              border: `1px solid rgba(167, 139, 250, 0.4)`,
              background: 'rgba(167, 139, 250, 0.12)',
              color: '#c084fc',
              fontWeight: 600,
              cursor: isActing || !manualTarget.trim() ? 'not-allowed' : 'pointer',
              font: 'inherit',
              fontSize: 12,
              opacity: !manualTarget.trim() ? 0.5 : 1,
            }}
          >
            ⚡ Prioritize to Fast Cores
          </button>
          <button
            disabled={isActing || !manualTarget.trim()}
            onClick={() => {
              const val = manualTarget.trim();
              const asNum = parseInt(val, 10);
              const target = !Number.isNaN(asNum) && String(asNum) === val ? { pid: asNum } : { pattern: val };
              handleApplyPriority(target, 'restore_normal');
            }}
            style={{
              padding: '7px 14px',
              borderRadius: radii.sm,
              border: `1px solid ${colors.border}`,
              background: colors.surfaceElevated,
              color: colors.textSecondary,
              cursor: isActing || !manualTarget.trim() ? 'not-allowed' : 'pointer',
              font: 'inherit',
              fontSize: 12,
              opacity: !manualTarget.trim() ? 0.5 : 1,
            }}
          >
            ↺ Reset to All Cores
          </button>
        </div>
      </div>

      {/* Action Feedback Banner */}
      {actionFeedback && (
        <div
          style={{
            ...card,
            padding: 12,
            background: actionFeedback.startsWith('✓') ? 'rgba(52, 211, 153, 0.12)' : 'rgba(245, 158, 11, 0.12)',
            border: `1px solid ${actionFeedback.startsWith('✓') ? 'rgba(52, 211, 153, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
            ...type.smallMedium,
            color: actionFeedback.startsWith('✓') ? '#34d399' : colors.amber,
          }}
        >
          {actionFeedback}
        </div>
      )}

      {/* Filter / Search Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div style={{ ...sectionLabel, margin: 0 }}>
          Running User Processes ({filteredProcesses.length} / {totalCount})
        </div>
        <input
          type="text"
          placeholder="Filter processes..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            padding: '5px 10px',
            borderRadius: radii.sm,
            border: `1px solid ${colors.border}`,
            background: colors.surfaceElevated,
            color: colors.textPrimary,
            fontFamily: fonts.sans,
            fontSize: 12,
            outline: 'none',
            minWidth: 200,
          }}
        />
      </div>

      {/* Process Table */}
      <div style={{ ...card, padding: 0, overflow: 'hidden' }}>
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 12, fontFamily: fonts.sans }}>
            <thead>
              <tr style={{ background: colors.surfaceElevated, borderBottom: `1px solid ${colors.border}`, color: colors.textTertiary }}>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>PID</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>Process Name</th>
                <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'right' }}>CPU %</th>
                <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'right' }}>RAM %</th>
                <th style={{ padding: '10px 14px', fontWeight: 600 }}>Core Affinity</th>
                <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'center' }}>Nice</th>
                <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'right' }}>Quick Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredProcesses.map((p) => {
                const isEco = p.affinity_label.includes('Eco') || p.affinity_label.includes('Zen 5c');
                const isFast = p.affinity_label.includes('Fast') || p.affinity_label.includes('Zen 5');
                const affinityBadgeColor = isEco
                  ? '#34d399'
                  : isFast
                    ? '#c084fc'
                    : colors.textSecondary;

                return (
                  <tr
                    key={p.pid}
                    style={{
                      borderBottom: `1px solid ${colors.borderSubtle}`,
                      background: p.cpu_pct >= 5 ? 'rgba(255, 255, 255, 0.02)' : 'transparent',
                    }}
                  >
                    <td style={{ padding: '9px 14px', fontFamily: fonts.mono, color: colors.textTertiary }}>
                      {p.pid}
                    </td>
                    <td style={{ padding: '9px 14px' }}>
                      <div style={{ fontWeight: 600, color: colors.textPrimary }}>{p.name}</div>
                      <div style={{ ...type.caption, color: colors.textQuaternary, maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {p.cmdline}
                      </div>
                    </td>
                    <td
                      style={{
                        padding: '9px 14px',
                        textAlign: 'right',
                        fontFamily: fonts.mono,
                        fontWeight: p.cpu_pct >= 5 ? 700 : 400,
                        color: p.cpu_pct >= 20 ? colors.amber : p.cpu_pct >= 5 ? colors.textPrimary : colors.textSecondary,
                      }}
                    >
                      {p.cpu_pct.toFixed(1)}%
                    </td>
                    <td style={{ padding: '9px 14px', textAlign: 'right', fontFamily: fonts.mono, color: colors.textTertiary }}>
                      {p.mem_pct.toFixed(1)}%
                    </td>
                    <td style={{ padding: '9px 14px' }}>
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '2px 8px',
                          borderRadius: radii.sm,
                          fontSize: 11,
                          fontFamily: fonts.mono,
                          fontWeight: 500,
                          background: `${affinityBadgeColor}18`,
                          border: `1px solid ${affinityBadgeColor}44`,
                          color: affinityBadgeColor,
                        }}
                      >
                        {p.affinity_label}
                      </span>
                    </td>
                    <td style={{ padding: '9px 14px', textAlign: 'center', fontFamily: fonts.mono, color: colors.textTertiary }}>
                      {p.nice}
                    </td>
                    <td style={{ padding: '9px 14px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: 6 }}>
                        <button
                          title="Pin all threads to Zen 5c efficiency cores (odd CPUs) and set nice +15"
                          disabled={isActing}
                          onClick={() => handleApplyPriority({ pid: p.pid }, 'deprioritize_eco')}
                          style={{
                            padding: '3px 8px',
                            borderRadius: radii.sm,
                            border: `1px solid ${isEco ? '#34d399' : colors.border}`,
                            background: isEco ? '#34d39920' : colors.surfaceElevated,
                            color: '#34d399',
                            cursor: isActing ? 'wait' : 'pointer',
                            fontSize: 11,
                            fontWeight: 600,
                          }}
                        >
                          🌿 Eco
                        </button>
                        <button
                          title="Pin all threads to Zen 5 fast cores (even CPUs) and set normal priority"
                          disabled={isActing}
                          onClick={() => handleApplyPriority({ pid: p.pid }, 'prioritize_fast')}
                          style={{
                            padding: '3px 8px',
                            borderRadius: radii.sm,
                            border: `1px solid ${isFast ? '#c084fc' : colors.border}`,
                            background: isFast ? '#c084fc20' : colors.surfaceElevated,
                            color: '#c084fc',
                            cursor: isActing ? 'wait' : 'pointer',
                            fontSize: 11,
                            fontWeight: 600,
                          }}
                        >
                          ⚡ Fast
                        </button>
                        <button
                          title="Reset affinity to all 16 cores"
                          disabled={isActing}
                          onClick={() => handleApplyPriority({ pid: p.pid }, 'restore_normal')}
                          style={{
                            padding: '3px 8px',
                            borderRadius: radii.sm,
                            border: `1px solid ${colors.border}`,
                            background: colors.surfaceElevated,
                            color: colors.textTertiary,
                            cursor: isActing ? 'wait' : 'pointer',
                            fontSize: 11,
                          }}
                        >
                          ↺ Normal
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {filteredProcesses.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ padding: '2rem 14px', textAlign: 'center', color: colors.textTertiary }}>
                    No processes matched your filter.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
