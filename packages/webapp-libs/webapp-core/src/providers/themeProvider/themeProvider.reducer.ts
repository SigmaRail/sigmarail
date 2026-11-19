import { assertUnreachable } from '../../utils';
import { ThemeAction, ThemeMode, ThemeState, Themes } from './themeProvider.types';
import { resolveTheme, setThemeInDOM } from './themeProvider.utils';

export const themeReducer = (state: ThemeState, { type, payload }: ThemeAction) => {
  switch (type) {
    case 'SET_THEME': {
      const next = { preference: payload, theme: resolveTheme(payload) };
      setThemeInDOM(next.theme);
      return next;
    }
    case 'TOGGLE_THEME': {
      const preference = state.theme === Themes.LIGHT ? ThemeMode.DARK : ThemeMode.LIGHT;
      const next = { preference, theme: resolveTheme(preference) };
      setThemeInDOM(next.theme);
      return next;
    }
    case 'SYSTEM_THEME_CHANGED': {
      if (state.preference !== ThemeMode.SYSTEM) return state;
      setThemeInDOM(payload);
      return { ...state, theme: payload };
    }
    default:
      return assertUnreachable(type, 'Cannot resolve locales reducer action type');
  }
};
