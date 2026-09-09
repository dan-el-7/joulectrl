import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { fetchUserProcesses, setProcessPriority, UserProcess } from '../api';
import { fonts, fontFeatures, radii } from '../design';

interface ThemePalette {
  canvasBg: string;
  columnBg: string;
  columnBorder: string;
  columnHeaderBg: string;
  cardBg: string;
  cardBorder: string;
  cardHoverBorder: string;
  cardShadow: string;
  textPrimary: string;
  textSecondary: string;
  textTertiary: string;
  textQuaternary: string;
  badgeBg: string;
  badgeBorder: string;
  inputBg: string;
  inputBorder: string;
}

const THEMES: Record<'dark' | 'light', ThemePalette> = {
  dark: {
    canvasBg: 'transparent',
    columnBg: 'rgba(255, 255, 255, 0.02)',
    columnBorder: 'rgba(255, 255, 255, 0.07)',
    columnHeaderBg: 'rgba(255, 255, 255, 0.04)',
    cardBg: '#141516',
    cardBorder: 'rgba(255, 255, 255, 0.08)',
    cardHoverBorder: 'rgba(113, 112, 255, 0.4)',
    cardShadow: '0 2px 4px rgba(0, 0, 0, 0.3)',
    textPrimary: '#f7f8f8',
    textSecondary: '#d0d6e0',
    textTertiary: '#8a8f98',
    textQuaternary: '#62666d',
    badgeBg: 'rgba(255, 255, 255, 0.06)',
    badgeBorder: 'rgba(255, 255, 255, 0.1)',
    inputBg: '#18191a',
    inputBorder: 'rgba(255, 255, 255, 0.12)',
  },
  light: {
    canvasBg: '#f8fafc',
    columnBg: '#f1f5f9',
    columnBorder: '#e2e8f0',
    columnHeaderBg: '#e2e8f0',
    cardBg: '#ffffff',
    cardBorder: '#e2e8f0',
    cardHoverBorder: '#6366f1',
    cardShadow: '0 1px 3px rgba(0, 0, 0, 0.07), 0 1px 2px rgba(0, 0, 0, 0.04)',
    textPrimary: '#0f172a',
    textSecondary: '#334155',
    textTertiary: '#64748b',
    textQuaternary: '#94a3b8',
    badgeBg: '#f8fafc',
    badgeBorder: '#cbd5e1',
    inputBg: '#ffffff',
    inputBorder: '#cbd5e1',
  },
};

const COMMON_APPS = [
  { name: 'Brave Browser', pattern: 'brave', icon: '🦁' },
  { name: 'Google Chrome', pattern: 'chrome', icon: '🌐' },
  { name: 'VS Code', pattern: 'code', icon: '💻' },
  { name: 'Cargo / Rust', pattern: 'cargo', icon: '🦀' },
  { name: 'Spotify', pattern: 'spotify', icon: '🎵' },
  { name: 'Discord', pattern: 'discord', icon: '💬' },
  { name: 'Steam', pattern: 'steam', icon: '🎮' },
  { name: 'FFmpeg', pattern: 'ffmpeg', icon: '🎬' },
];

