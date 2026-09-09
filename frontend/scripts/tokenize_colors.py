#!/usr/bin/env python3
"""Tokenize raw hex colors in ExplorerView/SetupView/ValidationView/WatchPanel/ParetoChart
into design.ts token references."""
import re, io, os

MAP = {
    "'#08090a'": 'colors.bg',
    '"#08090a"': 'colors.bg',
    "'#0f1011'": 'colors.panel',
    '"#0f1011"': 'colors.panel',
    "'#141516'": 'colors.surface',
    '"#141516"': 'colors.surface',
    "'#191a1b'": 'colors.surfaceElevated',
    '"#191a1b"': 'colors.surfaceElevated',
    "'#f7f8f8'": 'colors.textPrimary',
    '"#f7f8f8"': 'colors.textPrimary',
    "'#d0d6e0'": 'colors.textSecondary',
    '"#d0d6e0"': 'colors.textSecondary',
    "'#8a8f98'": 'colors.textTertiary',
    '"#8a8f98"': 'colors.textTertiary',
    "'#62666d'": 'colors.textQuaternary',
    '"#62666d"': 'colors.textQuaternary',
    "'#7170ff'": 'colors.accent',
    '"#7170ff"': 'colors.accent',
    "'#828fff'": 'colors.accentHover',
    '"#828fff"': 'colors.accentHover',
    "'#5e6ad2'": 'colors.accentBg',
    '"#5e6ad2"': 'colors.accentBg',
    "'#10b981'": 'colors.emerald',
    '"#10b981"': 'colors.emerald',
    "'#27a644'": 'colors.green',
    '"#27a644"': 'colors.green',
    "'#f59e0b'": 'colors.amber',
    '"#f59e0b"': 'colors.amber',
    "'#f4586e'": 'colors.red',
    '"#f4586e"': 'colors.red',
    "'#ffffff'": 'colors.textPrimary',
    '"#ffffff"': 'colors.textPrimary',
    "'#ef4444'": 'colors.red',
    '"#ef4444"': 'colors.red',
    # legacy tailwind-ish leftovers
    "'#fcd34d'": 'colors.amber',
    '"#fcd34d"': 'colors.amber',
    "'#d97706'": 'colors.amber',
    '"#d97706"': 'colors.amber',
    "'#b45309'": 'colors.amber',
    '"#b45309"': 'colors.amber',
    "'#78350f'": 'colors.amber',
    '"#78350f"': 'colors.amber',
    "'#b91c1c'": 'colors.red',
    '"#b91c1c"': 'colors.red',
    "'#be123c'": 'colors.red',
    '"#be123c"': 'colors.red',
    "'#065f46'": 'colors.emerald',
    '"#065f46"': 'colors.emerald',
    "'#a7f3d0'": 'colors.emerald',
    '"#a7f3d0"': 'colors.emerald',
    "'#94a3b8'": 'colors.textTertiary',
    '"#94a3b8"': 'colors.textTertiary',
    "'#334155'": 'colors.textQuaternary',
    '"#334155"': 'colors.textQuaternary',
    # alpha-suffixed variants -> rgba border token
    "'#191a1b15'": "'rgba(25,26,27,0.15)'",
    '"#191a1b15"': '"rgba(25,26,27,0.15)"',
    "'#78350f15'": "'rgba(245,158,11,0.10)'",
    '"#78350f15"': '"rgba(245,158,11,0.10)"',
}

FILES = ["ExplorerView.tsx", "SetupView.tsx", "ValidationView.tsx", "WatchPanel.tsx", "ParetoChart.tsx"]
base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src', 'components')

for fname in FILES:
    p = os.path.join(base, fname)
    src = open(p, encoding="utf-8").read()
    orig = src
    for k, v in MAP.items():
        src = src.replace(k, v)
    # rgba(255,255,255,0.08) raw borders -> token where plain
    if 'colors' not in src.split('\n')[0:12].__str__():
        pass
    # add import if we introduced tokens
    if 'colors.' in src and "from '../design'" not in src:
        # insert after last import line
        lines = src.split('\n')
        last_import = max(i for i, l in enumerate(lines) if l.startswith('import '))
        lines.insert(last_import + 1, "import { colors } from '../design';")
        src = '\n'.join(lines)
    open(p, 'w', encoding='utf-8', newline='').write(src)
    n = len(re.findall(r'#[0-9a-fA-F]{3,8}\b', src))
    print(f"{fname}: remaining hex literals: {n}")
