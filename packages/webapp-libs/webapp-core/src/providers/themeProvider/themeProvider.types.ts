import { ReactNode } from 'react';

export const THEME_DEFAULT_STORAGE_KEY = 'theme';

export enum Themes {
  LIGHT = 'light',
  DARK = 'dark',
}

export enum ThemeMode {
  LIGHT = 'light',
  DARK = 'dark',
  SYSTEM = 'system',
}

export type ThemeAction =
  | { type: 'SET_THEME'; payload: ThemeMode }
  | { type: 'TOGGLE_THEME'; payload: undefined }
  | { type: 'SYSTEM_THEME_CHANGED'; payload: Themes };

export interface ThemeState {
  preference: ThemeMode;
  theme: Themes;
}

export type ThemeProviderProps = {
  children: ReactNode;
  storageKey?: string;
};
