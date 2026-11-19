import { useCallback, useContext } from 'react';

import { ThemeContext, ThemeMode } from '../../providers/themeProvider';

export const useTheme = () => {
  const context = useContext(ThemeContext);

  if (!context) throw new Error('ThemeContext used outside of Provider');

  const {
    themeState: { preference, theme },
    dispatch,
  } = context;

  const setTheme = useCallback(
    (mode: ThemeMode) => {
      dispatch({ type: 'SET_THEME', payload: mode });
    },
    [dispatch]
  );

  const toggleTheme = useCallback(() => {
    dispatch({ type: 'TOGGLE_THEME', payload: undefined });
  }, [dispatch]);

  return { theme, themePreference: preference, setTheme, toggleTheme };
};
