import { TenantUserRole } from '@sb/webapp-api-client';
import { CommandPalette } from '@sb/webapp-ai-assistant';
import { Link } from '@sb/webapp-core/components/buttons';
import { Button } from '@sb/webapp-core/components/ui/button';
import { Separator } from '@sb/webapp-core/components/ui/separator';
import { Tooltip, TooltipContent, TooltipTrigger } from '@sb/webapp-core/components/ui/tooltip';
import { useGenerateLocalePath, useMediaQuery } from '@sb/webapp-core/hooks';
import { useTheme } from '@sb/webapp-core/hooks/useTheme/useTheme';
import { cn } from '@sb/webapp-core/lib/utils';
import { Themes } from '@sb/webapp-core/providers/themeProvider';
import { media } from '@sb/webapp-core/theme';
import { PermissionGate } from '@sb/webapp-tenants/components/permissionGate';
import { TenantRoleAccess } from '@sb/webapp-tenants/components/tenantRoleAccess';
import { TenantSwitchSidebar } from '@sb/webapp-tenants/components/tenantSwitch';
import { useCurrentTenantRole, useGenerateTenantPath, usePermissionCheck, PermissionCode } from '@sb/webapp-tenants/hooks';
import {
  Building2,
  Activity,
  BarChart3,
  Bookmark,
  LineChart,
  Rocket,
  Search,
  Sliders,
  User,
  ChevronLeft,
  ChevronRight,
  Shield,
  X,
} from 'lucide-react';
import { HTMLAttributes, ReactNode, useCallback, useContext } from 'react';
import { FormattedMessage, useIntl } from 'react-intl';
import { useLocation } from 'react-router-dom';

import { RoutesConfig } from '../../../../app/config/routes';
import { Role } from '../../../../modules/auth/auth.types';
import { useAuth } from '../../../hooks';
import { RoleAccess } from '../../roleAccess';
import { LayoutContext } from '../layout.context';
import { SidebarExpandableItem, ExpandableMenuItem } from './sidebarExpandableItem';
import { SidebarLogo } from './sidebarLogo';
import { LanguageSwitcher } from '../header/languageSwitcher';
import { UserMenu } from '../header/userMenu';

type MenuItem = {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  roles: Role[];
  tenantRoles: TenantUserRole[];
  permissions?: PermissionCode[]; // New: permission-based access
  generatePath: () => string;
};

type ExpandableMenuSection = {
  id: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  items: ExpandableMenuItem[];
  roles: Role[];
  tenantRoles: TenantUserRole[];
  permissions?: PermissionCode[]; // New: permission-based access
};

type MenuSection = {
  id: string;
  label: ReactNode;
  items: MenuItem[];
  expandableSections?: ExpandableMenuSection[];
};