export const TaskManagerView: React.FC = () => {
  const [processes, setProcesses] = useState<UserProcess[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [manualTarget, setManualTarget] = useState<string>('');
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);
  const [actionFeedback, setActionFeedback] = useState<string | null>(null);
  const [isActing, setIsActing] = useState<boolean>(false);

  // View & Theme state
  const [viewMode, setViewMode] = useState<'board' | 'table'>(() => {
    return (localStorage.getItem('joulectrl_tasks_view') as any) || 'board';
  });
  const [theme, setTheme] = useState<'dark' | 'light'>(() => {
    return (localStorage.getItem('joulectrl_theme') as any) || 'dark';
  });

  // Modal / Add task to column state
  const [activeAddColumn, setActiveAddColumn] = useState<'fast' | 'eco' | null>(null);

  const t = THEMES[theme];

  const handleToggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    localStorage.setItem('joulectrl_theme', next);
  };

  const handleToggleView = (mode: 'board' | 'table') => {
    setViewMode(mode);
    localStorage.setItem('joulectrl_tasks_view', mode);
  };

  const loadProcesses = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetchUserProcesses(150);
      setProcesses(res.processes || []);
      setTotalCount(res.total || 0);
    } catch (e: any) {
      console.warn('Failed to load processes:', e);
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
      await setProcessPriority({ ...target, policy });
      const policyLabel =
        policy === 'deprioritize_eco'
          ? 'pinned to Zen 5c Eco Cores (Nice +15)'
          : policy === 'prioritize_fast'
            ? 'pinned to Zen 5 Fast Cores (Nice 0, Boost ON)'
            : 'restored to All 16 Cores (Normal scheduling)';
      const name = target.pattern ? `All matching "${target.pattern}"` : `PID ${target.pid}`;
      setActionFeedback(`✓ ${name} ${policyLabel}`);
      setTimeout(() => setActionFeedback(null), 4500);
      await loadProcesses();
    } catch (e: any) {
      setActionFeedback(`⚠️ Priority error: ${e?.message ?? e}`);
      setTimeout(() => setActionFeedback(null), 5500);
    } finally {
      setIsActing(false);
      setActiveAddColumn(null);
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

  const { fastProcs, normalProcs, ecoProcs } = useMemo(() => {
    const fast: UserProcess[] = [];
    const normal: UserProcess[] = [];
    const eco: UserProcess[] = [];

    for (const p of filteredProcesses) {
      const label = p.affinity_label || '';
      if (label.includes('Eco') || label.includes('Zen 5c')) {
        eco.push(p);
      } else if (label.includes('Fast') || label.includes('Zen 5')) {
        fast.push(p);
      } else {
        normal.push(p);
      }
    }

    const byCpu = (a: UserProcess, b: UserProcess) => b.cpu_pct - a.cpu_pct;
    return {
      fastProcs: fast.sort(byCpu),
      normalProcs: normal.sort(byCpu),
      ecoProcs: eco.sort(byCpu),
    };
  }, [filteredProcesses]);

  const handleDragStart = (e: React.DragEvent, pid: number) => {
    e.dataTransfer.setData('text/plain', String(pid));
  };

  const handleDrop = (e: React.DragEvent, targetPolicy: 'deprioritize_eco' | 'prioritize_fast' | 'restore_normal') => {
    e.preventDefault();
    const pidStr = e.dataTransfer.getData('text/plain');
    if (!pidStr) return;
    const pid = parseInt(pidStr, 10);
    if (!Number.isNaN(pid)) {
      handleApplyPriority({ pid }, targetPolicy);
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        maxWidth: 1240,
        margin: '0 auto',
        fontFamily: fonts.sans,
        fontFeatureSettings: fontFeatures,
        padding: theme === 'light' ? '14px 18px' : 0,
        background: t.canvasBg,
        borderRadius: radii.lg,
        transition: 'background 0.2s ease',
      }}
    >
      {/* Top Bar: Title + View Switcher + Theme Switcher */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 20, fontWeight: 700, color: t.textPrimary, letterSpacing: '-0.3px' }}>
              Task Priority Manager
            </span>
            <span
              style={{
                fontSize: 11,
                fontFamily: fonts.mono,
                padding: '2px 8px',
                borderRadius: radii.full,
                background: t.badgeBg,
                border: `1px solid ${t.badgeBorder}`,
                color: t.textSecondary,
              }}
            >
              {totalCount} Active Tasks
            </span>
          </div>
          <div style={{ fontSize: 13, color: t.textTertiary, marginTop: 4 }}>
            Aceternity-style affinity board: push background tabs to Zen 5c eco cores or pin critical apps to Zen 5 fast cores.
          </div>
        </div>

        {/* Action Controls: Search, View Mode, Theme Toggle */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {/* Search bar */}
          <input
            type="text"
            placeholder="Search processes..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              padding: '6px 12px',
              borderRadius: radii.md,
              border: `1px solid ${t.inputBorder}`,
              background: t.inputBg,
              color: t.textPrimary,
              fontFamily: fonts.sans,
              fontSize: 12,
              outline: 'none',
              width: 170,
            }}
          />

          {/* View Mode Toggle: Board vs Table */}
          <div
            style={{
              display: 'flex',
              background: t.columnBg,
              border: `1px solid ${t.columnBorder}`,
              borderRadius: radii.md,
              padding: 2,
            }}
          >
            <button
              onClick={() => handleToggleView('board')}
              style={{
                padding: '4px 10px',
                borderRadius: radii.sm,
                border: 'none',
                background: viewMode === 'board' ? t.cardBg : 'transparent',
                color: viewMode === 'board' ? t.textPrimary : t.textTertiary,
                boxShadow: viewMode === 'board' ? t.cardShadow : 'none',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
              }}
            >
              <span>▦</span> Board
            </button>
            <button
              onClick={() => handleToggleView('table')}
              style={{
                padding: '4px 10px',
                borderRadius: radii.sm,
                border: 'none',
                background: viewMode === 'table' ? t.cardBg : 'transparent',
                color: viewMode === 'table' ? t.textPrimary : t.textTertiary,
                boxShadow: viewMode === 'table' ? t.cardShadow : 'none',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 5,
              }}
            >
              <span>☰</span> Table
            </button>
          </div>

          {/* Theme Switcher: Dark vs Light */}
          <button
            onClick={handleToggleTheme}
            style={{
              padding: '5px 12px',
              borderRadius: radii.md,
              border: `1px solid ${t.columnBorder}`,
              background: t.cardBg,
              color: t.textPrimary,
              boxShadow: t.cardShadow,
              fontSize: 12,
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
            title={theme === 'dark' ? 'Switch to Aceternity Light theme' : 'Switch to Dark theme'}
          >
            {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
          </button>

          {/* Refresh Button */}
          <button
            disabled={loading}
            onClick={() => loadProcesses()}
            style={{
              padding: '5px 12px',
              borderRadius: radii.md,
              border: `1px solid ${t.columnBorder}`,
              background: t.cardBg,
              color: t.textSecondary,
              cursor: loading ? 'wait' : 'pointer',
              fontSize: 12,
            }}
          >
            {loading ? 'Refreshing…' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {/* Common Applications Quick Chips */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          flexWrap: 'wrap',
          background: t.columnBg,
          padding: '8px 14px',
          borderRadius: radii.md,
          border: `1px solid ${t.columnBorder}`,
        }}
      >
        <span style={{ fontSize: 11, fontWeight: 600, color: t.textTertiary, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          Quick Pin:
        </span>
        {COMMON_APPS.map((app) => (
          <div
            key={app.pattern}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '2px 8px',
              borderRadius: radii.sm,
              background: t.cardBg,
              border: `1px solid ${t.cardBorder}`,
              fontSize: 11,
              color: t.textSecondary,
            }}
          >
            <span>{app.icon}</span>
            <span style={{ fontWeight: 500 }}>{app.name}</span>
            <button
              title={`Pin ${app.name} to Zen 5c Eco Cores`}
              disabled={isActing}
              onClick={() => handleApplyPriority({ pattern: app.pattern }, 'deprioritize_eco')}
              style={{
                background: 'none',
                border: 'none',
                color: '#10b981',
                cursor: 'pointer',
                padding: '0 2px',
                fontSize: 10,
                fontWeight: 700,
              }}
            >
              🌿 Eco
            </button>
            <span style={{ color: t.textQuaternary }}>|</span>
            <button
              title={`Pin ${app.name} to Zen 5 Fast Cores`}
              disabled={isActing}
              onClick={() => handleApplyPriority({ pattern: app.pattern }, 'prioritize_fast')}
              style={{
                background: 'none',
                border: 'none',
                color: '#8b5cf6',
                cursor: 'pointer',
                padding: '0 2px',
                fontSize: 10,
                fontWeight: 700,
              }}
            >
              ⚡ Fast
            </button>
          </div>
        ))}
      </div>

      {/* Action Feedback Banner */}
      {actionFeedback && (
        <div
          style={{
            padding: '10px 14px',
            borderRadius: radii.md,
            background: actionFeedback.startsWith('✓') ? 'rgba(16, 185, 129, 0.12)' : 'rgba(245, 158, 11, 0.12)',
            border: `1px solid ${actionFeedback.startsWith('✓') ? 'rgba(16, 185, 129, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
            color: actionFeedback.startsWith('✓') ? '#10b981' : '#f59e0b',
            fontSize: 12,
            fontWeight: 600,
          }}
        >
          {actionFeedback}
        </div>
      )}

      {/* Manual Target Bar */}
      <div
        style={{
          display: 'flex',
          gap: 10,
          alignItems: 'center',
          flexWrap: 'wrap',
          background: t.cardBg,
          padding: '10px 14px',
          borderRadius: radii.md,
          border: `1px solid ${t.cardBorder}`,
          boxShadow: t.cardShadow,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 600, color: t.textPrimary }}>
          Custom Target:
        </span>
        <input
          type="text"
          placeholder="Process name or PID (e.g. rustc, code, ffmpeg, 44436)..."
          value={manualTarget}
          onChange={(e) => setManualTarget(e.target.value)}
          style={{
            flex: '1 1 220px',
            maxWidth: 340,
            padding: '6px 12px',
            borderRadius: radii.sm,
            border: `1px solid ${t.inputBorder}`,
            background: t.inputBg,
            color: t.textPrimary,
            fontSize: 12,
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
            padding: '6px 12px',
            borderRadius: radii.sm,
            border: '1px solid rgba(16, 185, 129, 0.4)',
            background: 'rgba(16, 185, 129, 0.1)',
            color: '#10b981',
            fontWeight: 600,
            fontSize: 11,
            cursor: isActing || !manualTarget.trim() ? 'not-allowed' : 'pointer',
          }}
        >
          🌿 Push to Eco Cores
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
            padding: '6px 12px',
            borderRadius: radii.sm,
            border: '1px solid rgba(139, 92, 246, 0.4)',
            background: 'rgba(139, 92, 246, 0.1)',
            color: '#8b5cf6',
            fontWeight: 600,
            fontSize: 11,
            cursor: isActing || !manualTarget.trim() ? 'not-allowed' : 'pointer',
          }}
        >
          ⚡ Pin to Fast Cores
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
            padding: '6px 12px',
            borderRadius: radii.sm,
            border: `1px solid ${t.cardBorder}`,
            background: t.columnBg,
            color: t.textSecondary,
            fontSize: 11,
            cursor: isActing || !manualTarget.trim() ? 'not-allowed' : 'pointer',
          }}
        >
          ↺ Reset to Normal
        </button>
      </div>

      {/* KANBAN BOARD VIEW */}
      {viewMode === 'board' && (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
            gap: 16,
            alignItems: 'flex-start',
          }}
        >
          {/* Column 1: Zen 5c Eco Cores (Background) */}
          <KanbanColumn
            title="Zen 5c Eco Cores"
            badgeLabel="Eco Background"
            badgeColor="#10b981"
            icon="🌿"
            subtext="Cores 1,3,5,7,9,11,13,15 · Nice +15 · Zero interference"
            count={ecoProcs.length}
            processes={ecoProcs}
            t={t}
            columnPolicy="deprioritize_eco"
            isActing={isActing}
            onDrop={(e) => handleDrop(e, 'deprioritize_eco')}
            onDragStart={handleDragStart}
            onMoveToNormal={(pid) => handleApplyPriority({ pid }, 'restore_normal')}
            onMoveToFast={(pid) => handleApplyPriority({ pid }, 'prioritize_fast')}
            onAddProcess={() => setActiveAddColumn(activeAddColumn === 'eco' ? null : 'eco')}
            isAddOpen={activeAddColumn === 'eco'}
            onConfirmAdd={(pattern) => handleApplyPriority({ pattern }, 'deprioritize_eco')}
          />

          {/* Column 2: Normal / Unmanaged (All Cores) */}
          <KanbanColumn
            title="All 16 Cores"
            badgeLabel="Default / Normal"
            badgeColor={t.textTertiary}
            icon="⚪"
            subtext="Cores 0-15 · Nice 0 · Default Linux scheduler"
            count={normalProcs.length}
            processes={normalProcs}
            t={t}
            columnPolicy="restore_normal"
            isActing={isActing}
            onDrop={(e) => handleDrop(e, 'restore_normal')}
            onDragStart={handleDragStart}
            onMoveToEco={(pid) => handleApplyPriority({ pid }, 'deprioritize_eco')}
            onMoveToFast={(pid) => handleApplyPriority({ pid }, 'prioritize_fast')}
          />

          {/* Column 3: Zen 5 Fast Cores (Top Priority) */}
          <KanbanColumn
            title="Zen 5 Fast Cores"
            badgeLabel="Top Priority"
            badgeColor="#8b5cf6"
            icon="⚡"
            subtext="Cores 0,2,4,6,8,10,12,14 · Nice 0 · Max boost clocks"
            count={fastProcs.length}
            processes={fastProcs}
            t={t}
            columnPolicy="prioritize_fast"
            isActing={isActing}
            onDrop={(e) => handleDrop(e, 'prioritize_fast')}
            onDragStart={handleDragStart}
            onMoveToNormal={(pid) => handleApplyPriority({ pid }, 'restore_normal')}
            onMoveToEco={(pid) => handleApplyPriority({ pid }, 'deprioritize_eco')}
            onAddProcess={() => setActiveAddColumn(activeAddColumn === 'fast' ? null : 'fast')}
            isAddOpen={activeAddColumn === 'fast'}
            onConfirmAdd={(pattern) => handleApplyPriority({ pattern }, 'prioritize_fast')}
          />
        </div>
      )}

      {/* TABLE VIEW */}
      {viewMode === 'table' && (
        <div
          style={{
            background: t.cardBg,
            borderRadius: radii.md,
            border: `1px solid ${t.cardBorder}`,
            overflow: 'hidden',
            boxShadow: t.cardShadow,
          }}
        >
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 12 }}>
              <thead>
                <tr style={{ background: t.columnHeaderBg, borderBottom: `1px solid ${t.cardBorder}`, color: t.textTertiary }}>
                  <th style={{ padding: '10px 14px', fontWeight: 600 }}>PID</th>
                  <th style={{ padding: '10px 14px', fontWeight: 600 }}>Process Name</th>
                  <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'right' }}>CPU %</th>
                  <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'right' }}>RAM %</th>
                  <th style={{ padding: '10px 14px', fontWeight: 600 }}>Core Affinity</th>
                  <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'center' }}>Nice</th>
                  <th style={{ padding: '10px 14px', fontWeight: 600, textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredProcesses.map((p) => {
                  const isEco = p.affinity_label.includes('Eco') || p.affinity_label.includes('Zen 5c');
                  const isFast = p.affinity_label.includes('Fast') || p.affinity_label.includes('Zen 5');
                  const affinityBadgeColor = isEco ? '#10b981' : isFast ? '#8b5cf6' : t.textTertiary;

                  return (
                    <tr
                      key={p.pid}
                      style={{
                        borderBottom: `1px solid ${t.cardBorder}`,
                        background: p.cpu_pct >= 5 ? (theme === 'dark' ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)') : 'transparent',
                      }}
                    >
                      <td style={{ padding: '8px 14px', fontFamily: fonts.mono, color: t.textTertiary }}>
                        {p.pid}
                      </td>
                      <td style={{ padding: '8px 14px' }}>
                        <div style={{ fontWeight: 600, color: t.textPrimary }}>{p.name}</div>
                        <div style={{ fontSize: 11, color: t.textQuaternary, maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {p.cmdline}
                        </div>
                      </td>
                      <td
                        style={{
                          padding: '8px 14px',
                          textAlign: 'right',
                          fontFamily: fonts.mono,
                          fontWeight: p.cpu_pct >= 5 ? 700 : 400,
                          color: p.cpu_pct >= 20 ? '#f59e0b' : p.cpu_pct >= 5 ? t.textPrimary : t.textSecondary,
                        }}
                      >
                        {p.cpu_pct.toFixed(1)}%
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'right', fontFamily: fonts.mono, color: t.textTertiary }}>
                        {p.mem_pct.toFixed(1)}%
                      </td>
                      <td style={{ padding: '8px 14px' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            padding: '2px 8px',
                            borderRadius: radii.sm,
                            fontSize: 11,
                            fontFamily: fonts.mono,
                            fontWeight: 500,
                            background: `${affinityBadgeColor}15`,
                            border: `1px solid ${affinityBadgeColor}40`,
                            color: affinityBadgeColor,
                          }}
                        >
                          {p.affinity_label}
                        </span>
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'center', fontFamily: fonts.mono, color: t.textTertiary }}>
                        {p.nice}
                      </td>
                      <td style={{ padding: '8px 14px', textAlign: 'right' }}>
                        <div style={{ display: 'inline-flex', gap: 6 }}>
                          <button
                            disabled={isActing}
                            onClick={() => handleApplyPriority({ pid: p.pid }, 'deprioritize_eco')}
                            style={{
                              padding: '3px 8px',
                              borderRadius: radii.sm,
                              border: `1px solid ${isEco ? '#10b981' : t.cardBorder}`,
                              background: isEco ? '#10b98120' : t.columnBg,
                              color: '#10b981',
                              cursor: isActing ? 'wait' : 'pointer',
                              fontSize: 11,
                              fontWeight: 600,
                            }}
                          >
                            🌿 Eco
                          </button>
                          <button
                            disabled={isActing}
                            onClick={() => handleApplyPriority({ pid: p.pid }, 'prioritize_fast')}
                            style={{
                              padding: '3px 8px',
                              borderRadius: radii.sm,
                              border: `1px solid ${isFast ? '#8b5cf6' : t.cardBorder}`,
                              background: isFast ? '#8b5cf620' : t.columnBg,
                              color: '#8b5cf6',
                              cursor: isActing ? 'wait' : 'pointer',
                              fontSize: 11,
                              fontWeight: 600,
                            }}
                          >
                            ⚡ Fast
                          </button>
                          <button
                            disabled={isActing}
                            onClick={() => handleApplyPriority({ pid: p.pid }, 'restore_normal')}
                            style={{
                              padding: '3px 8px',
                              borderRadius: radii.sm,
                              border: `1px solid ${t.cardBorder}`,
                              background: t.columnBg,
                              color: t.textTertiary,
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
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

interface KanbanColumnProps {
  title: string;
  badgeLabel: string;
  badgeColor: string;
  icon: string;
  subtext: string;
  count: number;
  processes: UserProcess[];
  t: ThemePalette;
  columnPolicy: 'deprioritize_eco' | 'prioritize_fast' | 'restore_normal';
  isActing: boolean;
  onDrop: (e: React.DragEvent) => void;
  onDragStart: (e: React.DragEvent, pid: number) => void;
  onMoveToEco?: (pid: number) => void;
  onMoveToFast?: (pid: number) => void;
  onMoveToNormal?: (pid: number) => void;
  onAddProcess?: () => void;
  isAddOpen?: boolean;
  onConfirmAdd?: (pattern: string) => void;
}

const KanbanColumn: React.FC<KanbanColumnProps> = ({
  title,
  badgeColor,
  icon,
  subtext,
  count,
  processes,
  t,
  isActing,
  onDrop,
  onDragStart,
  onMoveToEco,
  onMoveToFast,
  onMoveToNormal,
  onAddProcess,
  isAddOpen,
  onConfirmAdd,
}) => {
  const [inputPattern, setInputPattern] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setIsDragOver(true);
      }}
      onDragLeave={() => setIsDragOver(false)}
      onDrop={(e) => {
        setIsDragOver(false);
        onDrop(e);
      }}
      style={{
        background: t.columnBg,
        borderRadius: radii.lg,
        border: `1px solid ${isDragOver ? badgeColor : t.columnBorder}`,
        display: 'flex',
        flexDirection: 'column',
        minHeight: 480,
        boxShadow: isDragOver ? `0 0 12px ${badgeColor}33` : 'none',
        transition: 'all 0.15s ease',
        overflow: 'hidden',
      }}
    >
      {/* Column Header */}
      <div
        style={{
          padding: '12px 14px',
          background: t.columnHeaderBg,
          borderBottom: `1px solid ${t.columnBorder}`,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 14 }}>{icon}</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: t.textPrimary }}>
              {title}
            </span>
            <span
              style={{
                fontSize: 11,
                fontFamily: fonts.mono,
                fontWeight: 600,
                padding: '1px 7px',
                borderRadius: radii.full,
                background: `${badgeColor}18`,
                border: `1px solid ${badgeColor}40`,
                color: badgeColor,
              }}
            >
              {count}
            </span>
          </div>
          <div style={{ fontSize: 11, color: t.textQuaternary, marginTop: 3 }}>
            {subtext}
          </div>
        </div>

        {onAddProcess && (
          <button
            onClick={onAddProcess}
            title={`Add process to ${title}`}
            style={{
              padding: '3px 8px',
              borderRadius: radii.sm,
              border: `1px solid ${t.cardBorder}`,
              background: isAddOpen ? `${badgeColor}20` : t.cardBg,
              color: isAddOpen ? badgeColor : t.textSecondary,
              cursor: 'pointer',
              fontSize: 11,
              fontWeight: 600,
            }}
          >
            {isAddOpen ? '✕' : '+ Add'}
          </button>
        )}
      </div>

      {/* Add Task Popover / Inline Input */}
      {isAddOpen && onConfirmAdd && (
        <div
          style={{
            padding: '10px 14px',
            background: t.cardBg,
            borderBottom: `1px solid ${t.cardBorder}`,
            display: 'flex',
            gap: 8,
          }}
        >
          <input
            type="text"
            placeholder="App name (e.g. brave, cargo, slack)..."
            value={inputPattern}
            onChange={(e) => setInputPattern(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && inputPattern.trim()) {
                onConfirmAdd(inputPattern.trim());
                setInputPattern('');
              }
            }}
            style={{
              flex: 1,
              padding: '5px 8px',
              borderRadius: radii.sm,
              border: `1px solid ${t.inputBorder}`,
              background: t.inputBg,
              color: t.textPrimary,
              fontSize: 11,
              outline: 'none',
            }}
          />
          <button
            disabled={!inputPattern.trim()}
            onClick={() => {
              if (inputPattern.trim()) {
                onConfirmAdd(inputPattern.trim());
                setInputPattern('');
              }
            }}
            style={{
              padding: '5px 10px',
              borderRadius: radii.sm,
              border: 'none',
              background: badgeColor,
              color: '#ffffff',
              fontSize: 11,
              fontWeight: 600,
              cursor: inputPattern.trim() ? 'pointer' : 'not-allowed',
            }}
          >
            Pin
          </button>
        </div>
      )}

      {/* Process Cards Container */}
      <div
        style={{
          padding: 12,
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          flex: 1,
          overflowY: 'auto',
          maxHeight: 640,
        }}
      >
        {processes.length === 0 ? (
          <div
            style={{
              padding: '2.5rem 1rem',
              textAlign: 'center',
              color: t.textQuaternary,
              fontSize: 12,
              fontStyle: 'italic',
            }}
          >
            No processes currently in this tier.
            <div style={{ marginTop: 4, fontSize: 11 }}>Drag cards here or click "+ Add".</div>
          </div>
        ) : (
          processes.map((p) => (
            <ProcessCard
              key={p.pid}
              proc={p}
              t={t}
              badgeColor={badgeColor}
              isActing={isActing}
              onDragStart={(e) => onDragStart(e, p.pid)}
              onMoveToEco={onMoveToEco ? () => onMoveToEco(p.pid) : undefined}
              onMoveToFast={onMoveToFast ? () => onMoveToFast(p.pid) : undefined}
              onMoveToNormal={onMoveToNormal ? () => onMoveToNormal(p.pid) : undefined}
            />
          ))
        )}
      </div>
    </div>
  );
};

interface ProcessCardProps {
  proc: UserProcess;
  t: ThemePalette;
  badgeColor: string;
  isActing: boolean;
  onDragStart: (e: React.DragEvent) => void;
  onMoveToEco?: () => void;
  onMoveToFast?: () => void;
  onMoveToNormal?: () => void;
}

const ProcessCard: React.FC<ProcessCardProps> = ({
  proc,
  t,
  badgeColor,
  isActing,
  onDragStart,
  onMoveToEco,
  onMoveToFast,
  onMoveToNormal,
}) => {
  const [hovered, setHovered] = useState(false);

  const cpuColor = proc.cpu_pct >= 20 ? '#f59e0b' : proc.cpu_pct >= 5 ? t.textPrimary : t.textSecondary;

  return (
    <div
      draggable
      onDragStart={onDragStart}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: t.cardBg,
        borderRadius: radii.md,
        border: `1px solid ${hovered ? t.cardHoverBorder : t.cardBorder}`,
        boxShadow: hovered ? '0 4px 12px rgba(0, 0, 0, 0.08)' : t.cardShadow,
        padding: '10px 12px',
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        cursor: 'grab',
        transition: 'all 0.15s ease',
        transform: hovered ? 'translateY(-1px)' : 'none',
      }}
    >
      {/* Card Header: PID Badge (like ACE-179) + CPU pill */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              fontSize: 10,
              fontFamily: fonts.mono,
              fontWeight: 600,
              padding: '1px 6px',
              borderRadius: radii.xs,
              background: t.badgeBg,
              border: `1px solid ${t.badgeBorder}`,
              color: t.textTertiary,
            }}
          >
            PID {proc.pid}
          </span>
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: '50%',
              backgroundColor: proc.cpu_pct > 0.5 ? badgeColor : t.textQuaternary,
            }}
          />
        </div>

        {/* CPU % metric badge */}
        <span
          style={{
            fontSize: 11,
            fontFamily: fonts.mono,
            fontWeight: 700,
            color: cpuColor,
          }}
        >
          {proc.cpu_pct.toFixed(1)}% CPU
        </span>
      </div>

      {/* Process Title & Command preview */}
      <div>
        <div style={{ fontSize: 13, fontWeight: 600, color: t.textPrimary, lineHeight: 1.3 }}>
          {proc.name}
        </div>
        <div
          title={proc.cmdline}
          style={{
            fontSize: 11,
            color: t.textQuaternary,
            lineHeight: 1.4,
            marginTop: 2,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {proc.cmdline}
        </div>
      </div>

      {/* Metrics Row: RAM, Nice, Affinity */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <span
          style={{
            fontSize: 10,
            fontFamily: fonts.mono,
            padding: '2px 6px',
            borderRadius: radii.xs,
            background: t.badgeBg,
            border: `1px solid ${t.badgeBorder}`,
            color: t.textTertiary,
          }}
        >
          RAM: {proc.mem_pct.toFixed(1)}%
        </span>
        <span
          style={{
            fontSize: 10,
            fontFamily: fonts.mono,
            padding: '2px 6px',
            borderRadius: radii.xs,
            background: t.badgeBg,
            border: `1px solid ${t.badgeBorder}`,
            color: t.textTertiary,
          }}
        >
          Nice: {proc.nice}
        </span>
        <span
          style={{
            fontSize: 10,
            fontFamily: fonts.mono,
            padding: '2px 6px',
            borderRadius: radii.xs,
            background: `${badgeColor}15`,
            border: `1px solid ${badgeColor}35`,
            color: badgeColor,
            maxWidth: 120,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
          title={proc.affinity_label}
        >
          {proc.affinity_label}
        </span>
      </div>

      {/* Quick Move Action Buttons */}
      <div
        style={{
          display: 'flex',
          gap: 6,
          justifyContent: 'flex-end',
          paddingTop: 4,
          borderTop: `1px solid ${t.cardBorder}`,
        }}
      >
        {onMoveToEco && (
          <button
            disabled={isActing}
            onClick={(e) => {
              e.stopPropagation();
              onMoveToEco();
            }}
            title="Move to Zen 5c Eco Cores (Nice +15)"
            style={{
              padding: '3px 8px',
              borderRadius: radii.xs,
              border: `1px solid ${t.cardBorder}`,
              background: t.columnBg,
              color: '#10b981',
              fontSize: 10,
              fontWeight: 600,
              cursor: isActing ? 'wait' : 'pointer',
            }}
          >
            🌿 Eco
          </button>
        )}
        {onMoveToNormal && (
          <button
            disabled={isActing}
            onClick={(e) => {
              e.stopPropagation();
              onMoveToNormal();
            }}
            title="Restore to All 16 Cores (Normal scheduling)"
            style={{
              padding: '3px 8px',
              borderRadius: radii.xs,
              border: `1px solid ${t.cardBorder}`,
              background: t.columnBg,
              color: t.textTertiary,
              fontSize: 10,
              cursor: isActing ? 'wait' : 'pointer',
            }}
          >
            ↺ Normal
          </button>
        )}
        {onMoveToFast && (
          <button
            disabled={isActing}
            onClick={(e) => {
              e.stopPropagation();
              onMoveToFast();
            }}
            title="Prioritize to Zen 5 Fast Cores (Max compute)"
            style={{
              padding: '3px 8px',
              borderRadius: radii.xs,
              border: `1px solid ${t.cardBorder}`,
              background: t.columnBg,
              color: '#8b5cf6',
              fontSize: 10,
              fontWeight: 600,
              cursor: isActing ? 'wait' : 'pointer',
            }}
          >
            ⚡ Fast
          </button>
        )}
      </div>
    </div>
  );
};
