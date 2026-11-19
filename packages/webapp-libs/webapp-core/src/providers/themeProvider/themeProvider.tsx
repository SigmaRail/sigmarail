import { useEffect, useMemo, useReducer } from 'react';

import { reportError } from '../../utils/reportError';
import { ThemeContext, themeInitialState } from './themeProvider.context';
import { themeReducer } from './themeProvider.reducer';
import { THEME_DEFAULT_STORAGE_KEY, ThemeMode, ThemeProviderProps } from './themeProvider.types';
import { getSystemTheme, setThemeInDOM } from './themeProvider.utils';

export const ThemeProvider = ({ children, storageKey = THEME_DEFAULT_STORAGE_KEY }: ThemeProviderProps) => {
  const [themeState, dispatch] = useReducer(themeReducer, themeInitialState);
  const value = useMemo(() => ({ themeState, dispatch }), [themeState, dispatch]);

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, themeState.preference);
    } catch (e) {
      reportError(e);
    }
  }, [themeState.preference, storageKey]);

  useEffect(() => {
    setThemeInDOM(themeState.theme);
  }, [themeState.theme]);

  useEffect(() => {
    if (themeState.preference !== ThemeMode.SYSTEM || typeof window === 'undefined' || !window.matchMedia) return;

    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (event: MediaQueryListEvent) => dispatch({ type: 'SYSTEM_THEME_CHANGED', payload: getSystemTheme(event) });
    media.addEventListener?.('change', handleChange);
    // Older Safari versions expose addListener instead of addEventListener.
    if (!media.addEventListener) media.addListener?.(handleChange);

    return () => {
      media.removeEventListener?.('change', handleChange);
      if (!media.removeEventListener) media.removeListener?.(handleChange);
    };
  }, [themeState.preference]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export default ThemeProvider;
