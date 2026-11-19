import { reportError } from '../../utils/reportError';
import { THEME_DEFAULT_STORAGE_KEY, ThemeMode, Themes, ThemeState } from './themeProvider.types';

const MEDIA = '(prefers-color-scheme: dark)';

export const getSystemTheme = (e?: MediaQueryList | MediaQueryListEvent): Themes => {
  const media = e ?? (typeof window !== 'undefined' ? window.matchMedia?.(MEDIA) : undefined);
  return media?.matches ? Themes.DARK : Themes.LIGHT;
};

export const setThemeInDOM = (theme: Themes) => {
  const classList = document.querySelector('html')?.classList;
  classList?.remove?.(theme === Themes.LIGHT ? Themes.DARK : Themes.LIGHT);
  classList?.add?.(theme);
};

export const getThemePreference = (storageKey = THEME_DEFAULT_STORAGE_KEY): ThemeMode => {
  let preference: string | null = null;

  try {
    preference = localStorage.getItem(storageKey);
  } catch (e) {
    reportError(e);
  }

  return Object.values(ThemeMode).includes(preference as ThemeMode) ? (preference as ThemeMode) : ThemeMode.SYSTEM;
};

export const resolveTheme = (preference: ThemeMode, systemTheme = getSystemTheme()): Themes => {
  if (preference === ThemeMode.SYSTEM) return systemTheme;
  return preference === ThemeMode.DARK ? Themes.DARK : Themes.LIGHT;
};

export const getInitialThemeState = (storageKey = THEME_DEFAULT_STORAGE_KEY): ThemeState => {
  const preference = getThemePreference(storageKey);
  return { preference, theme: resolveTheme(preference) };
};
