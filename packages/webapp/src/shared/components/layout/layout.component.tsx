import { isNil } from 'ramda';
import { ReactNode, useMemo, useState } from 'react';
import { matchPath, useLocation } from 'react-router-dom';

import { NO_NAVIGATION_ROUTES } from '../../../app/config/routes';
import { AppearancePreferenceSync } from '../../hooks/useAppearancePreference';
import { WelcomeModal } from '../welcomeModal';
import { Header } from './header';
import { LayoutContext } from './layout.context';
import { Sidebar } from './sidebar';

export type LayoutProps = {
  children?: ReactNode;
};

const SIDEBAR_COLLAPSED_KEY = 'sigmarail.sidebar.collapsed';

const getInitialSidebarCollapsed = () => {
  if (typeof window === 'undefined') return false;
  try {
    const saved = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (saved === 'true') return true;
    if (saved === 'false') return false;
  } catch {
    // Use the responsive default when browser storage is unavailable.
  }
  return window.matchMedia('(min-width: 768px) and (max-width: 1279px)').matches;
};

const saveSidebarPreference = (collapsed: boolean) => {
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(collapsed));
  } catch {
    // The current in-memory choice still works when browser storage is unavailable.
  }
};

export const Layout = ({ children }: LayoutProps) => {
  const [isSideMenuOpen, setSideMenuOpen] = useState(false);
  const [isSidebarCollapsed, setSidebarCollapsed] = useState(getInitialSidebarCollapsed);
  const { pathname } = useLocation();

  const rememberSidebarCollapsed = useMemo(
    () => (collapsed: boolean) => {
      setSidebarCollapsed(collapsed);
      saveSidebarPreference(collapsed);
    },
    []
  );

  const shouldDisplaySidebar = useMemo(
    () => NO_NAVIGATION_ROUTES.every((path) => isNil(matchPath({ path }, pathname))),
    [pathname]
  );

  const isAuthRoute = useMemo(
    () => !NO_NAVIGATION_ROUTES.every((path) => isNil(matchPath({ path }, pathname))),
    [pathname]
  );

  const isWorkbenchRoute = useMemo(() => {
    const routePath = pathname.replace(/^\/[^/]+/, '') || '/';
    return [
      '/screens',
      '/charts',
      '/stock',
      '/watchlists',
      '/market',
      '/strategies',
      '/backtests',
      '/optimize',
      '/deploy',
      '/monitor',
    ].some((path) => routePath === path || routePath.startsWith(`${path}/`));
  }, [pathname]);

  const toggleSidebar = useMemo(
    () => () => setSidebarCollapsed((prev) => {
      const next = !prev;
      saveSidebarPreference(next);
      return next;
    }),
    []
  );

  const value = useMemo(
    () => ({
      isSidebarAvailable: shouldDisplaySidebar,
      isSideMenuOpen,
      setSideMenuOpen,
      isSidebarCollapsed,
      setSidebarCollapsed: rememberSidebarCollapsed,
      toggleSidebar,
    }),
    [shouldDisplaySidebar, isSideMenuOpen, isSidebarCollapsed, toggleSidebar, rememberSidebarCollapsed]
  );

  const sidebarWidth = isSidebarCollapsed ? 'md:pl-16' : 'md:pl-72';

  return (
    <LayoutContext.Provider value={value}>
      <AppearancePreferenceSync />
      <div
        data-testid="application-layout-shell"
        className={`${shouldDisplaySidebar ? sidebarWidth : ''} flex flex-col ${
          isWorkbenchRoute ? 'h-screen supports-[height:100svh]:h-svh overflow-hidden' : 'min-h-[100dvh]'
        }`}
      >
        {!isAuthRoute && (isWorkbenchRoute ? <Header menuOnly /> : <Header />)}
        <main
          className={
            isAuthRoute
              ? undefined
              : isWorkbenchRoute
                ? 'flex min-h-0 flex-1 flex-col overflow-y-auto overscroll-contain'
                : 'py-10'
          }
        >
          {children}
        </main>
      </div>
      {shouldDisplaySidebar && <Sidebar />}
      {shouldDisplaySidebar && <WelcomeModal />}
    </LayoutContext.Provider>
  );
};
