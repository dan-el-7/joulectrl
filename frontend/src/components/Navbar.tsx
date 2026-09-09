import React from 'react';

interface NavbarProps {
  activeTab: 'setup' | 'explorer' | 'validation' | 'watch';
  onSelectTab: (tab: 'setup' | 'explorer' | 'validation' | 'watch') => void;
  restorationStatus: string;
  onEmergencyRestore: () => void;
  isRestoring: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onSelectTab,
  restorationStatus,
  onEmergencyRestore,
  isRestoring,
}) => {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.75rem 1.5rem',
        backgroundColor: '#111827',
        borderBottom: '1px solid #1f2937',
        position: 'sticky',
        top: 0,
        zIndex: 50,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '1.4rem' }}>⚡</span>
          <span style={{ fontSize: '1.2rem', fontWeight: 700, letterSpacing: '-0.025em', color: '#f9fafb' }}>
            joulectrl
          </span>
          <span
            style={{
              fontSize: '0.65rem',
              fontWeight: 600,
              padding: '0.15rem 0.4rem',
              borderRadius: '0.25rem',
              backgroundColor: '#1e3a8a',
              color: '#93c5fd',
              textTransform: 'uppercase',
            }}
          >
            v0.1 · demo
          </span>
        </div>

        <nav style={{ display: 'flex', gap: '0.25rem', marginLeft: '1rem' }}>
          {(
            [
              { id: 'setup', label: '1. Setup' },
              { id: 'explorer', label: '2. Profile Explorer' },
              { id: 'validation', label: '3. Validation' },
              { id: 'watch', label: 'Passive Watch Mode' },
            ] as const
          ).map((item) => (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              style={{
                padding: '0.4rem 0.75rem',
                fontSize: '0.85rem',
                fontWeight: 500,
                borderRadius: '0.375rem',
                border: 'none',
                cursor: 'pointer',
                backgroundColor: activeTab === item.id ? '#374151' : 'transparent',
                color: activeTab === item.id ? '#f3f4f6' : '#9ca3af',
                transition: 'all 0.15s ease',
              }}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        {/* Restoration status pill */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.25rem 0.6rem',
            borderRadius: '9999px',
            fontSize: '0.75rem',
            fontWeight: 500,
            backgroundColor: restorationStatus === 'restored' ? '#064e3b' : '#7f1d1d',
            color: restorationStatus === 'restored' ? '#6ee7b7' : '#fca5a5',
            border: `1px solid ${restorationStatus === 'restored' ? '#047857' : '#991b1b'}`,
          }}
        >
          <span style={{ width: 6, height: 6, borderRadius: '50%', backgroundColor: restorationStatus === 'restored' ? '#34d399' : '#f87171' }} />
          <span>Restoration: {restorationStatus.toUpperCase()}</span>
        </div>

        <button
          onClick={onEmergencyRestore}
          disabled={isRestoring}
          style={{
            padding: '0.3rem 0.7rem',
            fontSize: '0.75rem',
            fontWeight: 500,
            borderRadius: '0.375rem',
            backgroundColor: '#1f2937',
            color: '#f87171',
            border: '1px solid #374151',
            cursor: isRestoring ? 'wait' : 'pointer',
          }}
          title="Emergency restoration of CPU and power settings"
        >
          {isRestoring ? 'Restoring...' : 'Restore State'}
        </button>
      </div>
    </header>
  );
};