export const Sidebar = (props: HTMLAttributes<HTMLDivElement>) => {
  const intl = useIntl();
  const generateLocalePath = useGenerateLocalePath();
  const generateTenantPath = useGenerateTenantPath();
  const { pathname } = useLocation();
  const { setSideMenuOpen, isSideMenuOpen, isSidebarCollapsed, toggleSidebar } = useContext(LayoutContext);
  const { matches: isWideViewport } = useMediaQuery({
    above: media.Breakpoint.TABLET,
  });
  const { isLoggedIn, currentUser } = useAuth();
  const { theme } = useTheme();
  const currentTenantRole = useCurrentTenantRole();
  const userRoles = currentUser?.roles || [];

  // Get user's permissions for permission-based menu items
  const { userPermissions } = usePermissionCheck([]);

  const closeSidebar = useCallback(() => setSideMenuOpen(false), [setSideMenuOpen]);

  // Helper to check if user has a specific permission
  const hasPermission = useCallback((permissionCode: PermissionCode): boolean => {
    return userPermissions.includes(permissionCode);
  }, [userPermissions]);

  // Helper to check if user has any of the required permissions
  const hasAnyPermission = useCallback((permissions: PermissionCode[]): boolean => {
    if (!permissions || permissions.length === 0) return true;
    return permissions.some((p) => userPermissions.includes(p));
  }, [userPermissions]);

  // Helper to check if user has access to a menu item based on roles and permissions
  const hasAccessToItem = useCallback((item: MenuItem): boolean => {
    // If no roles or permissions required, allow access
    if (item.roles.length === 0 && item.tenantRoles.length === 0 && (!item.permissions || item.permissions.length === 0)) {
      return true;
    }
    // Check app-level roles
    if (item.roles.length > 0 && item.roles.some((role) => userRoles.includes(role))) {
      return true;
    }
    // Check tenant-level roles (legacy)
    if (item.tenantRoles.length > 0 && item.tenantRoles.some((role) => role === currentTenantRole)) {
      return true;
    }
    // Check permissions (new RBAC)
    if (item.permissions && item.permissions.length > 0 && hasAnyPermission(item.permissions)) {
      return true;
    }
    return false;
  }, [userRoles, currentTenantRole, hasAnyPermission]);

  // Helper to check if user has access to an expandable section
  const hasAccessToExpandableSection = useCallback((section: ExpandableMenuSection): boolean => {
    // If no roles or permissions required, allow access
    if (section.roles.length === 0 && section.tenantRoles.length === 0 && (!section.permissions || section.permissions.length === 0)) {
      return true;
    }
    // Check app-level roles
    if (section.roles.length > 0 && section.roles.some((role) => userRoles.includes(role))) {
      return true;
    }
    // Check tenant-level roles (legacy)
    if (section.tenantRoles.length > 0 && section.tenantRoles.some((role) => role === currentTenantRole)) {
      return true;
    }
    // Check permissions (new RBAC)
    if (section.permissions && section.permissions.length > 0 && hasAnyPermission(section.permissions)) {
      return true;
    }
    return false;
  }, [userRoles, currentTenantRole, hasAnyPermission]);

  // Helper to check if user has access to any item in a section
  const hasAccessToSection = useCallback((section: MenuSection): boolean => {
    const hasAccessToAnyItem = section.items.some(hasAccessToItem);
    const hasAccessToAnyExpandable = section.expandableSections?.some(hasAccessToExpandableSection) ?? false;
    return hasAccessToAnyItem || hasAccessToAnyExpandable;
  }, [hasAccessToItem, hasAccessToExpandableSection]);

  const menuItemClassName = ({ isActive = false }: { isActive?: boolean }) =>
    cn(
      'flex items-center rounded-md text-sm font-medium transition-colors',
      'hover:bg-accent hover:text-accent-foreground',
      {
        'justify-center px-0 py-2.5': isSidebarCollapsed && isWideViewport,
        'gap-3 px-3 py-2.5': !isSidebarCollapsed || !isWideViewport,
        'bg-accent text-accent-foreground': isActive,
        'text-muted-foreground': !isActive,
      }
    );

  const isActive = (path: string) => {
    if (path === RoutesConfig.home) {
      return pathname === generateTenantPath(RoutesConfig.home);
    }
    return pathname.includes(path);
  };

  const menuSections: MenuSection[] = [
    {
      id: 'research',
      label: 'Research',
      items: [
        {
          path: 'screens',
          label: 'Screener',
          icon: Search,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('screens'),
        },
        {
          path: 'charts',
          label: 'Charts',
          icon: LineChart,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('charts'),
        },
        {
          path: 'watchlists',
          label: 'Watchlists',
          icon: Bookmark,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('watchlists'),
        },
        {
          path: 'market',
          label: 'Market',
          icon: BarChart3,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('market'),
        },
      ],
    },
    {
      id: 'backtests',
      label: 'Backtests',
      items: [
        {
          path: 'strategies',
          label: 'Strategies',
          icon: Sliders,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('strategies'),
        },
        {
          path: 'backtests',
          label: 'Runs',
          icon: BarChart3,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('backtests'),
        },
        {
          path: 'optimize',
          label: 'Optimize',
          icon: LineChart,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('optimize'),
        },
      ],
    },
    {
      id: 'operations',
      label: 'Live Trading',
      items: [
        {
          path: 'deploy',
          label: 'Deploy',
          icon: Rocket,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('deploy'),
        },
        {
          path: 'monitor',
          label: 'Monitor',
          icon: Activity,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath('monitor'),
        },
      ],
    },
    {
      id: 'settings',
      label: 'Settings',
      items: [
        {
          path: RoutesConfig.tenant.settings.general,
          label: 'Organization settings',
          icon: Building2,
          roles: [],
          tenantRoles: [],
          permissions: ['org.settings.view'],
          generatePath: () => generateTenantPath(RoutesConfig.tenant.settings.general),
        },
        {
          path: RoutesConfig.profile,
          label: 'Profile',
          icon: User,
          roles: [],
          tenantRoles: [],
          generatePath: () => generateLocalePath(RoutesConfig.profile),
        },
        {
          path: RoutesConfig.admin,
          label: 'Admin panel',
          icon: Shield,
          roles: [Role.ADMIN],
          tenantRoles: [],
          generatePath: () => generateLocalePath(RoutesConfig.admin),
        },
      ],
    },
  ];

  const renderMenuItem = (item: MenuItem) => {
    const Icon = item.icon;
    const active = isActive(item.path);
    const content = (
      <Link to={item.generatePath()} onClick={closeSidebar} navLink className={menuItemClassName({ isActive: active })}>
        <Icon className="h-5 w-5 shrink-0" />
        {(!isSidebarCollapsed || !isWideViewport) && <span className="truncate">{item.label}</span>}
      </Link>
    );

    const wrappedContent =
      isSidebarCollapsed && isWideViewport ? (
        <Tooltip delayDuration={200}>
          <TooltipTrigger asChild>{content}</TooltipTrigger>
          <TooltipContent side="right">{item.label}</TooltipContent>
        </Tooltip>
      ) : (
        content
      );

    // Check app-level roles first
    if (item.roles.length > 0) {
      return (
        <RoleAccess allowedRoles={item.roles} key={item.path}>
          {wrappedContent}
        </RoleAccess>
      );
    }

    // Then check permission-based access (new RBAC)
    if (item.permissions && item.permissions.length > 0) {
      return (
        <PermissionGate permissions={item.permissions} mode="any" key={item.path}>
          {wrappedContent}
        </PermissionGate>
      );
    }

    // Legacy: check tenant roles
    if (item.tenantRoles.length > 0) {
      return (
        <TenantRoleAccess allowedRoles={item.tenantRoles} key={item.path}>
          {wrappedContent}
        </TenantRoleAccess>
      );
    }

    return <div key={item.path}>{wrappedContent}</div>;
  };

  const renderExpandableSection = (expandable: ExpandableMenuSection) => {
    // Filter items based on their individual permissions
    const filteredItems = expandable.items.filter((item) => {
      // Dividers are always shown (they have type: 'divider')
      if ('type' in item && item.type === 'divider') {
        return true;
      }
      // Links: check permissions
      const linkItem = item as { permissions?: string[] };
      if (!linkItem.permissions || linkItem.permissions.length === 0) {
        return true; // No permissions required
      }
      return linkItem.permissions.some((p) => userPermissions.includes(p));
    });

    // If no items remain after filtering (excluding dividers), don't show the section
    const hasVisibleItems = filteredItems.some(
      (item) => !('type' in item && item.type === 'divider')
    );
    if (!hasVisibleItems) {
      return null;
    }

    const content = (
      <SidebarExpandableItem
        key={expandable.id}
        label={expandable.label}
        icon={expandable.icon}
        items={filteredItems}
        isActive={isActive}
        isCollapsed={isSidebarCollapsed && isWideViewport}
        isDesktop={isWideViewport}
        onItemClick={closeSidebar}
      />
    );

    // Check app-level roles first
    if (expandable.roles.length > 0) {
      return (
        <RoleAccess allowedRoles={expandable.roles} key={expandable.id}>
          {content}
        </RoleAccess>
      );
    }

    // Then check permission-based access (new RBAC)
    if (expandable.permissions && expandable.permissions.length > 0) {
      return (
        <PermissionGate permissions={expandable.permissions} mode="any" key={expandable.id}>
          {content}
        </PermissionGate>
      );
    }

    // Legacy: check tenant roles
    if (expandable.tenantRoles.length > 0) {
      return (
        <TenantRoleAccess allowedRoles={expandable.tenantRoles} key={expandable.id}>
          {content}
        </TenantRoleAccess>
      );
    }

    return <div key={expandable.id}>{content}</div>;
  };

  const renderSection = (section: MenuSection, index: number, visibleIndex: number) => {
    // Don't render the section if user doesn't have access to any items
    if (!hasAccessToSection(section)) {
      return null;
    }

    return (
      <div key={section.id} className="flex flex-col gap-1">
        {visibleIndex > 0 && <Separator className="my-2" />}
        {(!isSidebarCollapsed || !isWideViewport) && (
          <span className="px-3 py-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {section.label}
          </span>
        )}
        {section.items.map(renderMenuItem)}
        {section.expandableSections?.map(renderExpandableSection)}
      </div>
    );
  };

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={cn('pointer-events-none fixed inset-0 z-50 bg-black/80 opacity-0 transition-opacity md:hidden', {
          'pointer-events-auto opacity-100': isSideMenuOpen && !isWideViewport,
        })}
        onClick={closeSidebar}
        aria-hidden="true"
      />

      {/* Mobile close button */}
      {isSideMenuOpen && !isWideViewport && (
        <Button
          variant="ghost"
          size="icon"
          className="fixed left-[280px] top-4 z-60 md:hidden"
          onClick={closeSidebar}
          aria-label={intl.formatMessage({
            defaultMessage: 'Close menu',
            id: 'Home / close sidebar icon label',
          })}
        >
          <X className="h-5 w-5" />
        </Button>
      )}

      {/* Sidebar */}
      <aside
        {...props}
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex flex-col border-r bg-background transition-all duration-300',
          'md:translate-x-0',
          {
            '-translate-x-full md:translate-x-0': !isSideMenuOpen && !isWideViewport,
            'translate-x-0': isSideMenuOpen || isWideViewport,
            'md:w-16': isSidebarCollapsed && isWideViewport,
            'w-72': !isSidebarCollapsed || !isWideViewport,
          },
          props.className
        )}
      >
        <div className="flex h-full flex-col">
          {/* Top section: Logo and Tenant Switch */}
          <div className="flex flex-col gap-4 border-b p-4">
            {/* Logo */}
            <div className="flex items-center justify-center">
              <SidebarLogo
                isCollapsed={isSidebarCollapsed && isWideViewport}
                logoColor={theme === Themes.DARK ? 'white' : 'black'}
                to={generateTenantPath(RoutesConfig.home)}
                onLogoClick={closeSidebar}
              />
            </div>

            {/* Tenant Switch */}
            {isLoggedIn && (
              <div
                className={cn('px-0', {
                  'flex justify-center': isSidebarCollapsed && isWideViewport,
                })}
              >
                <TenantSwitchSidebar collapsed={isSidebarCollapsed && isWideViewport} />
              </div>
            )}

            {isLoggedIn && (
              <CommandPalette
                compact={isSidebarCollapsed && isWideViewport}
                triggerClassName={isSidebarCollapsed && isWideViewport ? 'w-full justify-center px-0' : 'w-full justify-start px-3 xl:w-full'}
              />
            )}
          </div>

          {/* Menu items */}
          <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-4">
            <div className="flex flex-col">
              {(() => {
                let visibleIndex = 0;
                return menuSections.map((section, index) => {
                  // Legal section is always visible, other sections require login
                  if (section.id === 'legal') {
                    const result = renderSection(section, index, visibleIndex);
                    if (result) visibleIndex++;
                    return result;
                  }
                  if (!isLoggedIn) return null;
                  const result = renderSection(section, index, visibleIndex);
                  if (result) visibleIndex++;
                  return result;
                });
              })()}
            </div>
          </nav>

          {/* Bottom section: Toggle button and User panel */}
          <div className="border-t">
            {isLoggedIn && (
              <div
                className={cn('flex items-center justify-between gap-2 px-3 py-2', {
                  'flex-col px-2': isSidebarCollapsed && isWideViewport,
                })}
              >
                {!(isSidebarCollapsed && isWideViewport) && <LanguageSwitcher />}
                <UserMenu className={isSidebarCollapsed && isWideViewport ? 'flex-col' : undefined} />
              </div>
            )}
            {/* Toggle sidebar button */}
            {isWideViewport && (
              <div className="p-2">
                <Tooltip delayDuration={200}>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={toggleSidebar}
                      className={cn('w-full justify-start', {
                        'justify-center px-0': isSidebarCollapsed,
                      })}
                      aria-label={intl.formatMessage({
                        defaultMessage: 'Toggle sidebar',
                        id: 'Sidebar / Toggle sidebar',
                      })}
                    >
                      {isSidebarCollapsed ? (
                        <ChevronRight className="h-4 w-4" />
                      ) : (
                        <>
                          <ChevronLeft className="h-4 w-4" />
                          <span className="ml-2">
                            <FormattedMessage defaultMessage="Collapse" id="Sidebar / Collapse" />
                          </span>
                        </>
                      )}
                    </Button>
                  </TooltipTrigger>
                  {isSidebarCollapsed && (
                    <TooltipContent side="right">
                      <FormattedMessage defaultMessage="Expand sidebar" id="Sidebar / Expand sidebar" />
                    </TooltipContent>
                  )}
                </Tooltip>
              </div>
            )}
          </div>
        </div>
      </aside>
    </>
  );
};
