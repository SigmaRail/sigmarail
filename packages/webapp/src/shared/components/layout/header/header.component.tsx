import { CommandPalette } from '@sb/webapp-ai-assistant';
import { Button } from '@sb/webapp-core/components/ui/button';
import { cn } from '@sb/webapp-core/lib/utils';
import { Menu } from 'lucide-react';
import { HTMLAttributes, useContext } from 'react';
import { useIntl } from 'react-intl';

import { LayoutContext } from '../layout.context';
import { LanguageSwitcher } from './languageSwitcher';
import { UserMenu } from './userMenu';

export type HeaderProps = HTMLAttributes<HTMLElement> & {
  /** Compact menu control used on workbench routes where page chrome owns the header. */
  menuOnly?: boolean;
};

export const Header = ({ menuOnly = false, ...props }: HeaderProps) => {
  const intl = useIntl();
  const { setSideMenuOpen, isSideMenuOpen, isSidebarAvailable } = useContext(LayoutContext);

  return (
    <header
      {...props}
      className={cn(
        menuOnly
          ? 'sticky top-0 z-40 h-10 border-b-0 bg-transparent md:hidden'
          : 'sticky top-0 z-40 border-b bg-background/80 backdrop-blur-sm',
        props.className
      )}
    >
      <div className={cn('flex flex-row items-center gap-x-4', menuOnly ? 'h-10 px-2' : 'h-16 px-4 sm:px-6 lg:px-8')}>
        {isSidebarAvailable && (
          <Button
            variant="ghost"
            size="icon"
            className={menuOnly ? undefined : 'xl:hidden'}
            onClick={() => setSideMenuOpen(true)}
            aria-expanded={isSideMenuOpen}
            aria-label={intl.formatMessage({
              id: 'Header / Home menu link aria label',
              defaultMessage: 'Open menu',
            })}
          >
            <Menu className="h-5 w-5" />
          </Button>
        )}
        {!menuOnly && (
          <>
            <div className="flex-1"></div>
            <CommandPalette />
            <LanguageSwitcher />
            <UserMenu />
          </>
        )}
      </div>
    </header>
  );
};
