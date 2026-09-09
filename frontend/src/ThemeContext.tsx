import React, { createContext, useContext, useEffect, useState } from 'react';
import { getThemeColors, setActiveTheme, ThemeColors, ThemeMode } from './design';

interface ThemeContextType {
  theme: ThemeMode;
  themeColors: ThemeColors;
  toggleTheme: () => void;
  setTheme: (t: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextType | null>(null);

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<ThemeMode>(() => {
    return (localStorage.getItem('joulectrl_theme') as ThemeMode) || 'dark';
  });

  const themeColors = getThemeColors(theme);

  useEffect(() => {
    setActiveTheme(theme);
    document.body.style.backgroundColor = themeColors.bg;
    document.body.style.color = themeColors.textPrimary;
    localStorage.setItem('joulectrl_theme', theme);
  }, [theme, themeColors]);

  const toggleTheme = () => {
    setThemeState((prev) => {
      const next = prev === 'dark' ? 'light' : 'dark';
      setActiveTheme(next);
      return next;
    });
  };

  return (
    <ThemeContext.Provider value={{ theme, themeColors, toggleTheme, setTheme: setThemeState }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = (): ThemeContextType => {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    return {
      theme: 'dark',
      themeColors: getThemeColors('dark'),
      toggleTheme: () => {},
      setTheme: () => {},
    };
  }
  return ctx;
};
