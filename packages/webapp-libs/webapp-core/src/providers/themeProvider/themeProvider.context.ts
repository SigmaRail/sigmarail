import React from 'react';

import { ThemeAction, ThemeState } from './themeProvider.types';
import { getInitialThemeState, setThemeInDOM } from './themeProvider.utils';

export const themeInitialState: ThemeState = getInitialThemeState();

if (typeof document !== 'undefined') setThemeInDOM(themeInitialState.theme);

export const ThemeContext = React.createContext<{
  themeState: ThemeState;
  dispatch: React.Dispatch<ThemeAction>;
}>({
  themeState: themeInitialState,
  dispatch: () => undefined,
});
